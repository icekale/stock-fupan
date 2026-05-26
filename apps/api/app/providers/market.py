from dataclasses import dataclass
from typing import Protocol

from app.rules.scoring import RawSectorInput
from app.schemas.report import IndexSnapshot, MarketBreadth, NewsItem


@dataclass(frozen=True)
class MarketCloseSnapshot:
    trade_date: str
    indices: list[IndexSnapshot]
    breadth: MarketBreadth
    turnover_cny: float
    market_state_tags: list[str]
    raw_sectors: list[RawSectorInput]

    def to_report_seed(self, news: list[NewsItem]) -> dict[str, object]:
        return {
            "trade_date": self.trade_date,
            "indices": [index.model_dump() for index in self.indices],
            "breadth": self.breadth.model_dump(),
            "turnover_cny": self.turnover_cny,
            "market_state_tags": self.market_state_tags,
            "raw_sectors": [sector.__dict__ for sector in self.raw_sectors],
            "news": [item.model_dump() for item in news],
        }


class MarketDataProvider(Protocol):
    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        raise NotImplementedError


class FakeMarketDataProvider:
    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=[
                IndexSnapshot(name="上证指数", code="000001", close=3100.5, pct_change=1.2),
                IndexSnapshot(name="创业板指", code="399006", close=1950.2, pct_change=2.1),
            ],
            breadth=MarketBreadth(
                up_count=3200,
                down_count=1800,
                limit_up_count=86,
                limit_down_count=8,
            ),
            turnover_cny=12345.67,
            market_state_tags=["放量", "分化"],
            raw_sectors=[
                RawSectorInput(
                    name="机器人",
                    pct_change=5.88,
                    limit_up_count=8,
                    stock_up_ratio=0.82,
                    turnover_change=0.35,
                    news_weight=0.8,
                ),
                RawSectorInput(
                    name="PCB",
                    pct_change=3.6,
                    limit_up_count=4,
                    stock_up_ratio=0.7,
                    turnover_change=0.2,
                    news_weight=0.5,
                ),
            ],
        )
