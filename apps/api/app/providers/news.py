from datetime import datetime, timedelta
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from app.providers.market import ProviderFallbackError, ProviderStatus
from app.schemas.report import NewsItem


class SectorNewsResult(BaseModel):
    sector: str
    items: list[NewsItem]
    status: ProviderStatus


def _provider_name(provider: object, default: str) -> str:
    value = getattr(provider, "provider_name", default)
    return value if isinstance(value, str) and value else default


class NewsProvider(Protocol):
    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        raise NotImplementedError


class FakeNewsProvider:
    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        return [
            NewsItem(
                title=f"{sector_name}产业链催化增强",
                url=f"https://example.com/news/{trade_date}/{sector_name}",
                source="示例财经",
                summary=f"{sector_name}方向出现政策和产业消息共振。",
                published_at=f"{trade_date}T15:00:00+08:00",
                matched_sector=sector_name,
                weight=0.8,
            )
        ]


class AnspireNewsProvider:
    provider_name = "anspire"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://plugin.anspire.cn/api/ntsearch/search",
        top_k: int = 10,
        lookback_hours: int = 36,
        timeout_seconds: float = 12,
        http_client: object | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.top_k = top_k
        self.lookback_hours = lookback_hours
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def __enter__(self) -> "AnspireNewsProvider":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        if not self.api_key:
            raise ProviderFallbackError("ANSPIRE_API_KEY 未配置")

        to_time = datetime.fromisoformat(f"{trade_date}T23:59:59")
        from_time = to_time - timedelta(hours=self.lookback_hours)
        try:
            response = self.http_client.get(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={
                    "query": f"{sector_name} A股",
                    "top_k": self.top_k,
                    "FromTime": from_time.isoformat(),
                    "ToTime": to_time.isoformat(),
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderFallbackError("Anspire 请求超时") from exc
        except ProviderFallbackError as exc:
            raise ProviderFallbackError(self._safe_request_error(exc)) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            raise ProviderFallbackError(self._safe_http_status_error(status_code)) from exc
        except Exception as exc:
            raise ProviderFallbackError(self._safe_request_error(exc)) from exc

        try:
            payload = response.json()
        except Exception as exc:
            raise ProviderFallbackError("Anspire JSON 解析失败") from exc

        raw_items = self._extract_items(payload)
        if not raw_items:
            raise ProviderFallbackError("Anspire 无结果")

        return [self._to_news_item(raw_item, sector_name) for raw_item in raw_items[: self.top_k]]

    def _extract_items(self, payload: object) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ProviderFallbackError("Anspire 响应结构异常")
        data = payload.get("data")
        if data is None:
            data = payload.get("results")
        if data is None:
            data = payload.get("items")
        if isinstance(data, dict):
            nested = data.get("list")
            if nested is None:
                nested = data.get("items")
            if nested is None:
                nested = data.get("results")
            data = nested
        if not isinstance(data, list):
            raise ProviderFallbackError("Anspire 响应结构异常")
        return [item for item in data if isinstance(item, dict)]

    def _to_news_item(self, raw_item: dict[str, Any], sector_name: str) -> NewsItem:
        title = str(raw_item.get("title") or raw_item.get("name") or "未命名新闻")
        url = str(raw_item.get("url") or raw_item.get("link") or "")
        summary = str(raw_item.get("summary") or raw_item.get("snippet") or raw_item.get("content") or title)
        source = raw_item.get("source") or raw_item.get("site")
        source_text = str(source) if source is not None else None
        return NewsItem(
            title=title,
            url=url,
            source=source_text,
            summary=summary,
            published_at=raw_item.get("published_at") or raw_item.get("publish_time") or raw_item.get("time"),
            matched_sector=sector_name,
            weight=self._source_weight(source_text),
        )

    def _source_weight(self, source: str | None) -> float:
        if not source:
            return 0.5
        trusted_sources = ("财联社", "东方财富", "证券时报", "上海证券报", "上证报", "交易所")
        return 0.9 if any(name in source for name in trusted_sources) else 0.6

    def _safe_request_error(self, exc: Exception) -> str:
        if isinstance(exc, ProviderFallbackError):
            text = str(exc)
            if text.startswith("Anspire HTTP "):
                status_code = text.removeprefix("Anspire HTTP ").split()[0]
                return self._safe_http_status_error(status_code)
        return f"Anspire 请求失败: {exc.__class__.__name__}"

    def _safe_http_status_error(self, status_code: object) -> str:
        if status_code is None:
            return "Anspire HTTP 请求失败"
        return f"Anspire HTTP {status_code}"


class FallbackNewsProvider:
    def __init__(
        self,
        primary: NewsProvider,
        fallback: NewsProvider,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        result = self.search_sector_news_with_status(sector_name, trade_date)
        return result.items

    def search_sector_news_with_status(self, sector_name: str, trade_date: str) -> SectorNewsResult:
        provider = _provider_name(self.primary, "news")
        try:
            items = self.primary.search_sector_news(sector_name, trade_date)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            if not self.fallback_enabled:
                raise
            return SectorNewsResult(
                sector=sector_name,
                items=self.fallback.search_sector_news(sector_name, trade_date),
                status=ProviderStatus(
                    provider=provider,
                    status="fallback",
                    fallback_used=True,
                    reason=reason,
                ),
            )

        return SectorNewsResult(
            sector=sector_name,
            items=items,
            status=ProviderStatus(
                provider=provider,
                status="success",
                fallback_used=False,
                reason=None,
            ),
        )
