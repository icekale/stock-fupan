from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class MorningAuctionBucket(StrEnum):
    SELECTED = "selected"
    ATTACK = "attack"
    WATCH = "watch"
    AVOID = "avoid"


class DailyBar(BaseModel):
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    turnover_rate: float | None = None


class AuctionSnapshot(BaseModel):
    trade_date: str
    symbol: str
    name: str = ""
    snapshot_time: str
    indicative_price: float | None = None
    prev_close: float | None = None
    auction_volume: float | None = None
    auction_amount: float | None = None
    bid_volume: float | None = None
    ask_volume: float | None = None
    unmatched_volume: float | None = None


class FilterResult(BaseModel):
    passed: bool
    risk_flags: list[str] = Field(default_factory=list)


class MorningAuctionSample(BaseModel):
    trade_date: str
    symbol: str
    name: str
    features: dict[str, float | int | None] = Field(default_factory=dict)
    open_price: float
    close_price: float

    @property
    def _raw_open_to_close_return(self) -> float:
        if self.open_price <= 0:
            return 0.0
        return self.close_price / self.open_price - 1

    @property
    def open_to_close_return(self) -> float:
        return round(self._raw_open_to_close_return, 6)

    @property
    def main_label(self) -> bool:
        return self._raw_open_to_close_return >= 0.03

    @property
    def strong_label(self) -> bool:
        return self._raw_open_to_close_return >= 0.05

    @property
    def safe_label(self) -> bool:
        return self._raw_open_to_close_return > 0

    @property
    def risk_label(self) -> bool:
        return self._raw_open_to_close_return <= -0.03


class MorningAuctionPredictionItem(BaseModel):
    symbol: str
    name: str
    prob_3pct: float
    strong_5pct_score: float
    bucket: MorningAuctionBucket
    auction_reasons: list[str] = Field(default_factory=list)
    trend_reasons: list[str] = Field(default_factory=list)
    sector_reasons: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    data_quality: list[str] = Field(default_factory=list)


class MorningAuctionRun(BaseModel):
    run_id: str
    trade_date: str
    model_version: str
    feature_version: str
    source_status: dict[str, str] = Field(default_factory=dict)
    selected_pool: list[MorningAuctionPredictionItem] = Field(default_factory=list)
    attack_pool: list[MorningAuctionPredictionItem] = Field(default_factory=list)
    watch_pool: list[MorningAuctionPredictionItem] = Field(default_factory=list)
    avoid_pool: list[MorningAuctionPredictionItem] = Field(default_factory=list)
    items: list[MorningAuctionPredictionItem] = Field(default_factory=list)
