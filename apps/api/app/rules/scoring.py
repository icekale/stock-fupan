import math
from dataclasses import dataclass, field


SECTOR_SCORE_VERSION = "sector_score_v1"
PCT_CHANGE_OFFSET = 2.0
PCT_CHANGE_RANGE = 12.0
LIMIT_UP_DIVISOR = 10.0
TURNOVER_CHANGE_OFFSET = 0.2
TURNOVER_CHANGE_RANGE = 0.8

LIMIT_UP_WEIGHT = 0.35
PCT_CHANGE_WEIGHT = 0.20
TURNOVER_WEIGHT = 0.20
BREADTH_WEIGHT = 0.15
NEWS_WEIGHT = 0.10


@dataclass(frozen=True)
class RawSectorInput:
    name: str
    pct_change: float
    limit_up_count: int
    stock_up_ratio: float
    turnover_change: float
    news_weight: float


@dataclass(frozen=True)
class ScoredSector:
    name: str
    score: float
    rank: int
    pct_change: float
    factor_scores: dict[str, float] = field(default_factory=dict)
    algorithm_version: str = SECTOR_SCORE_VERSION


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    if not math.isfinite(value):
        return minimum
    return max(minimum, min(maximum, value))


def _finite_or_zero(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return value


def _normalize_pct_change(value: float) -> float:
    return _clamp((value + PCT_CHANGE_OFFSET) / PCT_CHANGE_RANGE * 100.0)


def _normalize_limit_up(value: int) -> float:
    return _clamp(value / LIMIT_UP_DIVISOR * 100.0)


def _normalize_ratio(value: float) -> float:
    return _clamp(value * 100.0)


def _normalize_turnover_change(value: float) -> float:
    return _clamp((value + TURNOVER_CHANGE_OFFSET) / TURNOVER_CHANGE_RANGE * 100.0)


def _normalize_news(value: float) -> float:
    return _clamp(value * 100.0)


def score_sectors(sectors: list[RawSectorInput], top_n: int = 5) -> list[ScoredSector]:
    if top_n <= 0:
        return []

    scored: list[ScoredSector] = []
    for sector in sectors:
        factor_scores = {
            "pct_change": _normalize_pct_change(sector.pct_change),
            "limit_up": _normalize_limit_up(sector.limit_up_count),
            "breadth": _normalize_ratio(sector.stock_up_ratio),
            "turnover": _normalize_turnover_change(sector.turnover_change),
            "news": _normalize_news(sector.news_weight),
        }
        total = (
            factor_scores["limit_up"] * LIMIT_UP_WEIGHT
            + factor_scores["pct_change"] * PCT_CHANGE_WEIGHT
            + factor_scores["turnover"] * TURNOVER_WEIGHT
            + factor_scores["breadth"] * BREADTH_WEIGHT
            + factor_scores["news"] * NEWS_WEIGHT
        )
        scored.append(
            ScoredSector(
                name=sector.name,
                score=round(total, 2),
                rank=0,
                pct_change=_finite_or_zero(sector.pct_change),
                factor_scores={key: round(value, 2) for key, value in factor_scores.items()},
            )
        )

    ranked = sorted(scored, key=lambda item: (-item.score, item.name))[:top_n]
    return [
        ScoredSector(
            name=item.name,
            score=item.score,
            rank=index + 1,
            pct_change=item.pct_change,
            factor_scores=item.factor_scores,
            algorithm_version=item.algorithm_version,
        )
        for index, item in enumerate(ranked)
    ]
