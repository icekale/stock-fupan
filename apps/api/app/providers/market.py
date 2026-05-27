from dataclasses import asdict, dataclass
from typing import Literal, Protocol

from pydantic import BaseModel

from app.rules.scoring import RawSectorInput
from app.schemas.report import IndexSnapshot, MarketBreadth, NewsItem


ProviderState = Literal["success", "fallback", "disabled", "failed"]


class ProviderStatus(BaseModel):
    provider: str
    status: ProviderState
    fallback_used: bool = False
    reason: str | None = None


class ProviderFallbackError(RuntimeError):
    pass


def _provider_name(provider: object, default: str) -> str:
    value = getattr(provider, "provider_name", default)
    return value if isinstance(value, str) and value else default


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
            "raw_sectors": [asdict(sector) for sector in self.raw_sectors],
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


class FallbackMarketDataProvider:
    def __init__(
        self,
        primary: MarketDataProvider,
        fallback: MarketDataProvider,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled
        self._last_success_provider: MarketDataProvider | None = None

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        snapshot, _status = self.get_close_snapshot_with_status(trade_date)
        return snapshot

    def get_close_snapshot_with_status(self, trade_date: str) -> tuple[MarketCloseSnapshot, ProviderStatus]:
        provider = _provider_name(self.primary, "market")
        try:
            snapshot = self.primary.get_close_snapshot(trade_date)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            if not self.fallback_enabled:
                raise
            self._last_success_provider = self.fallback
            return self.fallback.get_close_snapshot(trade_date), ProviderStatus(
                provider=provider,
                status="fallback",
                fallback_used=True,
                reason=reason,
            )

        self._last_success_provider = self.primary
        return snapshot, ProviderStatus(
            provider=provider,
            status="success",
            fallback_used=False,
            reason=None,
        )

    def get_sector_frontline_stocks(self, sector_name: str) -> list[object]:
        provider = self._last_success_provider
        if provider is None:
            return []
        get_frontline = getattr(provider, "get_sector_frontline_stocks", None)
        if not callable(get_frontline):
            return []
        return list(get_frontline(sector_name))
