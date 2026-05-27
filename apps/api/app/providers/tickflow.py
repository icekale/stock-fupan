from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from app.providers.market import MarketBreadth, MarketCloseSnapshot, ProviderFallbackError, ProviderStatus
from app.rules.scoring import RawSectorInput
from app.schemas.report import IndexSnapshot


DEFAULT_MARKET_SYMBOLS = ["600000.SH", "000001.SZ", "300750.SZ", "002594.SZ", "601318.SH"]
INDEX_SYMBOLS = ["000001.SH", "399006.SZ"]
FULL_MARKET_UNIVERSE = "CN_Equity_A"
INDUSTRY_UNIVERSE_PREFIX = "CN_Equity_SW3_"
TOP_STRONG_QUOTES = 80
MIN_STRONG_QUOTE_PCT = 5.0
MAX_INDUSTRY_DETAIL_REQUESTS = 40
THEME_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PCB", ("生益", "沪电", "胜宏", "景旺", "深南", "鹏鼎", "东山", "世运", "方正科技")),
    ("半导体", ("芯", "半导体", "晶", "微", "封测", "长电", "通富", "华天", "中芯")),
    ("新材料", ("新材", "材料", "纳米", "复材", "碳", "膜")),
    ("环保", ("环保", "复洁", "清源", "水务", "节能", "固废")),
    ("机器人", ("机器人", "智能", "自动化", "精工", "机电", "伺服")),
    ("有色金属", ("黄金", "铜", "铝", "钴", "锂", "钼", "稀土", "有色", "贵金属")),
    ("电力设备", ("输变电", "电网", "特锐德", "思源电气", "中国西电", "金盘科技", "三变科技")),
    ("电力", ("电力", "电网", "能源", "发电", "核电", "风电")),
)


class WatchlistQuote(BaseModel):
    symbol: str
    name: str | None = None
    last_price: float | None = None
    pct_change: float | None = None
    turnover_cny: float | None = None
    volume: float | None = None
    quote_time: str | None = None


@dataclass(frozen=True)
class IndustryUniverse:
    universe_id: str
    name: str
    symbol_count: int
    symbols: tuple[str, ...] = ()


class TickFlowQuoteProvider(Protocol):
    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        raise NotImplementedError


class FakeTickFlowProvider:
    provider_name = "fake_tickflow"

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        fake_names = {"600000.SH": "浦发银行", "000001.SZ": "平安银行", "300750.SZ": "宁德时代"}
        return [
            WatchlistQuote(
                symbol=symbol,
                name=fake_names.get(symbol),
                last_price=10.0 + index,
                pct_change=2.5 - index,
                turnover_cny=100000000 + index * 1000000,
                volume=10000 + index,
                quote_time="2026-05-26T15:00:00+08:00",
            )
            for index, symbol in enumerate(symbols)
        ]


class TickFlowProvider:
    provider_name = "tickflow"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 12,
        http_client: object | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        if not symbols:
            return []
        if not self.api_key:
            raise ProviderFallbackError("TICKFLOW_API_KEY 未配置")
        try:
            response = self.http_client.post(
                f"{self.base_url}/v1/quotes",
                headers={"x-api-key": self.api_key},
                json={"symbols": symbols},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderFallbackError("TickFlow 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            raise ProviderFallbackError(_safe_status_error(status_code)) from exc
        except Exception as exc:
            raise ProviderFallbackError(f"TickFlow 请求失败: {exc.__class__.__name__}") from exc
        return [_quote_from_item(item) for item in _extract_items(payload)]

    def get_universe_quotes(self, universe_id: str) -> list[WatchlistQuote]:
        if not self.api_key:
            raise ProviderFallbackError("TICKFLOW_API_KEY 未配置")
        try:
            response = self.http_client.get(
                f"{self.base_url}/v1/quotes",
                headers={"x-api-key": self.api_key},
                params={"universes": universe_id},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderFallbackError("TickFlow 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            raise ProviderFallbackError(_safe_status_error(status_code)) from exc
        except Exception as exc:
            raise ProviderFallbackError(f"TickFlow 请求失败: {exc.__class__.__name__}") from exc
        return [_quote_from_item(item) for item in _extract_items(payload)]

    def get_industry_universes(self) -> list[IndustryUniverse]:
        if not self.api_key:
            raise ProviderFallbackError("TICKFLOW_API_KEY 未配置")
        try:
            response = self.http_client.get(
                f"{self.base_url}/v1/universes",
                headers={"x-api-key": self.api_key},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderFallbackError("TickFlow 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            raise ProviderFallbackError(_safe_status_error(status_code)) from exc
        except Exception as exc:
            raise ProviderFallbackError(f"TickFlow 请求失败: {exc.__class__.__name__}") from exc
        return _industry_universes_from_items(_extract_items(payload))

    def get_universe(self, universe_id: str) -> IndustryUniverse:
        if not self.api_key:
            raise ProviderFallbackError("TICKFLOW_API_KEY 未配置")
        try:
            response = self.http_client.get(
                f"{self.base_url}/v1/universes/{universe_id}",
                headers={"x-api-key": self.api_key},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderFallbackError("TickFlow 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            raise ProviderFallbackError(_safe_status_error(status_code)) from exc
        except Exception as exc:
            raise ProviderFallbackError(f"TickFlow 请求失败: {exc.__class__.__name__}") from exc
        item = _extract_single_item(payload)
        return _industry_universe_from_item(item)


class TickFlowMarketDataProvider:
    provider_name = "tickflow"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        symbols: list[str] | None = None,
        timeout_seconds: float = 12,
        http_client: object | None = None,
    ) -> None:
        self.quote_provider = TickFlowProvider(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )
        self.symbols = symbols or DEFAULT_MARKET_SYMBOLS
        self._sector_frontline_stocks: dict[str, list[WatchlistQuote]] = {}

    def close(self) -> None:
        self.quote_provider.close()

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        market_quotes = self.quote_provider.get_universe_quotes(FULL_MARKET_UNIVERSE)
        indices = _indices_from_quotes(market_quotes)
        if len(indices) < len(INDEX_SYMBOLS):
            indices = _indices_from_quotes([*market_quotes, *self.quote_provider.get_quotes(INDEX_SYMBOLS)])
        equity_quotes = _tradable_equity_quotes(market_quotes)
        quoted_changes = [quote.pct_change for quote in equity_quotes if quote.pct_change is not None]
        if not indices or not quoted_changes:
            raise ProviderFallbackError("TickFlow 行情数据不足")
        turnover_cny = round(
            sum(quote.turnover_cny or 0 for quote in equity_quotes) / 100_000_000,
            2,
        )
        raw_sectors = self._strong_sectors_from_market(equity_quotes)
        if not raw_sectors:
            raise ProviderFallbackError("TickFlow 未返回可排序标的")
        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=indices,
            breadth=MarketBreadth(
                up_count=sum(1 for change in quoted_changes if change > 0),
                down_count=sum(1 for change in quoted_changes if change < 0),
                limit_up_count=sum(1 for change in quoted_changes if change >= 9.8),
                limit_down_count=sum(1 for change in quoted_changes if change <= -9.8),
            ),
            turnover_cny=turnover_cny,
            market_state_tags=_market_tags(quoted_changes, turnover_cny),
            raw_sectors=raw_sectors,
        )

    def get_sector_frontline_stocks(self, sector_name: str) -> list[WatchlistQuote]:
        return list(self._sector_frontline_stocks.get(sector_name, []))

    def _strong_sectors_from_market(self, equity_quotes: list[WatchlistQuote]) -> list[RawSectorInput]:
        self._sector_frontline_stocks = {}
        strong_quotes = _strong_quotes(equity_quotes, top_n=TOP_STRONG_QUOTES)
        themed = _sectors_from_theme_quotes(strong_quotes)
        self._sector_frontline_stocks = _frontline_stocks_from_theme_quotes(strong_quotes)
        industry_theme_quotes = self._refine_theme_frontline_stocks_with_industries(
            equity_quotes,
            strong_quotes,
        )
        if themed and industry_theme_quotes:
            themed = _replace_theme_sectors_with_industry_quotes(themed, industry_theme_quotes)
        return themed or _sectors_from_quotes(strong_quotes)

    def _refine_theme_frontline_stocks_with_industries(
        self,
        equity_quotes: list[WatchlistQuote],
        strong_quotes: list[WatchlistQuote],
    ) -> dict[str, list[WatchlistQuote]]:
        industries = self._matching_industries_for_quotes(strong_quotes)
        if not industries:
            return {}
        industry_frontline = _frontline_stocks_from_industry_members(
            equity_quotes,
            industries,
        )
        industry_theme_quotes: dict[str, list[WatchlistQuote]] = {}
        for theme, theme_industries in _industries_by_theme(industries).items():
            quotes = [
                quote
                for industry in theme_industries
                for quote in industry_frontline.get(industry.name, [])
            ]
            if quotes:
                ranked = _rank_frontline_stocks(quotes)
                self._sector_frontline_stocks[theme] = ranked
                industry_theme_quotes[theme] = ranked
        return industry_theme_quotes

    def _matching_industries_for_quotes(
        self,
        quotes: list[WatchlistQuote],
    ) -> list[IndustryUniverse]:
        strong_symbols = {quote.symbol for quote in quotes}
        if not strong_symbols:
            return []
        try:
            candidates = self.quote_provider.get_industry_universes()
        except Exception:
            return []
        detailed: list[IndustryUniverse] = []
        for industry in candidates[:MAX_INDUSTRY_DETAIL_REQUESTS]:
            try:
                detail = industry if industry.symbols else self.quote_provider.get_universe(industry.universe_id)
            except Exception:
                continue
            if set(detail.symbols).intersection(strong_symbols):
                detailed.append(detail)
        return detailed


class FallbackTickFlowProvider:
    def __init__(
        self,
        primary: TickFlowQuoteProvider,
        fallback: TickFlowQuoteProvider,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        quotes, _status = self.get_quotes_with_status(symbols)
        return quotes

    def get_quotes_with_status(self, symbols: list[str]) -> tuple[list[WatchlistQuote], ProviderStatus]:
        try:
            quotes = self.primary.get_quotes(symbols)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            if not self.fallback_enabled:
                raise
            return self.fallback.get_quotes(symbols), ProviderStatus(
                provider="tickflow",
                status="fallback",
                fallback_used=True,
                reason=reason,
            )
        return quotes, ProviderStatus(
            provider="tickflow",
            status="success",
            fallback_used=False,
            reason=None,
        )


def _extract_items(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if "data" in payload:
            data = payload["data"]
        elif "items" in payload:
            data = payload["items"]
        else:
            data = payload.get("results")
    else:
        data = payload
    if not isinstance(data, list):
        raise ProviderFallbackError("TickFlow 响应结构异常")
    return [item for item in data if isinstance(item, dict)]


def _extract_single_item(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict):
        if "data" in payload:
            data = payload["data"]
        elif "item" in payload:
            data = payload["item"]
        else:
            data = payload
    else:
        data = payload
    if not isinstance(data, dict):
        raise ProviderFallbackError("TickFlow 响应结构异常")
    return data


def _industry_universes_from_items(items: list[dict[str, Any]]) -> list[IndustryUniverse]:
    return [
        _industry_universe_from_item(item)
        for item in items
        if str(item.get("id") or "").startswith(INDUSTRY_UNIVERSE_PREFIX)
    ]


def _industry_universe_from_item(item: dict[str, Any]) -> IndustryUniverse:
    universe_id = str(item.get("id") or "")
    name = _clean_industry_name(str(item.get("name") or item.get("description") or universe_id))
    symbol_count = int(_optional_float(item.get("symbol_count")) or 0)
    symbols = tuple(str(symbol) for symbol in item.get("symbols", []) if symbol)
    return IndustryUniverse(
        universe_id=universe_id,
        name=name,
        symbol_count=symbol_count,
        symbols=symbols,
    )


def _quote_from_item(item: dict[str, Any]) -> WatchlistQuote:
    symbol = str(item.get("symbol") or item.get("ticker") or item.get("code") or "")
    if not symbol:
        raise ProviderFallbackError("TickFlow 响应缺少 symbol")
    ext = item.get("ext")
    ext_item = ext if isinstance(ext, dict) else {}
    change_pct = (
        item.get("pct_change")
        or item.get("change_percent")
        or item.get("percent")
        or ext_item.get("change_pct")
    )
    pct_change = _optional_float(change_pct)
    if pct_change is not None and abs(pct_change) <= 1:
        pct_change = pct_change * 100
    return WatchlistQuote(
        symbol=symbol,
        name=_optional_str(item.get("name") or ext_item.get("name")),
        last_price=_optional_float(item.get("last_price") or item.get("price") or item.get("last")),
        pct_change=pct_change,
        turnover_cny=_optional_float(item.get("turnover_cny") or item.get("turnover") or item.get("amount")),
        volume=_optional_float(item.get("volume")),
        quote_time=_optional_str(item.get("quote_time") or item.get("time") or item.get("timestamp")),
    )


def _indices_from_quotes(quotes: list[WatchlistQuote]) -> list[IndexSnapshot]:
    index_names = {"000001.SH": "上证指数", "399006.SZ": "创业板指"}
    results: list[IndexSnapshot] = []
    for quote in quotes:
        if quote.symbol not in index_names or quote.last_price is None or quote.pct_change is None:
            continue
        results.append(
            IndexSnapshot(
                name=quote.name or index_names[quote.symbol],
                code=quote.symbol.split(".")[0],
                close=quote.last_price,
                pct_change=quote.pct_change,
            )
        )
    return results


def _tradable_equity_quotes(quotes: list[WatchlistQuote]) -> list[WatchlistQuote]:
    return [
        quote
        for quote in quotes
        if quote.symbol not in set(INDEX_SYMBOLS)
        and quote.pct_change is not None
        and quote.turnover_cny is not None
        and _is_mainland_regular_equity(quote)
    ]


def _is_mainland_regular_equity(quote: WatchlistQuote) -> bool:
    if quote.symbol.endswith(".BJ"):
        return False
    name = quote.name or ""
    return "ST" not in name.upper()


def _strong_quotes(quotes: list[WatchlistQuote], top_n: int) -> list[WatchlistQuote]:
    candidates = [quote for quote in quotes if (quote.pct_change or 0) >= MIN_STRONG_QUOTE_PCT]
    if not candidates:
        candidates = quotes
    ranked = sorted(
        candidates,
        key=lambda quote: ((quote.pct_change or 0), (quote.turnover_cny or 0)),
        reverse=True,
    )
    return ranked[:top_n]


def _sectors_from_quotes(quotes: list[WatchlistQuote]) -> list[RawSectorInput]:
    ranked = sorted(
        [quote for quote in quotes if quote.pct_change is not None],
        key=lambda quote: quote.pct_change or 0,
        reverse=True,
    )
    return [
        RawSectorInput(
            name=quote.name or quote.symbol,
            pct_change=quote.pct_change or 0,
            limit_up_count=1 if (quote.pct_change or 0) >= 9.8 else 0,
            stock_up_ratio=1.0 if (quote.pct_change or 0) > 0 else 0.0,
            turnover_change=0.0,
            news_weight=min(max(abs(quote.pct_change or 0) / 8, 0.0), 1.0),
        )
        for quote in ranked[:10]
    ]


def _sectors_from_theme_quotes(quotes: list[WatchlistQuote]) -> list[RawSectorInput]:
    grouped: dict[str, list[WatchlistQuote]] = {}
    for quote in quotes:
        theme = _theme_for_quote(quote)
        if theme is not None:
            grouped.setdefault(theme, []).append(quote)

    sectors = [_sector_from_group(theme, theme_quotes) for theme, theme_quotes in grouped.items()]
    return sorted(
        [sector for sector in sectors if sector is not None],
        key=lambda sector: (sector.limit_up_count, sector.pct_change, sector.stock_up_ratio),
        reverse=True,
    )[:10]


def _frontline_stocks_from_theme_quotes(quotes: list[WatchlistQuote]) -> dict[str, list[WatchlistQuote]]:
    grouped: dict[str, list[WatchlistQuote]] = {}
    for quote in quotes:
        theme = _theme_for_quote(quote)
        if theme is not None:
            grouped.setdefault(theme, []).append(quote)
    return {
        theme: _rank_frontline_stocks(theme_quotes)
        for theme, theme_quotes in grouped.items()
    }


def _rank_frontline_stocks(quotes: list[WatchlistQuote]) -> list[WatchlistQuote]:
    candidates = [
        quote
        for quote in quotes
        if quote.pct_change is not None and _is_mainland_regular_equity(quote)
    ]
    ranked = sorted(
        candidates,
        key=lambda quote: ((quote.pct_change or 0), (quote.turnover_cny or 0)),
        reverse=True,
    )
    return ranked[:8]


def _theme_for_quote(quote: WatchlistQuote) -> str | None:
    name = quote.name or quote.symbol
    for theme, keywords in THEME_KEYWORDS:
        if any(keyword in name for keyword in keywords):
            return theme
    return None


def _sector_from_group(theme: str, quotes: list[WatchlistQuote]) -> RawSectorInput | None:
    if not quotes:
        return None
    changes = [quote.pct_change or 0 for quote in quotes if quote.pct_change is not None]
    if not changes:
        return None
    turnover_values = [quote.turnover_cny or 0 for quote in quotes]
    avg_change = sum(changes) / len(changes)
    limit_up_count = sum(1 for change in changes if change >= 9.8)
    up_ratio = sum(1 for change in changes if change > 0) / len(changes)
    return RawSectorInput(
        name=theme,
        pct_change=avg_change,
        limit_up_count=limit_up_count,
        stock_up_ratio=up_ratio,
        turnover_change=min(sum(turnover_values) / 10_000_000_000, 1.0),
        news_weight=min(max((limit_up_count * 0.25) + (avg_change / 20), 0.0), 1.0),
    )


def _replace_theme_sectors_with_industry_quotes(
    sectors: list[RawSectorInput],
    industry_theme_quotes: dict[str, list[WatchlistQuote]],
) -> list[RawSectorInput]:
    output: list[RawSectorInput] = []
    for sector in sectors:
        quotes = industry_theme_quotes.get(sector.name)
        replacement = _sector_from_group(sector.name, quotes) if quotes else None
        output.append(replacement or sector)
    return sorted(
        output,
        key=lambda sector: (sector.limit_up_count, sector.pct_change, sector.stock_up_ratio),
        reverse=True,
    )[:10]


def _sectors_from_industry_members(
    quotes: list[WatchlistQuote],
    industries: list[IndustryUniverse],
) -> list[RawSectorInput]:
    quote_by_symbol = {quote.symbol: quote for quote in quotes}
    grouped: dict[str, list[WatchlistQuote]] = {}
    for industry in industries:
        for symbol in industry.symbols:
            quote = quote_by_symbol.get(symbol)
            if quote is not None and _is_mainland_regular_equity(quote):
                grouped.setdefault(industry.name, []).append(quote)

    sectors: list[RawSectorInput] = []
    for name, sector_quotes in grouped.items():
        changes = [quote.pct_change or 0 for quote in sector_quotes if quote.pct_change is not None]
        if not changes:
            continue
        turnover_values = [quote.turnover_cny or 0 for quote in sector_quotes]
        avg_change = sum(changes) / len(changes)
        limit_up_count = sum(1 for change in changes if change >= 9.8)
        up_ratio = sum(1 for change in changes if change > 0) / len(changes)
        sectors.append(
            RawSectorInput(
                name=name,
                pct_change=avg_change,
                limit_up_count=limit_up_count,
                stock_up_ratio=up_ratio,
                turnover_change=min(sum(turnover_values) / 10_000_000_000, 1.0),
                news_weight=min(max((limit_up_count * 0.25) + (avg_change / 20), 0.0), 1.0),
            )
        )
    return sorted(
        sectors,
        key=lambda sector: (sector.limit_up_count, sector.pct_change, sector.stock_up_ratio),
        reverse=True,
    )[:10]


def _frontline_stocks_from_industry_members(
    quotes: list[WatchlistQuote],
    industries: list[IndustryUniverse],
) -> dict[str, list[WatchlistQuote]]:
    quote_by_symbol = {quote.symbol: quote for quote in quotes}
    output: dict[str, list[WatchlistQuote]] = {}
    for industry in industries:
        sector_quotes = [
            quote
            for symbol in industry.symbols
            if (quote := quote_by_symbol.get(symbol)) is not None
        ]
        ranked = _rank_frontline_stocks(sector_quotes)
        if ranked:
            output[industry.name] = ranked
    return output


def _industries_by_theme(industries: list[IndustryUniverse]) -> dict[str, list[IndustryUniverse]]:
    grouped: dict[str, list[IndustryUniverse]] = {}
    for industry in industries:
        theme = _theme_for_industry(industry.name)
        if theme is not None:
            grouped.setdefault(theme, []).append(industry)
    return grouped


def _theme_for_industry(industry_name: str) -> str | None:
    aliases: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("PCB", ("印制电路板", "PCB")),
        ("半导体", ("半导体", "集成电路", "芯片", "封测")),
        ("机器人", ("机器人", "自动化设备")),
        ("有色金属", ("黄金", "贵金属", "铜", "铝", "铅锌", "小金属", "金属新材料")),
        ("电力设备", ("电力设备", "综合电力设备商", "电网", "输变电")),
        ("电力", ("火力发电", "水力发电", "核力发电", "热力服务")),
        ("新材料", ("新材料", "非金属材料", "磁性材料", "膜材料", "改性塑料")),
    )
    return next(
        (
            theme
            for theme, keywords in aliases
            if any(keyword in industry_name for keyword in keywords)
        ),
        None,
    )


def _clean_industry_name(name: str) -> str:
    text = name
    if ":" in text:
        text = text.split(":", 1)[1]
    for prefix in ("SW3", "SW2", "SW1"):
        if text.startswith(prefix):
            text = text.removeprefix(prefix)
    return text.replace("Ⅲ", "").replace("Ⅱ", "").strip()


def _market_tags(changes: list[float], turnover_cny: float) -> list[str]:
    up_count = sum(1 for change in changes if change > 0)
    down_count = sum(1 for change in changes if change < 0)
    if up_count > down_count * 1.5:
        breadth = "普涨"
    elif down_count > up_count * 1.5:
        breadth = "普跌"
    else:
        breadth = "分化"
    return [breadth, "放量" if turnover_cny >= 10000 else "缩量"]


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None and str(value) else None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_status_error(status_code: object) -> str:
    return "TickFlow HTTP 请求失败" if status_code is None else f"TickFlow HTTP {status_code}"
