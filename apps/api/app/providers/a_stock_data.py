from __future__ import annotations

import re
import uuid
from typing import Any

import httpx

from app.providers.market import ProviderFallbackError
from app.providers.review_sources import (
    ReviewSourceResult,
    ReviewStockEvidence,
    ReviewThemeEvidence,
)
from app.schemas.report import NewsItem


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
    source_name = "a-stock-data 东财行业排名"

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
        self.source_url = "https://push2.eastmoney.com/api/qt/clist/get"

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
                "fs": "m:90+t:2",
                "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
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
                reason="东财行业排名无结果",
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
            leader = str(item.get("f140") or "").strip()
            leader_change = _to_float(item.get("f136"))
            up_count = item.get("f104", 0)
            down_count = item.get("f105", 0)
            if industry:
                themes.append(
                    ReviewThemeEvidence(
                        name=industry,
                        pct_change=pct_change,
                        reason=(
                            f"行业涨跌幅{pct_change if pct_change is not None else 0}%，"
                            f"涨{up_count}跌{down_count}"
                        ),
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
                        pct_change=leader_change,
                        source=self.source_name,
                    )
                )
        return ReviewSourceResult(
            source=self.source_name,
            source_url=self.source_url,
            status="success" if themes else "failed",
            reason=None if themes else "未解析到行业排名内容",
            trade_date=trade_date,
            themes=_dedupe_themes(themes),
            hot_stocks=_dedupe_stocks(stocks),
            market_notes=_dedupe_text(notes),
        )


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
