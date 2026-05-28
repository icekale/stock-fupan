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
    market_quality = _market_quality_evidence(review_source_results or [])
    predictions = [_prediction_for_sector(report, sector, market_quality) for sector in report.sectors[:max_items]]
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
    market_quality: tuple[str | None, list[str]],
) -> NextDayPrediction:
    source_basis = _curated_sources(sector.review_sources)
    evidence_notes = _evidence_notes(sector)
    board_efficiency, market_quality_basis = market_quality
    front_row = [_stock_focus(stock, position) for position, stock in enumerate(sector.top_stocks, start=1) if stock.name]
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
            primary_basis=_primary_basis(sector),
            secondary_basis=_secondary_basis(source_basis),
            market_quality_basis=market_quality_basis,
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
        primary_basis=_primary_basis(sector),
        secondary_basis=_secondary_basis(source_basis),
        market_quality_basis=market_quality_basis,
        evidence_notes=evidence_notes,
    )


def _curated_sources(sources: list[str]) -> list[str]:
    return [source for source in sources if source in CURATED_REVIEW_SOURCES]


def _primary_basis(sector: SectorCandidate) -> list[str]:
    basis = [f"TickFlow行情：强度{sector.score:.1f}、排名{sector.rank}、板块涨幅{sector.pct_change:+.2f}%"]
    capital_evidence = _capital_evidence_for_sector(sector)
    if capital_evidence is not None:
        basis.append(f"TickFlow资金：{capital_evidence.summary}，资金强度{capital_evidence.strength}")
    news_count = len(_distinct_text(sector.news_summaries))
    if news_count:
        basis.append(f"Anspire新闻：{news_count}条催化")
    return basis


def _secondary_basis(source_basis: list[str]) -> list[str]:
    if not source_basis:
        return []
    return [f"辅助复盘：{'、'.join(source_basis)}"]


def _has_sufficient_evidence(sector: SectorCandidate, source_basis: list[str]) -> bool:
    return bool(source_basis or sector.top_stocks or (sector.rank <= 3 and sector.review_notes))


def _stock_focus(stock: StockCandidate, position: int) -> PredictionStockFocus:
    return PredictionStockFocus(
        code=stock.code,
        name=stock.name,
        pct_change=stock.pct_change,
        turnover_cny=stock.turnover_cny,
        turnover_rate=stock.turnover_rate,
        capital_strength=stock.capital_strength,
        role="前排强势股",
        source_tags=stock.tags,
        observation=_stock_observation(stock, position),
    )


def _stock_observation(stock: StockCandidate, position: int) -> str:
    pct_text = f"涨幅约{stock.pct_change:.2f}%"
    evidence_part = _stock_capital_evidence_text(stock)
    strength_part = f"，{stock.capital_strength}" if stock.capital_strength and stock.capital_strength not in {"强", "温和放量"} else ""
    if _is_20cm_stock(stock):
        return f"{pct_text}{evidence_part}{strength_part}，{_position_context(position)}，观察高弹性前排是否继续领涨，避免冲高回落削弱板块强度。"
    if stock.pct_change >= 9.5:
        return f"{pct_text}{evidence_part}{strength_part}，{_position_context(position)}，观察竞价溢价与开盘承接，确认是否继续维持队形。"
    if stock.pct_change >= 5:
        return f"{pct_text}{evidence_part}{strength_part}，观察放量强势后是否继续保持主动承接。"
    if position >= 4 or stock.pct_change < 2:
        return f"{pct_text}，属于前排中的跟随位，观察是否补涨转强或掉队。"
    return f"{pct_text}{evidence_part}{strength_part}，观察是否继续强于板块平均并承接前排分歧。"


def _stock_capital_evidence_text(stock: StockCandidate) -> str:
    parts = []
    turnover_text = _turnover_text(stock.turnover_cny)
    if turnover_text:
        parts.append(f"成交约{turnover_text}")
    if stock.turnover_rate is not None:
        parts.append(f"换手约{stock.turnover_rate:.2f}%")
    return f"、{'、'.join(parts)}" if parts else ""


def _position_context(position: int) -> str:
    if position == 1:
        return "位于前排领涨位"
    if position <= 3:
        return "位于前排同梯队"
    return "位于前排扩散位"


def _turnover_text(turnover_cny: float | None) -> str:
    if not turnover_cny or turnover_cny <= 0:
        return ""
    if turnover_cny >= 100_000_000:
        return f"{turnover_cny / 100_000_000:.2f}亿"
    return f"{turnover_cny / 10_000:.0f}万"


def _score_breakdown(
    report: ReportDTO,
    sector: SectorCandidate,
    source_basis: list[str],
    board_efficiency: str | None,
) -> PredictionScoreBreakdown:
    review_confirmation = 10 if len(set(source_basis)) >= 2 else 5 if source_basis else 0
    market_strength = round(min(max(sector.score, 0), 100) * 0.35)
    rank_bonus = 5 if sector.rank == 1 else 3 if sector.rank in {2, 3} else 0
    pct_bonus = 5 if sector.pct_change >= 3 else -5 if sector.pct_change <= 0 else 0
    front_row_quality = min(len(sector.top_stocks) * 5, 15)
    if any(_is_20cm_stock(stock) for stock in sector.top_stocks):
        front_row_quality += 4
    if _has_height_evidence(sector):
        front_row_quality += 6
    capital_strength = _capital_strength_points(sector)
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
        + capital_strength
        + board_quality
        + catalyst
        + risk_penalty
    )
    return PredictionScoreBreakdown(
        review_confirmation=review_confirmation,
        market_strength=market_strength + rank_bonus + pct_bonus,
        front_row_quality=front_row_quality,
        capital_strength=capital_strength,
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
    if not source_basis:
        labels.append("复盘源缺失")
    if _has_height_evidence(sector):
        labels.append("高位加速")
    if report.breadth.limit_down_count >= 10 or any(tag in "".join(report.market_state_tags) for tag in HIGH_RISK_MARKET_TAGS):
        labels.append("情绪分歧")
    if not sector.news_summaries:
        labels.append("催化不足")
    if sector.score >= 70 and len(sector.review_notes) <= 1:
        labels.append("后排补涨风险")
    if sector.capital_evidence is not None and sector.capital_evidence.strength == "弱":
        labels.append("资金强度不足")
    if any((stock.turnover_rate or 0) >= 25 and stock.pct_change < 5 for stock in sector.top_stocks):
        labels.append("高换手分歧")
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


def _market_quality_evidence(results: list[ReviewSourceResult]) -> tuple[str | None, list[str]]:
    fallback: ReviewSourceResult | None = None
    for result in results:
        if not result.board_efficiency:
            continue
        if fallback is None:
            fallback = result
        if _board_quality_points(result.board_efficiency) != 0:
            return result.board_efficiency, [_market_quality_note(result)]
    if fallback is None:
        return None, []
    return fallback.board_efficiency, [_market_quality_note(fallback)]


def _market_quality_note(result: ReviewSourceResult) -> str:
    label = "封板率" if "%" in (result.board_efficiency or "") else "封板效率"
    return f"{result.source}：{label}{result.board_efficiency}"


def _board_quality_points(board_efficiency: str | None) -> int:
    if not board_efficiency:
        return 0
    rate_match = re.search(r"([0-9]+(?:\.[0-9]+)?)%", board_efficiency)
    if rate_match:
        rate = float(rate_match.group(1))
        if rate >= 60:
            return 5
        if rate < 50:
            return -5
    if any(word in board_efficiency for word in POSITIVE_BOARD_WORDS):
        return 5
    if any(word in board_efficiency for word in WEAK_BOARD_WORDS):
        return -5
    return 0


def _capital_strength_points(sector: SectorCandidate) -> int:
    evidence = _capital_evidence_for_sector(sector)
    if evidence is None:
        return 0
    if evidence.strength == "强":
        return 8
    if evidence.strength == "中":
        return 4
    return -4


def _capital_evidence_for_sector(sector: SectorCandidate):
    if sector.capital_evidence is not None:
        return sector.capital_evidence
    turnover_values = [stock.turnover_cny for stock in sector.top_stocks if stock.turnover_cny is not None]
    turnover_rate_values = [stock.turnover_rate for stock in sector.top_stocks if stock.turnover_rate is not None]
    if not turnover_values and not turnover_rate_values:
        return None
    front_row_turnover = sum(turnover_values) if turnover_values else None
    avg_turnover_rate = (
        round(sum(turnover_rate_values) / len(turnover_rate_values), 2)
        if turnover_rate_values
        else None
    )
    active_count = sum(
        1
        for stock in sector.top_stocks
        if (stock.turnover_cny or 0) >= 1_000_000_000 or (stock.turnover_rate or 0) >= 5
    )
    strength = _capital_strength_label(front_row_turnover, avg_turnover_rate, active_count)
    summary_parts = []
    if front_row_turnover is not None:
        summary_parts.append(f"前排成交额合计{front_row_turnover / 100_000_000:.2f}亿")
    if avg_turnover_rate is not None:
        summary_parts.append(f"平均换手{avg_turnover_rate:.2f}%")
    summary_parts.append(f"活跃前排{active_count}只")
    return type(
        "DerivedCapitalEvidence",
        (),
        {
            "front_row_turnover_cny": front_row_turnover,
            "avg_turnover_rate": avg_turnover_rate,
            "active_stock_count": active_count,
            "strength": strength,
            "summary": "、".join(summary_parts),
        },
    )()


def _capital_strength_label(
    front_row_turnover: float | None,
    avg_turnover_rate: float | None,
    active_count: int,
) -> str:
    turnover_yi = (front_row_turnover or 0) / 100_000_000
    rate = avg_turnover_rate or 0
    if turnover_yi >= 80 and active_count >= 2 and rate >= 8:
        return "强"
    if turnover_yi >= 30 or active_count >= 2 or rate >= 6:
        return "中"
    return "弱"


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
