from typing import Protocol

from pydantic import BaseModel

from app.providers.market import ProviderStatus
from app.schemas.report import NewsItem


class SectorNewsResult(BaseModel):
    sector: str
    items: list[NewsItem]
    status: ProviderStatus


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
