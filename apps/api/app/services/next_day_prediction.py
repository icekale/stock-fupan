import re

from app.providers.review_sources import ReviewSourceResult
from app.schemas.report import (
    NextDayPrediction,
    PredictionConfidence,
    PredictionScoreBreakdown,
    PredictionStockFocus,
    ReportDTO,
    SectorCandidate,
    StockCandidate,
)

CURATED_REVIEW_SOURCES = {"同花顺复盘", "东方财富涨停复盘"}
HEIGHT_PATTERN = re.compile(r"(?:\d+板|\d+天\d+板|连板|高度)")
POSITIVE_BOARD_WORDS = ("高", "强", "较好")
WEAK_BOARD_WORDS = ("低", "弱", "较差")
HIGH_RISK_MARKET_TAGS = ("分化", "退潮", "缩量")


def build_next_day_predictions(
    report: ReportDTO,
    review_source_results: list[ReviewSourceResult] | None = None,
    max_items: int = 5,
) -> list[NextDayPrediction]:
    if max_items <= 0 or not report.sectors:
        return []
    board_efficiency = _board_efficiency(review_source_results or [])
    predictions = [_prediction_for_sector(report, sector, board_efficiency) for sector in report.sectors[:max_items]]
    return sorted(
        predictions,
        key=lambda item: (
            item.continuation_probability is not None,
            item.continuation_probability or -1,
            -item.rank,
        ),
        reverse=True,
    )


def _prediction_for_sector(
    report: ReportDTO,
    sector: SectorCandidate,
    board_efficiency: str | None,
) -> NextDayPrediction:
    source_basis = _curated_sources(sector.review_sources)
    evidence_notes = _evidence_notes(sector)
    front_row = [_stock_focus(stock) for stock in sector.top_stocks if stock.name]
    if not _has_sufficient_evidence(sector, source_basis):
        return NextDayPrediction(
            sector=sector.name,
            rank=sector.rank,
            continuation_probability=None,
            confidence=PredictionConfidence.INSUFFICIENT,
            headline="证据不足，仅保留观察",
            front_row_stocks=front_row,
            trigger_conditions=_insufficient_trigger_conditions(sector),
            invalidation_conditions=_invalidation_conditions(report, sector),
            risk_labels=_risk_labels(report, sector, source_basis),
            score_breakdown=None,
            source_basis=source_basis,
            evidence_notes=evidence_notes,
        )

    breakdown = _score_breakdown(report, sector, source_basis, board_efficiency)
    probability = breakdown.total
    return NextDayPrediction(
        sector=sector.name,
        rank=sector.rank,
        continuation_probability=probability,
        confidence=_confidence(probability),
        headline=_headline(sector.name, probability),
        front_row_stocks=front_row,
        trigger_conditions=_trigger_conditions(report, sector),
        invalidation_conditions=_invalidation_conditions(report, sector),
        risk_labels=_risk_labels(report, sector, source_basis),
        score_breakdown=breakdown,
        source_basis=source_basis,
        evidence_notes=evidence_notes,
    )


def _curated_sources(sources: list[str]) -> list[str]:
    return [source for source in sources if source in CURATED_REVIEW_SOURCES]


def _has_sufficient_evidence(sector: SectorCandidate, source_basis: list[str]) -> bool:
    return bool(source_basis or sector.top_stocks or (sector.rank <= 3 and sector.review_notes))


def _stock_focus(stock: StockCandidate) -> PredictionStockFocus:
    return PredictionStockFocus(
        code=stock.code,
        name=stock.name,
        pct_change=stock.pct_change,
        role="前排强势股",
        source_tags=stock.tags,
        observation=f"观察{stock.name}竞价与开盘承接是否强于板块平均。",
    )


def _score_breakdown(
    report: ReportDTO,
    sector: SectorCandidate,
    source_basis: list[str],
    board_efficiency: str | None,
) -> PredictionScoreBreakdown:
    review_confirmation = 15 if len(set(source_basis)) >= 2 else 8 if source_basis else 0
    market_strength = round(min(max(sector.score, 0), 100) * 0.25)
    rank_bonus = 5 if sector.rank == 1 else 3 if sector.rank in {2, 3} else 0
    pct_bonus = 5 if sector.pct_change >= 3 else -5 if sector.pct_change <= 0 else 0
    front_row_quality = min(len(sector.top_stocks) * 5, 15)
    if any(_is_20cm_stock(stock) for stock in sector.top_stocks):
        front_row_quality += 4
    if _has_height_evidence(sector):
        front_row_quality += 6
    board_quality = _board_quality_points(board_efficiency)
    catalyst = 8 if len(_distinct_text(sector.news_summaries)) >= 2 else 5 if sector.news_summaries else 0
    risk_penalty = _risk_penalty(report, sector)
    total = _clamp_int(
        35
        + review_confirmation
        + market_strength
        + rank_bonus
        + pct_bonus
        + front_row_quality
        + board_quality
        + catalyst
        + risk_penalty
    )
    return PredictionScoreBreakdown(
        review_confirmation=review_confirmation,
        market_strength=market_strength + rank_bonus + pct_bonus,
        front_row_quality=front_row_quality,
        board_quality=board_quality,
        catalyst=catalyst,
        risk_penalty=risk_penalty,
        total=total,
    )


def _risk_penalty(report: ReportDTO, sector: SectorCandidate) -> int:
    penalty = 0
    if not sector.top_stocks:
        penalty -= 10
    if len(sector.review_notes) <= 1 and not sector.news_summaries:
        penalty -= 5
    if report.breadth.limit_down_count >= 10 or any(tag in "".join(report.market_state_tags) for tag in HIGH_RISK_MARKET_TAGS):
        penalty -= 5
    return penalty


def _risk_labels(report: ReportDTO, sector: SectorCandidate, source_basis: list[str]) -> list[str]:
    labels: list[str] = []
    if not sector.top_stocks:
        labels.append("前排缺失")
    if len(set(source_basis)) == 1:
        labels.append("单源确认")
    if _has_height_evidence(sector):
        labels.append("高位加速")
    if report.breadth.limit_down_count >= 10 or any(tag in "".join(report.market_state_tags) for tag in HIGH_RISK_MARKET_TAGS):
        labels.append("情绪分歧")
    if not sector.news_summaries:
        labels.append("催化不足")
    if sector.score >= 70 and len(sector.review_notes) <= 1:
        labels.append("后排补涨风险")
    return _dedupe(labels)


def _trigger_conditions(report: ReportDTO, sector: SectorCandidate) -> list[str]:
    stocks = [stock.name for stock in sector.top_stocks if stock.name][:3]
    stock_text = "、".join(stocks)
    first = (
        f"观察{stock_text}竞价是否强于板块平均。"
        if stock_text
        else "暂未解析到明确前排股，需先确认板块内主动领涨标的。"
    )
    return [
        first,
        f"观察{sector.name}是否继续处于市场强势组前列。",
        "指数不出现明显放量下杀，成交额维持活跃区间。",
        "前排分歧温和，板块内不出现集体负反馈。",
    ]


def _insufficient_trigger_conditions(sector: SectorCandidate) -> list[str]:
    return [
        "同花顺/东方财富复盘证据不足，暂不生成强势概率。",
        f"需要先确认{sector.name}是否有明确前排股和复盘源确认。",
        "仅保留观察，不把市场排名单独当作延续依据。",
    ]


def _invalidation_conditions(report: ReportDTO, sector: SectorCandidate) -> list[str]:
    stocks = [stock.name for stock in sector.top_stocks if stock.name][:3]
    stock_text = "、".join(stocks) if stocks else "前排股"
    return [
        f"{stock_text}集体低开低走。",
        f"{sector.name}高开后快速跌出强势排名。",
        "指数放量下杀且高位股开板反馈扩大。",
        "催化消息不能映射到价格强度。",
    ]


def _headline(sector_name: str, probability: int) -> str:
    if probability >= 70:
        return f"{sector_name}延续概率较高，重点观察前排分歧承接。"
    if probability >= 50:
        return f"{sector_name}处于延续观察区，需要前排确认。"
    return f"{sector_name}延续条件偏弱，优先等待确认。"


def _confidence(probability: int) -> PredictionConfidence:
    if probability >= 70:
        return PredictionConfidence.HIGH
    if probability >= 50:
        return PredictionConfidence.MEDIUM
    return PredictionConfidence.LOW


def _evidence_notes(sector: SectorCandidate) -> list[str]:
    return _dedupe([*sector.review_notes, *sector.news_summaries])[:4]


def _board_efficiency(results: list[ReviewSourceResult]) -> str | None:
    for result in results:
        if result.board_efficiency:
            return result.board_efficiency
    return None


def _board_quality_points(board_efficiency: str | None) -> int:
    if not board_efficiency:
        return 0
    if any(word in board_efficiency for word in POSITIVE_BOARD_WORDS):
        return 5
    if any(word in board_efficiency for word in WEAK_BOARD_WORDS):
        return -5
    return 0


def _is_20cm_stock(stock: StockCandidate) -> bool:
    tag_text = " ".join(stock.tags)
    return stock.pct_change >= 19.5 or "20CM" in tag_text.upper()


def _has_height_evidence(sector: SectorCandidate) -> bool:
    text = "\n".join([*sector.review_notes, *(tag for stock in sector.top_stocks for tag in stock.tags)])
    return bool(HEIGHT_PATTERN.search(text))


def _distinct_text(values: list[str]) -> list[str]:
    return _dedupe([value.strip() for value in values if value.strip()])


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _clamp_int(value: int) -> int:
    return max(0, min(100, int(round(value))))
