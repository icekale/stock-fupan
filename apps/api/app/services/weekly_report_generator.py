from __future__ import annotations

import html
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.renderers.png_exporter import export_pdf, export_png
from app.services.assets import AssetPaths, create_named_report_copies, create_report_asset_dir, write_json
from app.providers.a_stock_data import AStockQuoteProvider


CHINA_TZ = timezone(timedelta(hours=8))
WEEKLY_REPORT_ALGORITHM_VERSION = "weekly_report_daily_dimensions_v2"
DEFAULT_WEEKLY_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("600726.SH", "华电能源"),
    ("000539.SZ", "粤电力Ａ"),
    ("600744.SH", "华银电力"),
    ("301439.SZ", "泓淋电力"),
    ("688347.SH", "华虹公司"),
    ("600584.SH", "长电科技"),
    ("002156.SZ", "通富微电"),
    ("300476.SZ", "胜宏科技"),
    ("002463.SZ", "沪电股份"),
    ("002896.SZ", "中大力德"),
    ("688017.SH", "绿的谐波"),
    ("000799.SZ", "酒鬼酒"),
)
DEFAULT_WEEKLY_INDEX_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("000001.SH", "上证指数"),
    ("399006.SZ", "创业板指"),
    ("399001.SZ", "深证成指"),
)
WEEKLY_THEMES: dict[str, tuple[str, ...]] = {
    "电力": (
        "电力",
        "电网",
        "能源",
        "发电",
        "核电",
        "风电",
        "水电",
        "粤电",
        "华电",
        "大唐",
        "晋控",
        "黔源",
        "华能",
    ),
    "电力设备": (
        "输变电",
        "电网",
        "特锐德",
        "思源电气",
        "中国西电",
        "金盘科技",
        "平高电气",
        "长高电新",
        "许继电气",
        "电缆",
    ),
    "半导体/先进封装": (
        "芯",
        "半导体",
        "晶",
        "微",
        "封测",
        "封装",
        "长电",
        "通富",
        "华天",
        "中芯",
        "赛微",
        "华虹",
    ),
    "PCB/高速连接": (
        "生益",
        "沪电",
        "胜宏",
        "景旺",
        "深南电路",
        "鹏鼎",
        "东山",
        "世运",
        "PCB",
        "线路板",
        "电路",
    ),
    "机器人": (
        "机器人",
        "智能",
        "自动化",
        "精工",
        "机电",
        "伺服",
        "减速器",
        "绿的谐波",
        "埃斯顿",
    ),
    "有色/黄金": ("黄金", "铜", "铝", "钴", "锂", "钼", "稀土", "有色", "贵金属", "矿业"),
    "白酒/消费": ("白酒", "酒鬼酒", "今世缘", "舍得酒业", "贵州茅台", "五粮液", "零售", "百货"),
}


@dataclass(frozen=True)
class WeeklyGeneratedReport:
    trade_date: str
    start_date: str
    end_date: str
    assets: AssetPaths
    validation_errors: list[str]
    provider_status: dict[str, object]
    summary: dict[str, Any]


class TickFlowWeeklyDataClient:
    provider_name = "tickflow"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 120,
        batch_size: int = 100,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size

    def get_weekly_market_data(self, start_date: str, end_date: str) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("TICKFLOW_API_KEY 未配置")

        symbols = self._request_json("GET", "/v1/universes/CN_Equity_A")["data"]["symbols"]
        instruments = self._fetch_instruments(symbols)
        quotes = self._fetch_quotes()
        klines = self._fetch_klines(symbols, start_date, end_date)
        trading_dates = _trading_dates_from_klines(klines, start_date, end_date)
        stocks = [
            item
            for symbol, data in klines.items()
            if (
                item := _compact_kline(
                    symbol=symbol,
                    data=data,
                    trading_dates=trading_dates,
                    name=(instruments.get(symbol) or {}).get("name"),
                    realtime=quotes.get(symbol),
                )
            )
        ]
        indices = self._fetch_indices(start_date, end_date, trading_dates, quotes)
        return {
            "meta": {
                "source": "TickFlow",
                "range": f"{start_date}..{end_date}",
                "symbol_count": len(symbols),
                "klines_count": len(klines),
                "stock_rows": len(stocks),
                "quote_count": len(quotes),
                "instrument_count": len(instruments),
                "generated_at": datetime.now(CHINA_TZ).isoformat(timespec="seconds"),
            },
            "indices": indices,
            "breadth": _build_breadth(stocks, trading_dates),
            "theme_stats": _build_theme_stats(stocks),
            "top_week": _clean_stocks(
                sorted(
                    stocks,
                    key=lambda stock: stock.get("week_pct")
                    if stock.get("week_pct") is not None
                    else -999,
                    reverse=True,
                )
            )[:100],
            "top_friday": _clean_stocks(
                sorted(
                    stocks,
                    key=lambda stock: stock.get("friday_pct_from_kline")
                    if stock.get("friday_pct_from_kline") is not None
                    else -999,
                    reverse=True,
                )
            )[:100],
        }

    def _fetch_instruments(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        instruments: dict[str, dict[str, Any]] = {}
        for part in _chunks(symbols, 1000):
            payload = self._request_json("POST", "/v1/instruments", body={"symbols": part})
            for item in payload.get("data", []):
                if isinstance(item, dict):
                    instruments[str(item.get("symbol"))] = item
            time.sleep(0.05)
        return instruments

    def _fetch_quotes(self) -> dict[str, dict[str, Any]]:
        payload = self._request_json(
            "POST",
            "/v1/quotes",
            body={"universes": ["CN_Equity_A"]},
        )
        return {
            str(item.get("symbol")): item
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("symbol")
        }

    def _fetch_klines(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str,
    ) -> dict[str, dict[str, Any]]:
        klines: dict[str, dict[str, Any]] = {}
        start_time = _date_to_ms(start_date)
        end_time = _date_to_ms(_next_day(end_date))
        for part in _chunks(symbols, self.batch_size):
            payload = self._request_json(
                "GET",
                "/v1/klines/batch",
                params={
                    "symbols": ",".join(part),
                    "period": "1d",
                    "count": 10,
                    "start_time": start_time,
                    "end_time": end_time,
                },
            )
            data = payload.get("data") or {}
            if isinstance(data, dict):
                klines.update({str(key): value for key, value in data.items() if isinstance(value, dict)})
            time.sleep(1.05)
        return klines

    def _fetch_indices(
        self,
        start_date: str,
        end_date: str,
        trading_dates: list[str],
        quotes: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        index_names = {
            "000001.SH": "上证指数",
            "399006.SZ": "创业板指",
            "399001.SZ": "深证成指",
            "000852.SH": "中证1000",
            "000300.SH": "沪深300",
        }
        payload = self._request_json(
            "GET",
            "/v1/klines/batch",
            params={
                "symbols": ",".join(index_names),
                "period": "1d",
                "count": 10,
                "start_time": _date_to_ms(start_date),
                "end_time": _date_to_ms(_next_day(end_date)),
            },
        )
        return {
            symbol: compact
            for symbol, data in (payload.get("data") or {}).items()
            if (
                compact := _compact_kline(
                    symbol=symbol,
                    data=data,
                    trading_dates=trading_dates,
                    name=index_names.get(symbol),
                    realtime=quotes.get(symbol),
                )
            )
        }

    def _request_json(
        self,
        method: str,
        path: str,
        params: dict[str, object] | None = None,
        body: dict[str, object] | None = None,
        retry: int = 5,
    ) -> dict[str, Any]:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"x-api-key": self.api_key, "User-Agent": "stock-fupan-weekly/1.0"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        for attempt in range(retry):
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429:
                    wait_seconds = _rate_limit_wait_seconds(raw, attempt)
                    time.sleep(wait_seconds)
                    continue
                raise RuntimeError(f"TickFlow HTTP {exc.code}: {raw[:300]}") from exc
            except urllib.error.URLError:
                if attempt < retry - 1:
                    time.sleep(min(15, 2 * (attempt + 1)))
                    continue
                raise
        raise RuntimeError("TickFlow 请求重试耗尽")


class AStockWeeklyDataClient:
    provider_name = "a_stock"

    def __init__(
        self,
        timeout_seconds: float = 15,
        http_client: object | None = None,
        symbols: tuple[tuple[str, str], ...] = DEFAULT_WEEKLY_SYMBOLS,
        index_symbols: tuple[tuple[str, str], ...] = DEFAULT_WEEKLY_INDEX_SYMBOLS,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()
        self.symbols = symbols
        self.index_symbols = index_symbols

    def close(self) -> None:
        if self._owns_client:
            close = getattr(self.http_client, "close", None)
            if callable(close):
                close()

    def get_weekly_market_data(self, start_date: str, end_date: str) -> dict[str, Any]:
        symbols = [symbol for symbol, _name in self.symbols]
        index_symbols = [symbol for symbol, _name in self.index_symbols]
        names = {symbol: name for symbol, name in [*self.symbols, *self.index_symbols]}
        quotes = self._fetch_quotes([*symbols, *index_symbols])
        klines = {
            symbol: data
            for symbol in [*symbols, *index_symbols]
            if (data := self._fetch_baidu_kline(symbol, start_date))
        }
        trading_dates = _trading_dates_from_klines(klines, start_date, end_date)
        stocks = [
            item
            for symbol in symbols
            if (
                item := _compact_kline(
                    symbol=symbol,
                    data=klines.get(symbol, {}),
                    trading_dates=trading_dates,
                    name=names.get(symbol),
                    realtime=quotes.get(symbol),
                )
            )
        ]
        indices = {
            symbol: compact
            for symbol in index_symbols
            if (
                compact := _compact_kline(
                    symbol=symbol,
                    data=klines.get(symbol, {}),
                    trading_dates=trading_dates,
                    name=names.get(symbol),
                    realtime=quotes.get(symbol),
                )
            )
        }
        return {
            "meta": {
                "source": "a-stock-data",
                "range": f"{start_date}..{end_date}",
                "symbol_count": len(symbols),
                "klines_count": len(klines),
                "stock_rows": len(stocks),
                "quote_count": len(quotes),
                "instrument_count": len(names),
                "generated_at": datetime.now(CHINA_TZ).isoformat(timespec="seconds"),
            },
            "indices": indices,
            "breadth": _build_breadth(stocks, trading_dates),
            "theme_stats": _build_theme_stats(stocks),
            "top_week": _clean_stocks(
                sorted(
                    stocks,
                    key=lambda stock: stock.get("week_pct")
                    if stock.get("week_pct") is not None
                    else -999,
                    reverse=True,
                )
            )[:100],
            "top_friday": _clean_stocks(
                sorted(
                    stocks,
                    key=lambda stock: stock.get("friday_pct_from_kline")
                    if stock.get("friday_pct_from_kline") is not None
                    else -999,
                    reverse=True,
                )
            )[:100],
        }

    def _fetch_quotes(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        provider = AStockQuoteProvider(
            timeout_seconds=self.timeout_seconds,
            http_client=self.http_client,
        )
        return {
            quote.symbol: {
                "symbol": quote.symbol,
                "name": quote.name,
                "pct_change": quote.pct_change,
                "amount": quote.turnover_cny,
                "ext": {
                    "name": quote.name,
                    "turnover_rate": (quote.turnover_rate or 0) / 100,
                },
            }
            for quote in provider.get_quotes(symbols)
        }

    def _fetch_baidu_kline(self, symbol: str, start_date: str) -> dict[str, Any] | None:
        response = self.http_client.get(
            "https://finance.pae.baidu.com/selfselect/getstockquotation",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/vnd.finance-web.v1+json",
                "Origin": "https://gushitong.baidu.com",
                "Referer": "https://gushitong.baidu.com/",
            },
            params={
                "all": "1",
                "isIndex": "false",
                "isBk": "false",
                "isBlock": "false",
                "isFutures": "false",
                "isStock": "true",
                "newFormat": "1",
                "group": "quotation_kline_ab",
                "finClientType": "pc",
                "code": symbol.split(".", 1)[0],
                "start_time": start_date.replace("-", ""),
                "ktype": "1",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return _baidu_kline_payload_to_tickflow_shape(payload)


class WeeklyReportGenerator:
    def __init__(
        self,
        reports_root: Path,
        market_client: object | None = None,
        tickflow_client: object | None = None,
        news_provider: object | None = None,
    ) -> None:
        self.reports_root = reports_root
        self.market_client = market_client or tickflow_client
        self.news_provider = news_provider

    def generate_weekly_report(self, start_date: str, end_date: str) -> WeeklyGeneratedReport:
        trade_date = f"{start_date}_{end_date}"
        assets = create_report_asset_dir(self.reports_root, trade_date, "weekly")
        summary = self.market_client.get_weekly_market_data(start_date, end_date)
        summary["catalysts"] = self._collect_catalysts(summary, end_date)
        summary["algorithm_versions"] = {"weekly_report": WEEKLY_REPORT_ALGORITHM_VERSION}
        html_text = render_weekly_report_html(start_date, end_date, summary)
        assets.report_html.write_text(html_text, encoding="utf-8")
        export_png(assets.report_html, assets.report_png)
        export_pdf(assets.report_html, assets.report_pdf)
        create_named_report_copies(assets, trade_date=trade_date, kind="weekly")
        write_json(assets.snapshot, summary)
        write_json(assets.report_dto, summary)
        write_json(assets.news_raw, summary.get("catalysts", {}))
        write_json(assets.notes, {"overrides": []})
        return WeeklyGeneratedReport(
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            assets=assets,
            validation_errors=[],
            provider_status={
                "weekly_market": {
                    "provider": getattr(self.market_client, "provider_name", "market"),
                    "status": "success",
                    "fallback_used": False,
                    "reason": None,
                },
            },
            summary=summary,
        )

    def _collect_catalysts(self, summary: dict[str, Any], end_date: str) -> dict[str, list[dict[str, Any]]]:
        if self.news_provider is None:
            return {}
        catalysts: dict[str, list[dict[str, Any]]] = {}
        for sector_name in list(summary.get("theme_stats", {}))[:6]:
            try:
                items = self.news_provider.search_sector_news(sector_name, end_date)
            except Exception as exc:
                catalysts[sector_name] = [
                    {
                        "title": "Anspire 查询失败",
                        "summary": str(exc) or exc.__class__.__name__,
                        "source": "Anspire",
                    }
                ]
                continue
            catalysts[sector_name] = [
                _news_item_to_dict(item)
                for item in items[:3]
            ]
        return catalysts


def render_weekly_report_html(start_date: str, end_date: str, summary: dict[str, Any]) -> str:
    themes = _rank_weekly_themes(summary.get("theme_stats", {}))
    leader = themes[0] if themes else None
    indices = summary.get("indices", {})
    breadth = summary.get("breadth", {})
    last_breadth = breadth.get(end_date) or next(reversed(breadth.values()), {})
    meta = summary.get("meta", {})
    catalysts = summary.get("catalysts", {})
    html_sections = [
        _style_block(),
        "<main class='article-wrap'>",
        "<header class='article-header'>",
        f"<div class='eyebrow'>A股周报 · {html.escape(start_date)} 至 {html.escape(end_date)}</div>",
        f"<h1>{html.escape(start_date)} 至 {html.escape(end_date)} 周报复盘</h1>",
        "<p class='subtitle'>目标：找出本周最强板块和个股，并给出下周观察条件。</p>",
        "</header>",
        _render_weekly_core_conclusion(meta, leader, themes, last_breadth),
        _render_indices(indices),
        _render_breadth(breadth),
        _render_weekly_prediction_review(themes, breadth),
        _render_sector_detail_blocks(themes, catalysts),
        _render_capital_rotation(themes),
        _render_sustainability_ranking(themes),
        _render_next_week_strategy(themes, last_breadth),
        _render_weekend_news(themes, catalysts),
        _render_weekly_stock_ranking(themes),
        _render_practical_conclusion(themes, last_breadth),
        _render_index_mid_term(indices, breadth),
        _render_source_notes(),
        "</main>",
    ]
    return "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>" + html.escape(f"{start_date} 至 {end_date} 周报复盘") + "</title></head><body>" + "".join(html_sections) + "</body></html>"


def _style_block() -> str:
    return """
<style>
:root{--ink:#172033;--muted:#64748b;--line:#e2e8f0;--paper:#fff;--bg:#f6f7fb;--red:#b91c1c;--green:#15803d;--gold:#b45309;--blue:#1d4ed8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.72}
.article-wrap{max-width:1080px;margin:0 auto;padding:28px 24px 48px}.article-header{padding:24px 4px 16px}.eyebrow{font-size:13px;font-weight:800;letter-spacing:.18em;color:var(--gold);text-transform:uppercase}.article-header h1{margin:10px 0 8px;font-size:34px;line-height:1.2}.subtitle{margin:0;color:var(--muted)}
.card{background:var(--paper);border:1px solid var(--line);border-radius:24px;padding:22px;margin:16px 0;box-shadow:0 14px 40px rgba(15,23,42,.06)}.card h2{margin:0 0 14px;font-size:22px}.card h3{margin:18px 0 8px;font-size:17px}
.hero-card{border-color:#fde68a;background:linear-gradient(135deg,#fff,#fffbeb)}.metric-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:18px}.metric-grid div{border:1px solid var(--line);border-radius:18px;padding:14px;background:rgba(255,255,255,.72)}.metric-grid strong{display:block;font-size:22px}.metric-grid span{font-size:12px;color:var(--muted)}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:18px}table{width:100%;border-collapse:collapse;min-width:760px;background:#fff}th,td{padding:12px 14px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:#f8fafc;color:#334155;font-size:13px}.pos{color:var(--red);font-weight:800}.neg{color:var(--green);font-weight:800}.pill{display:inline-flex;border-radius:999px;background:#f1f5f9;color:#334155;font-size:12px;font-weight:800;padding:3px 9px;margin:2px}.stock-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.stock-card{border:1px solid var(--line);border-radius:18px;padding:14px;background:#fff}.stock-card strong{display:block}.stock-card small{color:var(--muted)}.note-list{padding-left:20px;margin:8px 0}.note-list li{margin:5px 0}.source-note{font-size:13px;color:var(--muted)}
.sector-block{border:1px solid var(--line);border-radius:20px;padding:18px;margin:14px 0;background:#fff}.sector-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.insight-card{border:1px solid var(--line);border-radius:16px;padding:13px;background:#f8fafc}.insight-label{font-size:12px;font-weight:900;color:var(--blue);letter-spacing:.08em;margin-bottom:5px}.path-flow{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:10px 0 14px}.path-node{border:1px solid var(--line);border-radius:999px;background:#fff;padding:6px 11px;font-weight:800}.path-arrow{color:var(--muted);font-weight:900}.conclusion-box{border:1px solid #fde68a;border-left:4px solid var(--gold);border-radius:18px;background:#fffbeb;padding:16px}.avoid-box{border:1px solid #bbf7d0;border-left:4px solid var(--green);border-radius:18px;background:#f0fdf4;padding:16px}.section-num{display:inline-flex;border-radius:999px;background:#172033;color:#fff;font-size:12px;font-weight:900;padding:2px 10px;margin-bottom:8px}.muted{color:var(--muted)}
@media(max-width:720px){.article-wrap{padding:18px 12px 32px}.article-header h1{font-size:26px}.metric-grid,.stock-grid,.sector-grid{grid-template-columns:1fr}table{min-width:640px}.card{padding:18px;border-radius:20px}}
</style>
"""


def _render_weekly_core_conclusion(
    meta: dict[str, Any],
    leader: dict[str, Any] | None,
    themes: list[dict[str, Any]],
    last_breadth: dict[str, Any],
) -> str:
    leader_name = str((leader or {}).get("name") or "暂无明确主线")
    runner_up = themes[1] if len(themes) > 1 else None
    return (
        "<section class='card hero-card'>"
        "<span class='section-num'>ONE</span>"
        "<h2>本周核心结论</h2>"
        f"<p>{html.escape(_core_conclusion(leader, last_breadth))}</p>"
        f"<p><span class='pill'>最强主线：{html.escape(leader_name)}</span>"
        f"<span class='pill'>阶段：{html.escape(_theme_status(leader or {}))}</span>"
        f"<span class='pill'>次强观察：{html.escape(str((runner_up or {}).get('name') or '—'))}</span></p>"
        "<div class='metric-grid'>"
        f"<div><strong>{html.escape(_coverage_text(meta))}</strong><span>数据覆盖</span></div>"
        f"<div><strong>{_fmt_pct((leader or {}).get('avg_week_pct'))}</strong><span>最强主线周均涨幅</span></div>"
        f"<div><strong>{last_breadth.get('limit_down_count', '—')}</strong><span>周五跌停数</span></div>"
        "</div></section>"
    )


def _render_indices(indices: dict[str, Any]) -> str:
    rows = []
    for item in indices.values():
        pct = item.get("week_pct")
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('name') or '—'))}</td>"
            f"<td class='{_pct_class(pct)}'>{_fmt_pct(pct)}</td>"
            f"<td>{html.escape(_daily_path_text(item.get('daily') or []))}</td>"
            "</tr>"
        )
    return "<section class='card'><span class='section-num'>TWO</span><h2>指数与市场情绪</h2><div class='table-wrap'><table><thead><tr><th>指数</th><th>周涨跌</th><th>周内节奏</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>"


def _render_breadth(breadth: dict[str, Any]) -> str:
    rows = []
    for date, item in breadth.items():
        rows.append(
            "<tr>"
            f"<td>{html.escape(date)}</td><td>{item.get('up_count', '—')} / {item.get('down_count', '—')}</td>"
            f"<td>{item.get('limit_up_count', '—')} / {item.get('limit_down_count', '—')}</td>"
            f"<td class='{_pct_class(item.get('median_pct'))}'>{_fmt_pct(item.get('median_pct'))}</td>"
            f"<td>{_fmt_yi(item.get('amount'))}</td>"
            "</tr>"
        )
    return "<section class='card'><h2>市场情绪逐日变化</h2><div class='table-wrap'><table><thead><tr><th>日期</th><th>上涨/下跌</th><th>涨停/跌停</th><th>中位涨跌</th><th>成交额</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>"


def _render_weekly_prediction_review(themes: list[dict[str, Any]], breadth: dict[str, Any]) -> str:
    leader = themes[0] if themes else None
    diverged = _first_theme_with_status(themes, "高位分歧")
    last_item = next(reversed(breadth.values()), {}) if breadth else {}
    rows = [
        (
            "本周是否形成主线",
            "已验证" if leader else "未验证",
            f"{(leader or {}).get('name', '暂无')}处于{_theme_status(leader or {})}",
            _leader_commentary(leader) if leader else "a-stock-data 未返回可排序板块。",
        ),
        (
            "前期强势方向是否还能延续",
            "分化验证" if diverged else "继续跟踪",
            f"{(diverged or {}).get('name', '暂无明显分歧方向')}",
            _divergence_commentary(diverged) if diverged else "本周没有出现周涨为正但周五均幅转负的典型高位分歧方向。",
        ),
        (
            "市场风险是否放大",
            "需要防守" if int(last_item.get("limit_down_count") or 0) >= 10 else "风险可控",
            f"周五涨停/跌停 {last_item.get('limit_up_count', '—')} / {last_item.get('limit_down_count', '—')}",
            f"周五中位涨跌为{_fmt_pct(last_item.get('median_pct'))}，决定下周先看修复还是退潮。",
        ),
    ]
    body = "".join(
        "<tr>"
        f"<td>{html.escape(claim)}</td><td>{html.escape(verdict)}</td>"
        f"<td>{html.escape(actual)}</td><td>{html.escape(evidence)}</td>"
        "</tr>"
        for claim, verdict, actual, evidence in rows
    )
    return (
        "<section class='card'><span class='section-num'>THREE</span><h2>本周预判验证</h2>"
        "<p class='muted'>当前按本周逐日证据回放主线形成、分歧和风险，不用主观猜测替代数据。</p>"
        "<div class='table-wrap'><table><thead><tr><th>验证项</th><th>结论</th><th>实际结果</th><th>证据 / 偏差</th></tr></thead><tbody>"
        + body
        + "</tbody></table></div></section>"
    )


def _render_sector_detail_blocks(themes: list[dict[str, Any]], catalysts: dict[str, list[dict[str, Any]]]) -> str:
    if not themes:
        return "<section class='card'><h2>板块详细分析</h2><p>a-stock-data 未返回可分析板块。</p></section>"
    blocks = []
    for rank, theme in enumerate(themes[:5], 1):
        name = str(theme.get("name") or "—")
        status = _theme_status(theme)
        blocks.append(
            "<article class='sector-block'>"
            f"<h3>{rank}. {html.escape(name)} <span class='pill'>阶段：{html.escape(status)}</span></h3>"
            "<div class='sector-grid'>"
            f"<div class='insight-card'><div class='insight-label'>周内路径</div><p>{html.escape(_theme_weekly_path_text(theme))}</p></div>"
            f"<div class='insight-card'><div class='insight-label'>前排股</div><p>{html.escape(_front_stock_text(theme))}</p></div>"
            f"<div class='insight-card'><div class='insight-label'>资金强度</div><p>{html.escape(_capital_strength_text(theme))}</p></div>"
            f"<div class='insight-card'><div class='insight-label'>催化逻辑</div><p>{html.escape(_catalyst_logic_text(name, catalysts.get(name, [])))}</p></div>"
            f"<div class='insight-card'><div class='insight-label'>下周条件 / 下周观察条件</div><p>{html.escape(_next_week_condition(theme))}</p></div>"
            f"<div class='insight-card'><div class='insight-label'>结论</div><p>{html.escape(_sector_weekly_conclusion(theme))}</p></div>"
            "</div></article>"
        )
    return "<section class='card'><span class='section-num'>FOUR</span><h2>板块详细分析</h2>" + "".join(blocks) + "</section>"


def _render_capital_rotation(themes: list[dict[str, Any]]) -> str:
    if not themes:
        return "<section class='card'><h2>资金轮动路径</h2><p>缺少板块排序，无法判断资金轮动。</p></section>"
    path = [f"{theme['name']}（{_theme_status(theme)}）" for theme in themes[:4]]
    finding = _capital_rotation_finding(themes)
    return (
        "<section class='card'><span class='section-num'>5</span><h2>资金轮动路径</h2>"
        "<div class='path-flow'>"
        + "".join(
            f"<span class='path-node'>{html.escape(item)}</span>"
            + ("" if index == len(path) - 1 else "<span class='path-arrow'>→</span>")
            for index, item in enumerate(path)
        )
        + "</div>"
        f"<div class='conclusion-box'><strong>轮动判断：</strong>{html.escape(finding)}</div></section>"
    )


def _render_sustainability_ranking(themes: list[dict[str, Any]]) -> str:
    rows = []
    for rank, theme in enumerate(themes[:8], 1):
        rows.append(
            "<tr>"
            f"<td>{rank}</td><td><strong>{html.escape(theme['name'])}</strong></td>"
            f"<td>{html.escape(_sustainability_rating(theme))}</td>"
            f"<td>{html.escape(_theme_status(theme))}</td>"
            f"<td style='text-align:left;'>{html.escape(_sustainability_reason(theme))}</td>"
            "</tr>"
        )
    return "<section class='card'><span class='section-num'>6</span><h2>板块持续性排序</h2><div class='table-wrap'><table><thead><tr><th>排序</th><th>方向</th><th>评级</th><th>阶段</th><th>核心理由</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>"


def _render_next_week_strategy(themes: list[dict[str, Any]], last_breadth: dict[str, Any]) -> str:
    leader = themes[0] if themes else None
    runner_up = themes[1] if len(themes) > 1 else None
    weak_names = [
        theme["name"]
        for theme in themes
        if _theme_status(theme) in {"高位分歧", "弱势退潮"}
    ][:2]
    risk = int(last_breadth.get("limit_down_count") or 0)
    focus = _front_stock_text(leader) if leader else "等待明确前排"
    observe = f"{runner_up['name']}能否放量修复并出现前排扩散" if runner_up else "观察是否出现新轮动方向"
    avoid = "、".join(weak_names) if weak_names else "后排无量补涨"
    return (
        "<section class='card'><span class='section-num'>7</span><h2>下周操作思路</h2>"
        "<div class='sector-grid'>"
        f"<div class='insight-card'><div class='insight-label'>重点关注</div><p>{html.escape(str((leader or {}).get('name') or '暂无主线'))}：{html.escape(focus)}，只看分歧承接。</p></div>"
        f"<div class='insight-card'><div class='insight-label'>谨慎观察</div><p>{html.escape(observe)}。</p></div>"
        f"<div class='insight-card'><div class='insight-label'>规避方向</div><p>{html.escape(avoid)}不做主线预设，除非重新放量转强。</p></div>"
        f"<div class='insight-card'><div class='insight-label'>失效条件</div><p>周五跌停数基准为{risk}只；若下周继续放大，前排集体低开低走，按退潮处理。</p></div>"
        "</div></section>"
    )


def _render_weekend_news(themes: list[dict[str, Any]], catalysts: dict[str, list[dict[str, Any]]]) -> str:
    rows = []
    for theme in themes[:5]:
        name = str(theme.get("name") or "—")
        rows.append(
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{html.escape(_catalyst_logic_text(name, catalysts.get(name, [])))}</td>"
            f"<td>{html.escape(_next_week_condition(theme))}</td>"
            "</tr>"
        )
    return "<section class='card'><span class='section-num'>8</span><h2>周末 / 下周消息梳理</h2><div class='table-wrap'><table><thead><tr><th>方向</th><th>已验证催化</th><th>下周验证点</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>"


def _render_weekly_stock_ranking(themes: list[dict[str, Any]]) -> str:
    leader = themes[0] if themes else None
    keep = _clean_stocks((leader or {}).get("top_week", []))[:5]
    switch = []
    for theme in themes[1:]:
        if _theme_status(theme) in {"高位分歧", "弱势退潮", "低位修复"}:
            switch.extend(_clean_stocks(theme.get("top_week", []))[:2])
    keep_items = "".join(f"<li class='pos'>{html.escape(_stock_line(stock))}</li>" for stock in keep) or "<li>暂无可保留标的。</li>"
    switch_items = "".join(f"<li>{html.escape(_stock_line(stock))}</li>" for stock in switch[:6]) or "<li>暂无明确换弱标的，继续按板块强弱排序观察。</li>"
    return (
        "<section class='card'><span class='section-num'>9</span><h2>去弱留强排序</h2>"
        "<div class='conclusion-box'><strong>优先保留 / 加仓观察：</strong><ul class='note-list'>"
        + keep_items
        + "</ul></div><div class='avoid-box' style='margin-top:12px;'><strong>优先换弱 / 降低预期：</strong><ul class='note-list'>"
        + switch_items
        + "</ul></div></section>"
    )


def _render_practical_conclusion(themes: list[dict[str, Any]], last_breadth: dict[str, Any]) -> str:
    leader = themes[0] if themes else None
    leader_name = str((leader or {}).get("name") or "暂无主线")
    risk = int(last_breadth.get("limit_down_count") or 0)
    points = [
        f"第一观察仍是{leader_name}，但只做前排分歧承接，不追后排补涨。",
        "高位分歧方向必须等前排反包和成交回流同时出现，否则只按修复看。",
        f"若跌停数从{risk}继续放大，降低仓位与预期，等待新强势方向重新确认。",
    ]
    return (
        "<section class='card'><span class='section-num'>10</span><h2>最实战的结论</h2>"
        f"<div class='conclusion-box'><strong>一句话：</strong>{html.escape(_practical_headline(leader))}</div>"
        "<ol class='note-list'>"
        + "".join(f"<li>{html.escape(point)}</li>" for point in points)
        + "</ol></section>"
    )


def _render_index_mid_term(indices: dict[str, Any], breadth: dict[str, Any]) -> str:
    shanghai = indices.get("000001.SH") or next(
        (item for item in indices.values() if str(item.get("name") or "").startswith("上证")),
        None,
    )
    breadth_values = list(breadth.values())
    last = breadth_values[-1] if breadth_values else {}
    scenario_rows = [
        ("放量修复", "指数止跌且上涨家数恢复到多数", "围绕主线前排做去弱留强"),
        ("震荡分化", "指数横盘但板块轮动加快", "只看资金强度最高的方向"),
        ("退潮下杀", "跌停数继续扩大且中位数走弱", "降低仓位，等待新主线确认"),
    ]
    rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{html.escape(condition)}</td><td>{html.escape(response)}</td></tr>"
        for name, condition, response in scenario_rows
    )
    current = (
        f"{shanghai.get('name')}本周{_fmt_pct(shanghai.get('week_pct'))}，周内节奏：{_daily_path_text(shanghai.get('daily') or [])}。"
        if shanghai
        else "a-stock-data 未返回上证指数周线数据。"
    )
    current += f" 周五市场中位涨跌为{_fmt_pct(last.get('median_pct'))}，用于判断指数修复质量。"
    return (
        "<section class='card'><span class='section-num'>11</span><h2>指数中期走势研判</h2>"
        f"<p>{html.escape(current)}</p>"
        "<div class='table-wrap'><table><thead><tr><th>情景</th><th>条件</th><th>应对</th></tr></thead><tbody>"
        + rows
        + "</tbody></table></div></section>"
    )


def _render_source_notes() -> str:
    return (
        "<section class='card'><h2>数据源说明</h2>"
        "<p class='source-note'>本周报主数据来自 a-stock-data 行情、K 线、成交额和换手率；Anspire 仅用于新闻催化补充。"
        "未使用模拟内容；若某只股票无历史 K 线，则仅计入覆盖率缺口。</p></section>"
    )


def _rank_weekly_themes(theme_stats: dict[str, Any]) -> list[dict[str, Any]]:
    themes = []
    for name, payload in theme_stats.items():
        if not isinstance(payload, dict):
            continue
        item = dict(payload)
        item["name"] = name
        item["strength_score"] = _theme_strength_score(item)
        themes.append(item)
    return sorted(
        themes,
        key=lambda item: (
            item.get("strength_score") if item.get("strength_score") is not None else -999,
            item.get("avg_week_pct") if item.get("avg_week_pct") is not None else -999,
        ),
        reverse=True,
    )


def _theme_strength_score(theme: dict[str, Any]) -> float:
    front_week = _average(
        [
            stock.get("week_pct")
            for stock in _clean_stocks(theme.get("top_week", []))[:5]
        ]
    )
    front_friday = _average(
        [
            stock.get("friday_pct_from_kline")
            for stock in _clean_stocks(theme.get("top_friday", []))[:5]
        ]
    )
    average_week = _as_float(theme.get("avg_week_pct")) or 0.0
    average_friday = _as_float(theme.get("friday_avg_pct")) or 0.0
    limit_up_score = min(float(theme.get("limit_up_days_sum") or 0), 30.0)
    amount_score = min(float(theme.get("amount_sum") or 0) / 100_000_000 / 500, 10.0)
    return (
        front_week * 0.42
        + front_friday * 0.22
        + average_week * 0.18
        + average_friday * 0.08
        + limit_up_score * 0.45
        + amount_score * 0.35
    )


def _average(values: list[object]) -> float:
    numbers = [number for value in values if (number := _as_float(value)) is not None]
    return sum(numbers) / len(numbers) if numbers else 0.0


def _as_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_theme_stats(stocks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for theme_name in WEEKLY_THEMES:
        members = [stock for stock in stocks if _matches_theme(stock, theme_name)]
        week_values = [stock["week_pct"] for stock in members if stock.get("week_pct") is not None]
        friday_values = [
            stock["friday_pct_from_kline"]
            for stock in members
            if stock.get("friday_pct_from_kline") is not None
        ]
        if not week_values:
            continue
        stats[theme_name] = {
            "member_count": len(members),
            "avg_week_pct": sum(week_values) / len(week_values),
            "median_week_pct": sorted(week_values)[len(week_values) // 2],
            "friday_avg_pct": sum(friday_values) / len(friday_values) if friday_values else None,
            "limit_up_days_sum": sum(stock.get("limit_up_days") or 0 for stock in members),
            "amount_sum": sum(stock.get("amount_sum") or 0 for stock in members),
            "top_week": _clean_stocks(
                sorted(
                    members,
                    key=lambda stock: stock.get("week_pct")
                    if stock.get("week_pct") is not None
                    else -999,
                    reverse=True,
                )
            )[:15],
            "top_friday": _clean_stocks(
                sorted(
                    members,
                    key=lambda stock: stock.get("friday_pct_from_kline")
                    if stock.get("friday_pct_from_kline") is not None
                    else -999,
                    reverse=True,
                )
            )[:10],
        }
    return stats


def _build_breadth(stocks: list[dict[str, Any]], trading_dates: list[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for date in trading_dates:
        values = []
        amounts = []
        for stock in stocks:
            daily = next((item for item in stock.get("daily", []) if item.get("date") == date), None)
            if daily and daily.get("pct") is not None:
                values.append(daily["pct"])
                amounts.append(daily.get("amount") or 0)
        output[date] = {
            "count": len(values),
            "up_count": sum(1 for value in values if value > 0),
            "down_count": sum(1 for value in values if value < 0),
            "limit_up_count": sum(1 for value in values if value >= 9.8),
            "limit_down_count": sum(1 for value in values if value <= -9.8),
            "amount": sum(amounts),
            "median_pct": sorted(values)[len(values) // 2] if values else None,
        }
    return output


def _compact_kline(
    symbol: str,
    data: dict[str, Any],
    trading_dates: list[str],
    name: str | None = None,
    realtime: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    timestamps = data.get("timestamp") or []
    rows = []
    for index, timestamp in enumerate(timestamps):
        date = datetime.fromtimestamp(timestamp / 1000, tz=CHINA_TZ).date().isoformat()
        if date not in trading_dates:
            continue
        row = {
            "date": date,
            "open": _list_float(data, "open", index),
            "close": _list_float(data, "close", index),
            "amount": _list_float(data, "amount", index),
            "volume": _list_float(data, "volume", index),
        }
        if row["open"] is not None and row["close"] is not None:
            rows.append(row)
    if not rows:
        return None
    rows.sort(key=lambda item: item["date"])
    previous_close = None
    daily = []
    for row in rows:
        change = _pct(previous_close, row["close"]) if previous_close else _pct(row["open"], row["close"])
        daily.append(
            {
                "date": row["date"],
                "pct": change,
                "amount": row["amount"],
                "close": row["close"],
            }
        )
        previous_close = row["close"]
    ext = (realtime or {}).get("ext") or {}
    turnover_rate = ext.get("turnover_rate")
    return {
        "symbol": symbol,
        "name": name or ext.get("name") or symbol,
        "week_pct": _pct(rows[0]["open"], rows[-1]["close"]),
        "max_daily_pct": max((item["pct"] for item in daily if item.get("pct") is not None), default=None),
        "limit_up_days": sum(1 for item in daily if item.get("pct") is not None and item["pct"] >= 9.8),
        "amount_sum": sum(row.get("amount") or 0 for row in rows),
        "friday_amount": rows[-1].get("amount"),
        "friday_pct_from_kline": daily[-1].get("pct") if daily else None,
        "turnover_rate": float(turnover_rate) * 100 if turnover_rate is not None else None,
        "daily": daily,
    }


def _baidu_kline_payload_to_tickflow_shape(payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    result = payload.get("Result")
    if not isinstance(result, dict):
        return None
    market_data = result.get("newMarketData")
    if not isinstance(market_data, dict):
        return None
    keys = market_data.get("keys") or []
    rows_text = str(market_data.get("marketData") or "")
    if not isinstance(keys, list) or not rows_text:
        return None
    output = {
        "timestamp": [],
        "open": [],
        "close": [],
        "high": [],
        "low": [],
        "volume": [],
        "amount": [],
    }
    for row in rows_text.split(";"):
        if not row.strip():
            continue
        values = row.split(",")
        data = {str(key): values[index] for index, key in enumerate(keys) if index < len(values)}
        date_value = str(data.get("time") or data.get("date") or "")
        if not date_value:
            continue
        try:
            timestamp = int(
                datetime.fromisoformat(f"{date_value}T00:00:00")
                .replace(tzinfo=CHINA_TZ)
                .timestamp()
                * 1000
            )
        except ValueError:
            continue
        output["timestamp"].append(timestamp)
        output["open"].append(_field_float(data, "open"))
        output["close"].append(_field_float(data, "close"))
        output["high"].append(_field_float(data, "high"))
        output["low"].append(_field_float(data, "low"))
        output["volume"].append(_field_float(data, "volume"))
        output["amount"].append(_field_float(data, "amount"))
    return output if output["timestamp"] else None


def _trading_dates_from_klines(klines: dict[str, Any], start_date: str, end_date: str) -> list[str]:
    dates: set[str] = set()
    for data in klines.values():
        for timestamp in data.get("timestamp") or []:
            date = datetime.fromtimestamp(timestamp / 1000, tz=CHINA_TZ).date().isoformat()
            if start_date <= date <= end_date:
                dates.add(date)
    return sorted(dates)


def _matches_theme(stock: dict[str, Any], theme_name: str) -> bool:
    name = str(stock.get("name") or "")
    return any(keyword in name for keyword in WEEKLY_THEMES[theme_name])


def _clean_stocks(stocks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        stock
        for stock in stocks
        if stock.get("name")
        and "ST" not in str(stock.get("name")).upper()
        and not str(stock.get("symbol", "")).endswith(".BJ")
    ]


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _date_to_ms(date: str) -> int:
    return int(datetime.fromisoformat(f"{date}T00:00:00").replace(tzinfo=CHINA_TZ).timestamp() * 1000)


def _next_day(date: str) -> str:
    return (datetime.fromisoformat(date) + timedelta(days=1)).date().isoformat()


def _pct(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or start == 0:
        return None
    return (end / start - 1) * 100


def _list_float(data: dict[str, Any], key: str, index: int) -> float | None:
    values = data.get(key) or []
    if index >= len(values):
        return None
    try:
        value = float(values[index])
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def _field_float(data: dict[str, str], key: str) -> float | None:
    try:
        value = float(data.get(key, ""))
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def _rate_limit_wait_seconds(raw: str, attempt: int) -> float:
    match = re.search(r"请\s*(\d+)ms\s*后重试", raw)
    if match:
        return int(match.group(1)) / 1000 + 1
    return min(65, 10 * (attempt + 1))


def _news_item_to_dict(item: object) -> dict[str, Any]:
    dump = getattr(item, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    return {
        "title": getattr(item, "title", "新闻线索"),
        "summary": getattr(item, "summary", ""),
        "url": getattr(item, "url", ""),
        "source": getattr(item, "source", None),
    }


def _coverage_text(meta: dict[str, Any]) -> str:
    source = str(meta.get("source") or "a-stock-data")
    return f"{source} 覆盖 {meta.get('stock_rows', 0)}/{meta.get('symbol_count', 0)} 只"


def _core_conclusion(leader: dict[str, Any] | None, breadth: dict[str, Any]) -> str:
    if not leader:
        return "本周未形成可验证主线，先等待数据源恢复。"
    risk = breadth.get("limit_down_count")
    return (
        f"本周最强主线是{leader['name']}，但周五跌停数达到{risk}只，说明市场处于强主线与退潮风险并存的状态。"
    )


def _leader_commentary(leader: dict[str, Any]) -> str:
    return (
        f"{leader['name']}周均涨幅{_fmt_pct(leader.get('avg_week_pct'))}，周五均幅{_fmt_pct(leader.get('friday_avg_pct'))}，"
        f"涨停天数合计{leader.get('limit_up_days_sum', 0)}，是本周最需要继续跟踪的方向。"
    )


def _divergence_commentary(theme: dict[str, Any]) -> str:
    return (
        f"{theme['name']}周均涨幅{_fmt_pct(theme.get('avg_week_pct'))}，周五均幅{_fmt_pct(theme.get('friday_avg_pct'))}。"
        "若下周没有前排反包和成交额回流，只按修复或轮动看。"
    )


def _theme_status(theme: dict[str, Any]) -> str:
    week = theme.get("avg_week_pct") or 0
    friday = theme.get("friday_avg_pct") or 0
    if week > 0 and friday > 0:
        return "主线延续"
    if week > 0 and friday < 0:
        return "高位分歧"
    if week < 0 and friday > 0:
        return "低位修复"
    return "弱势退潮"


def _first_theme_with_status(themes: list[dict[str, Any]], status: str) -> dict[str, Any] | None:
    return next((theme for theme in themes if _theme_status(theme) == status), None)


def _theme_weekly_path_text(theme: dict[str, Any]) -> str:
    stocks = _clean_stocks(theme.get("top_week", []))
    top_stock = stocks[0] if stocks else None
    if top_stock and top_stock.get("daily"):
        return (
            f"板块周均{_fmt_pct(theme.get('avg_week_pct'))}，周五均幅{_fmt_pct(theme.get('friday_avg_pct'))}；"
            f"前排{top_stock.get('name')}路径：{_daily_path_text(top_stock.get('daily') or [])}。"
        )
    return (
        f"板块周均{_fmt_pct(theme.get('avg_week_pct'))}，周五均幅{_fmt_pct(theme.get('friday_avg_pct'))}，"
        f"涨停天数合计{theme.get('limit_up_days_sum', 0)}。"
    )


def _front_stock_text(theme: dict[str, Any] | None) -> str:
    if not theme:
        return "暂无明确前排股"
    stocks = _clean_stocks(theme.get("top_week", []))[:4]
    if not stocks:
        return "暂无明确前排股"
    return "、".join(
        f"{stock.get('name')}({stock.get('symbol')}) 周{_fmt_pct(stock.get('week_pct'))}"
        for stock in stocks
    )


def _capital_strength_text(theme: dict[str, Any]) -> str:
    front = _clean_stocks(theme.get("top_week", []))[:5]
    turnover = _average([stock.get("turnover_rate") for stock in front])
    return (
        f"板块周成交{_fmt_yi(theme.get('amount_sum'))}，前排平均换手{_fmt_pct(turnover)}，"
        f"涨停天数合计{theme.get('limit_up_days_sum', 0)}；资金强度评级{_sustainability_rating(theme)}。"
    )


def _catalyst_logic_text(theme_name: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return "暂无 Anspire 可验证增量新闻，先按价格、成交额、换手率验证。"
    summaries = []
    for item in items[:2]:
        title = str(item.get("title") or theme_name)
        summary = _short_text(str(item.get("summary") or ""), 56)
        summaries.append(f"{title}：{summary}" if summary else title)
    return "；".join(summaries)


def _next_week_condition(theme: dict[str, Any]) -> str:
    status = _theme_status(theme)
    name = str(theme.get("name") or "该方向")
    front = _front_stock_text(theme)
    if status == "主线延续":
        return f"{name}下周必须看到前排继续强于板块平均，核心观察：{front}。"
    if status == "高位分歧":
        return f"{name}需要前排反包、成交额回流、周五弱势股止跌同时出现，否则只按修复看。"
    if status == "低位修复":
        return f"{name}先看一到两只前排是否打出持续性，再判断能否从修复变成新主线。"
    return f"{name}当前不做主线预设，除非出现放量涨停前排和板块扩散。"


def _sector_weekly_conclusion(theme: dict[str, Any]) -> str:
    status = _theme_status(theme)
    if status == "主线延续":
        return f"{theme['name']}是本周需要优先跟踪的方向，但买点只能来自分歧承接。"
    if status == "高位分歧":
        return f"{theme['name']}本周有强势基础，但周五资金松动，下周先看修复质量。"
    if status == "低位修复":
        return f"{theme['name']}属于低位修复观察，不能提前按主线处理。"
    return f"{theme['name']}处于弱势退潮，暂时回避后排反抽。"


def _capital_rotation_finding(themes: list[dict[str, Any]]) -> str:
    leader = themes[0]
    diverged = _first_theme_with_status(themes, "高位分歧")
    if diverged:
        return (
            f"资金本周优先选择{leader['name']}，同时{diverged['name']}出现高位分歧，"
            "下周关键是主线承接能否覆盖分歧方向的流出。"
        )
    if len(themes) > 1:
        return f"资金集中在{leader['name']}，并向{themes[1]['name']}做轮动扩散。"
    return f"资金集中在{leader['name']}，尚未看到明确扩散方向。"


def _sustainability_rating(theme: dict[str, Any]) -> str:
    status = _theme_status(theme)
    score = _as_float(theme.get("strength_score")) or 0
    limit_up_days = int(theme.get("limit_up_days_sum") or 0)
    if status == "主线延续" and (score >= 18 or limit_up_days >= 3):
        return "高"
    if status in {"主线延续", "高位分歧", "低位修复"}:
        return "中"
    return "低"


def _sustainability_reason(theme: dict[str, Any]) -> str:
    return (
        f"阶段{_theme_status(theme)}，周均{_fmt_pct(theme.get('avg_week_pct'))}，"
        f"周五均幅{_fmt_pct(theme.get('friday_avg_pct'))}，前排资金强度看{_capital_strength_text(theme)}"
    )


def _stock_line(stock: dict[str, Any]) -> str:
    return (
        f"{stock.get('name')} {stock.get('symbol')}：周{_fmt_pct(stock.get('week_pct'))}，"
        f"周五{_fmt_pct(stock.get('friday_pct_from_kline'))}，换手{_fmt_pct(stock.get('turnover_rate'))}"
    )


def _practical_headline(leader: dict[str, Any] | None) -> str:
    if not leader:
        return "没有明确主线时不硬做，等待资金重新投票。"
    return f"下周围绕{leader['name']}去弱留强，先看前排分歧承接，再决定是否扩大战果。"


def _daily_path_text(daily: list[dict[str, Any]]) -> str:
    return " / ".join(f"{item.get('date', '')[-5:]} {_fmt_pct(item.get('pct'))}" for item in daily)


def _fmt_pct(value: object) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:+.2f}%"


def _fmt_yi(value: object) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) / 100_000_000:.1f}亿"
    except (TypeError, ValueError):
        return "—"


def _pct_class(value: object) -> str:
    try:
        return "pos" if float(value) >= 0 else "neg"
    except (TypeError, ValueError):
        return ""


def _short_text(value: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized if len(normalized) <= limit else normalized[:limit] + "…"
