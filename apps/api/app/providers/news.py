from typing import Protocol

from pydantic import BaseModel

from app.providers.market import ProviderStatus
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
