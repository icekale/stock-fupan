from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.structured_review import StructuredReviewDTO


class ReportKind(StrEnum):
    CLOSE = "close"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    VALIDATION_FAILED = "validation_failed"
    READY_FOR_REVIEW = "ready_for_review"
    EXPORTED = "exported"


class IndexSnapshot(BaseModel):
    name: str
    code: str
    close: float
    pct_change: float


class MarketBreadth(BaseModel):
    up_count: int
    down_count: int
    limit_up_count: int
    limit_down_count: int


class StockCandidate(BaseModel):
    code: str
    name: str
    pct_change: float
    turnover_cny: float | None = None
    tags: list[str] = Field(default_factory=list)


class NewsItem(BaseModel):
    title: str
    url: str
    source: str | None = None
    summary: str
    published_at: str | None = None
    matched_sector: str | None = None
    weight: float = 1.0


class SectorCandidate(BaseModel):
    name: str
    score: float
    rank: int
    pct_change: float
    reason: str
    top_stocks: list[StockCandidate] = Field(default_factory=list)
    news_summaries: list[str] = Field(default_factory=list)
    factor_scores: dict[str, float] = Field(default_factory=dict)
    confidence: str = "medium"


class ReportNarrative(BaseModel):
    conclusion: str
    overview: str
    sector_commentary: list[str]
    watchlist: list[str]
    tomorrow: str
    risks: list[str]


class OverrideRecord(BaseModel):
    target_type: str
    target_id: str
    action: str
    payload: dict[str, Any]


class LLMCallRecord(BaseModel):
    provider: str
    model: str
    prompt: str
    parameters: dict[str, Any]
    output: dict[str, Any]
    validation_errors: list[str] = Field(default_factory=list)


class WatchlistMatch(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    pct_change: float | None = None
    reason: str


class WatchlistObservation(BaseModel):
    import_id: int | None = None
    total_count: int = 0
    quote_count: int = 0
    strongest: list[WatchlistMatch] = Field(default_factory=list)
    weakest: list[WatchlistMatch] = Field(default_factory=list)
    sector_matches: list[WatchlistMatch] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReportDTO(BaseModel):
    trade_date: str
    kind: ReportKind
    title: str
    indices: list[IndexSnapshot]
    breadth: MarketBreadth
    turnover_cny: float
    market_state_tags: list[str]
    sectors: list[SectorCandidate]
    narrative: ReportNarrative
    news: list[NewsItem] = Field(default_factory=list)
    structured_review: StructuredReviewDTO | None = None
    watchlist_observation: WatchlistObservation | None = None
    overrides: list[OverrideRecord] = Field(default_factory=list)
    algorithm_versions: dict[str, str] = Field(
        default_factory=lambda: {
            "sector_score": "sector_score_v1",
            "news_weight": "news_weight_v1",
            "fact_validation": "fact_validation_v1",
        }
    )
