from __future__ import annotations

import re
import time
import uuid
from typing import Any

import httpx

from app.providers.market import ProviderFallbackError
from app.providers.review_sources import (
    ReviewSourceResult,
    ReviewStockEvidence,
    ReviewThemeEvidence,
)
from app.schemas.report import DragonTigerSeat, DragonTigerStock, DragonTigerSummary, NewsItem


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"


class AStockThsHotProvider:
    source_name = "a-stock-data 同花顺热点"

    def __init__(self, timeout_seconds: float = 12, http_client: object | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()
        self.source_url = "http://zx.10jqka.com.cn/event/api/getharden/"

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def __call__(self, trade_date: str) -> ReviewSourceResult:
        url = (
            "http://zx.10jqka.com.cn/event/api/getharden/"
            f"date/{trade_date}/orderby/date/orderway/desc/charset/GBK/"
        )
        response = self.http_client.get(url, headers={"User-Agent": UA}, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("errocode", 0) != 0:
            return ReviewSourceResult(
                source=self.source_name,
                source_url=url,
                status="failed",
                reason=str(payload.get("errormsg", "同花顺热点响应异常"))
                if isinstance(payload, dict)
                else "同花顺热点响应异常",
                trade_date=trade_date,
            )
        rows = payload.get("data") or []
        if not isinstance(rows, list) or not rows:
            return ReviewSourceResult(
                source=self.source_name,
                source_url=url,
                status="failed",
                reason="同花顺热点无结果",
                trade_date=trade_date,
            )

        themes: list[ReviewThemeEvidence] = []
        hot_stocks: list[ReviewStockEvidence] = []
        notes: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            code = str(row.get("code") or "").strip()
            reason = str(row.get("reason") or "").strip()
            pct_change = _to_float(row.get("zhangfu"))
            stock = ReviewStockEvidence(
                name=name,
                code=code or None,
                pct_change=pct_change,
                note=reason,
                source=self.source_name,
            )
            if name:
                hot_stocks.append(stock)
            if name and reason:
                notes.append(f"{name}: {reason}")
            for theme_name in _split_reason_tags(reason):
                themes.append(
                    ReviewThemeEvidence(
                        name=theme_name,
                        pct_change=pct_change,
                        reason=reason,
                        stocks=[stock] if name else [],
                        source=self.source_name,
                    )
                )

        return ReviewSourceResult(
            source=self.source_name,
            source_url=url,
            status="success" if themes or hot_stocks else "failed",
            reason=None if themes or hot_stocks else "未解析到同花顺热点内容",
            trade_date=trade_date,
            themes=_dedupe_themes(themes),
            hot_stocks=_dedupe_stocks(hot_stocks),
            market_notes=_dedupe_text(notes[:20]),
        )


class AStockIndustryRankProvider:
    source_name = "a-stock-data 东财板块排名"

    def __init__(
        self,
        timeout_seconds: float = 12,
        http_client: object | None = None,
        top_n: int = 20,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()
        self.top_n = top_n
        self.source_url = "https://push2delay.eastmoney.com/api/qt/clist/get"

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def __call__(self, trade_date: str) -> ReviewSourceResult:
        response = self.http_client.get(
            self.source_url,
            headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"},
            params={
                "pn": "1",
                "pz": "100",
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fs": "m:90+t:3",
                "fid": "f3",
                "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", {}).get("diff", []) if isinstance(payload, dict) else []
        if not isinstance(items, list) or not items:
            return ReviewSourceResult(
                source=self.source_name,
                source_url=self.source_url,
                status="failed",
                reason="东财板块排名无结果",
                trade_date=trade_date,
            )
        themes: list[ReviewThemeEvidence] = []
        stocks: list[ReviewStockEvidence] = []
        notes: list[str] = []
        for item in items[: self.top_n]:
            if not isinstance(item, dict):
                continue
            industry = str(item.get("f14") or "").strip()
            pct_change = _to_float(item.get("f3"))
            leader = str(item.get("f128") or "").strip()
            leader_code = str(item.get("f140") or "").strip()
            leader_change = _to_float(item.get("f136"))
            up_count = item.get("f104", 0)
            down_count = item.get("f105", 0)
            theme_stocks = [
                ReviewStockEvidence(
                    name=leader,
                    code=leader_code or None,
                    pct_change=leader_change,
                    source=self.source_name,
                )
            ] if leader else []
            if industry:
                themes.append(
                    ReviewThemeEvidence(
                        name=industry,
                        pct_change=pct_change,
                        reason=(
                            f"行业涨跌幅{pct_change if pct_change is not None else 0}%，"
                            f"涨{up_count}跌{down_count}"
                        ),
                        stocks=theme_stocks,
                        source=self.source_name,
                    )
                )
                notes.append(
                    f"{industry}: {pct_change if pct_change is not None else 0}% "
                    f"涨{up_count}跌{down_count} 领涨{leader}"
                )
            if leader:
                stocks.append(
                    ReviewStockEvidence(
                        name=leader,
                        code=leader_code or None,
                        pct_change=leader_change,
                        source=self.source_name,
                    )
                )
        return ReviewSourceResult(
            source=self.source_name,
            source_url=self.source_url,
            status="success" if themes else "failed",
            reason=None if themes else "未解析到板块排名内容",
            trade_date=trade_date,
            themes=_dedupe_themes(themes),
            hot_stocks=_dedupe_stocks(stocks),
            market_notes=_dedupe_text(notes),
        )


class AStockDragonTigerProvider:
    source_name = "a-stock-data 东财龙虎榜"

    def __init__(
        self,
        timeout_seconds: float = 12,
        http_client: object | None = None,
        page_size: int = 200,
        max_detail_stocks: int = 5,
        sleep_seconds: float = 1.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()
        self.page_size = page_size
        self.max_detail_stocks = max_detail_stocks
        self.sleep_seconds = sleep_seconds
        self.source_url = "https://data.eastmoney.com/stock/lhb.html"
        self.api_url = "https://datacenter-web.eastmoney.com/api/data/v1/get"

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def __call__(self, trade_date: str) -> ReviewSourceResult:
        try:
            rows = self._datacenter(
                "RPT_DAILYBILLBOARD_DETAILSNEW",
                filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
                page_size=self.page_size,
                sort_columns="BILLBOARD_NET_AMT",
                sort_types="-1",
            )
        except Exception as exc:
            summary = DragonTigerSummary(
                trade_date=trade_date,
                status="failed",
                reason=str(exc) or exc.__class__.__name__,
                conclusion="龙虎榜数据未取得。",
            )
            return ReviewSourceResult(
                source=self.source_name,
                source_url=self.source_url,
                status="failed",
                reason=summary.reason,
                trade_date=trade_date,
                dragon_tiger=summary,
            )
        if not rows:
            summary = DragonTigerSummary(
                trade_date=trade_date,
                status="failed",
                reason="东财龙虎榜无结果",
                conclusion="龙虎榜数据未取得。",
            )
            return ReviewSourceResult(
                source=self.source_name,
                source_url=self.source_url,
                status="failed",
                reason="东财龙虎榜无结果",
                trade_date=trade_date,
                dragon_tiger=summary,
            )

        stocks = [_dragon_tiger_stock(row) for row in rows if isinstance(row, dict)]
        stocks = [stock for stock in stocks if stock.code and stock.name]
        top_net_buy = sorted(stocks, key=lambda stock: stock.net_buy_wan, reverse=True)[:5]
        top_net_sell = sorted(stocks, key=lambda stock: stock.net_buy_wan)[:5]
        detail_failed = False
        for stock in top_net_buy[: self.max_detail_stocks]:
            try:
                self._attach_seats(stock, trade_date)
            except Exception:
                detail_failed = True
            if self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)

        institution_net = _seat_net_by_role(top_net_buy, "institution")
        connect_net = _seat_net_by_role(top_net_buy, "northbound")
        summary = DragonTigerSummary(
            trade_date=trade_date,
            status="success",
            reason="席位明细部分失败" if detail_failed else None,
            total_records=len(stocks),
            positive_net_count=sum(1 for stock in stocks if stock.net_buy_wan > 0),
            negative_net_count=sum(1 for stock in stocks if stock.net_buy_wan < 0),
            net_buy_total_wan=round(sum(stock.net_buy_wan for stock in stocks), 1),
            top_net_buy=top_net_buy,
            top_net_sell=top_net_sell,
            highlighted_stocks=top_net_buy[:3],
            institution_net_buy_wan=institution_net,
            connect_net_buy_wan=connect_net,
            sentiment=_dragon_tiger_sentiment(stocks, institution_net, connect_net),
            strength=_dragon_tiger_strength(stocks),
            conclusion=_dragon_tiger_conclusion(top_net_buy, institution_net, connect_net),
            risk_notes=_dragon_tiger_risk_notes(top_net_sell),
        )
        return ReviewSourceResult(
            source=self.source_name,
            source_url=self.source_url,
            status="success",
            reason=summary.reason,
            trade_date=trade_date,
            market_notes=_dragon_tiger_market_notes(summary),
            hot_stocks=[
                ReviewStockEvidence(
                    name=stock.name,
                    code=stock.code,
                    pct_change=stock.change_pct,
                    note=stock.reason,
                    source=self.source_name,
                )
                for stock in top_net_buy[:5]
            ],
            dragon_tiger=summary,
        )

    def _datacenter(
        self,
        report_name: str,
        filter_str: str,
        page_size: int,
        sort_columns: str,
        sort_types: str,
    ) -> list[dict[str, Any]]:
        response = self.http_client.get(
            self.api_url,
            headers={
                "User-Agent": UA,
                "Referer": self.source_url,
                "Accept": "application/json,text/plain,*/*",
            },
            params={
                "reportName": report_name,
                "columns": "ALL",
                "filter": filter_str,
                "pageNumber": "1",
                "pageSize": str(page_size),
                "sortColumns": sort_columns,
                "sortTypes": sort_types,
                "source": "WEB",
                "client": "WEB",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is False:
            message = (
                payload.get("message", "东财龙虎榜响应异常")
                if isinstance(payload, dict)
                else "东财龙虎榜响应异常"
            )
            raise ProviderFallbackError(str(message))
        rows = payload.get("result", {}).get("data", []) if isinstance(payload.get("result"), dict) else []
        return rows if isinstance(rows, list) else []

    def _attach_seats(self, stock: DragonTigerStock, trade_date: str) -> None:
        filter_str = f"(TRADE_DATE='{trade_date}')(SECURITY_CODE=\"{stock.code}\")"
        buy_rows = self._datacenter(
            "RPT_BILLBOARD_DAILYDETAILSBUY",
            filter_str=filter_str,
            page_size=10,
            sort_columns="BUY",
            sort_types="-1",
        )
        sell_rows = self._datacenter(
            "RPT_BILLBOARD_DAILYDETAILSSELL",
            filter_str=filter_str,
            page_size=10,
            sort_columns="SELL",
            sort_types="-1",
        )
        stock.seats_buy = [_dragon_tiger_seat(row) for row in buy_rows[:5]]
        stock.seats_sell = [_dragon_tiger_seat(row) for row in sell_rows[:5]]


class EastmoneyGlobalNewsProvider:
    provider_name = "eastmoney_global"

    def __init__(
        self,
        timeout_seconds: float = 12,
        http_client: object | None = None,
        page_size: int = 50,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()
        self.page_size = page_size
        self.base_url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        try:
            response = self.http_client.get(
                self.base_url,
                headers={"User-Agent": UA, "Referer": "https://kuaixun.eastmoney.com/"},
                params={
                    "client": "web",
                    "biz": "web_724",
                    "fastColumn": "102",
                    "sortEnd": "",
                    "pageSize": str(self.page_size),
                    "req_trace": str(uuid.uuid4()),
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ProviderFallbackError(f"东财全球资讯请求失败: {exc.__class__.__name__}") from exc

        rows = payload.get("data", {}).get("fastNewsList", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list) or not rows:
            raise ProviderFallbackError("东财全球资讯无结果")
        items = [_global_news_item(row, sector_name) for row in rows if isinstance(row, dict)]
        matched = [
            item
            for item in items
            if sector_name in item.title or sector_name in item.summary
        ]
        if matched:
            return matched[:5]
        return [
            item.model_copy(update={"matched_sector": sector_name, "weight": 0.4})
            for item in items[:3]
        ]


def _global_news_item(row: dict[str, Any], sector_name: str) -> NewsItem:
    title = str(row.get("title") or "东财全球资讯")
    summary = str(row.get("summary") or title)
    return NewsItem(
        title=title,
        url=str(row.get("url") or "https://kuaixun.eastmoney.com/"),
        source="东方财富",
        summary=summary[:200],
        published_at=row.get("showTime") or row.get("time"),
        matched_sector=sector_name,
        weight=0.7,
    )


def _dragon_tiger_stock(row: dict[str, Any]) -> DragonTigerStock:
    return DragonTigerStock(
        code=str(row.get("SECURITY_CODE") or ""),
        name=str(row.get("SECURITY_NAME_ABBR") or ""),
        reason=str(row.get("EXPLANATION") or row.get("EXPLAIN") or ""),
        close=_to_float_value(row.get("CLOSE_PRICE")),
        change_pct=_to_float_value(row.get("CHANGE_RATE")),
        turnover_pct=_to_float_value(row.get("TURNOVERRATE")),
        net_buy_wan=round((_to_float_value(row.get("BILLBOARD_NET_AMT")) or 0) / 10000, 1),
        buy_wan=round((_to_float_value(row.get("BILLBOARD_BUY_AMT")) or 0) / 10000, 1),
        sell_wan=round((_to_float_value(row.get("BILLBOARD_SELL_AMT")) or 0) / 10000, 1),
        tags=["龙虎榜"],
    )


def _dragon_tiger_seat(row: dict[str, Any]) -> DragonTigerSeat:
    name = str(row.get("OPERATEDEPT_NAME") or "")
    return DragonTigerSeat(
        name=name,
        buy_wan=round((_to_float_value(row.get("BUY")) or 0) / 10000, 1),
        sell_wan=round((_to_float_value(row.get("SELL")) or 0) / 10000, 1),
        net_wan=round((_to_float_value(row.get("NET")) or 0) / 10000, 1),
        role=_dragon_tiger_seat_role(name),
    )


def _dragon_tiger_seat_role(name: str) -> str:
    if "机构专用" in name:
        return "institution"
    if "沪股通专用" in name or "深股通专用" in name:
        return "northbound"
    return "brokerage"


def _seat_net_by_role(stocks: list[DragonTigerStock], role: str) -> float:
    value = sum(
        seat.net_wan
        for stock in stocks
        for seat in stock.seats_buy
        if seat.role == role
    )
    return round(value, 1)


def _dragon_tiger_sentiment(
    stocks: list[DragonTigerStock],
    institution_net: float,
    connect_net: float,
) -> str:
    if not stocks:
        return "unknown"
    positive_ratio = sum(1 for stock in stocks if stock.net_buy_wan > 0) / len(stocks)
    top_net = max((stock.net_buy_wan for stock in stocks), default=0)
    if len(stocks) >= 50 and positive_ratio >= 0.55 and top_net >= 10000 and (
        institution_net > 0 or connect_net > 0
    ):
        return "strong"
    if len(stocks) >= 20 and positive_ratio >= 0.45:
        return "medium"
    return "weak"


def _dragon_tiger_strength(stocks: list[DragonTigerStock]) -> str:
    top_five_total = sum(
        stock.net_buy_wan
        for stock in sorted(stocks, key=lambda item: item.net_buy_wan, reverse=True)[:5]
    )
    big_net_count = sum(1 for stock in stocks if stock.net_buy_wan >= 10000)
    if top_five_total >= 50000 and big_net_count >= 2:
        return "high"
    if top_five_total >= 15000 or big_net_count:
        return "normal"
    return "low"


def _dragon_tiger_conclusion(
    top_net_buy: list[DragonTigerStock],
    institution_net: float,
    connect_net: float,
) -> str:
    names = "、".join(stock.name for stock in top_net_buy[:3] if stock.name)
    seat_parts = []
    if institution_net > 0:
        seat_parts.append("机构净买")
    if connect_net > 0:
        seat_parts.append("股通席位净买")
    seat_text = f"，{'、'.join(seat_parts)}参与" if seat_parts else ""
    return f"龙虎榜净买集中在{names or '核心个股'}{seat_text}。"


def _dragon_tiger_risk_notes(top_net_sell: list[DragonTigerStock]) -> list[str]:
    if not top_net_sell:
        return []
    names = "、".join(stock.name for stock in top_net_sell[:3] if stock.net_buy_wan < 0)
    return [f"净卖出集中在{names}，次日需观察高位分歧是否扩大。"] if names else []


def _dragon_tiger_market_notes(summary: DragonTigerSummary) -> list[str]:
    names = "、".join(stock.name for stock in summary.top_net_buy[:3])
    return [
        f"龙虎榜情绪{summary.sentiment}，攻击强度{summary.strength}，净买额集中在{names}。",
        summary.conclusion,
        *summary.risk_notes[:1],
    ]


def _to_float_value(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace("%", "").replace("+", "").strip())
    except ValueError:
        return None


def _split_reason_tags(reason: str) -> list[str]:
    return [item.strip() for item in re.split(r"[+、,/，]+", reason) if item.strip()]


def _dedupe_text(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _dedupe_stocks(values: list[ReviewStockEvidence]) -> list[ReviewStockEvidence]:
    output: list[ReviewStockEvidence] = []
    seen: set[tuple[str, str | None]] = set()
    for value in values:
        key = (value.name, value.code)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _dedupe_themes(values: list[ReviewThemeEvidence]) -> list[ReviewThemeEvidence]:
    output: list[ReviewThemeEvidence] = []
    seen: set[str] = set()
    for value in values:
        if value.name in seen:
            continue
        seen.add(value.name)
        output.append(value)
    return output
