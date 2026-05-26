from dataclasses import dataclass, field


SECTOR_SCORE_VERSION = "sector_score_v1"


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
    return max(minimum, min(maximum, value))


def _normalize_pct_change(value: float) -> float:
    return _clamp((value + 2.0) / 12.0 * 100.0)


def _normalize_limit_up(value: int) -> float:
    return _clamp(value / 10.0 * 100.0)


def _normalize_ratio(value: float) -> float:
    return _clamp(value * 100.0)


def _normalize_turnover_change(value: float) -> float:
    return _clamp((value + 0.2) / 0.8 * 100.0)


def _normalize_news(value: float) -> float:
    return _clamp(value * 100.0)


def score_sectors(sectors: list[RawSectorInput], top_n: int = 5) -> list[ScoredSector]:
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
            factor_scores["limit_up"] * 0.35
            + factor_scores["pct_change"] * 0.20
            + factor_scores["turnover"] * 0.20
            + factor_scores["breadth"] * 0.15
            + factor_scores["news"] * 0.10
        )
        scored.append(
            ScoredSector(
                name=sector.name,
                score=round(total, 2),
                rank=0,
                pct_change=sector.pct_change,
                factor_scores={key: round(value, 2) for key, value in factor_scores.items()},
            )
        )

    ranked = sorted(scored, key=lambda item: item.score, reverse=True)[:top_n]
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
