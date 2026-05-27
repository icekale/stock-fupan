from app.schemas.report import (
    IndexSnapshot,
    MarketBreadth,
    NextDayPrediction,
    PredictionConfidence,
    PredictionScoreBreakdown,
    PredictionStockFocus,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    SectorCandidate,
    StockCandidate,
)
from app.services.next_day_prediction import build_next_day_predictions


def test_next_day_prediction_schema_serializes_core_fields() -> None:
    prediction = NextDayPrediction(
        sector="PCB",
        rank=1,
        continuation_probability=76,
        confidence=PredictionConfidence.HIGH,
        headline="PCB 延续概率较高，观察前排承接。",
        front_row_stocks=[
            PredictionStockFocus(
                code="300476.SZ",
                name="胜宏科技",
                pct_change=20.0,
                role="前排强势股",
                source_tags=["同花顺复盘", "东方财富涨停复盘"],
                observation="观察胜宏科技竞价是否强于板块平均。",
            )
        ],
        trigger_conditions=["观察胜宏科技竞价是否强于板块平均。"],
        invalidation_conditions=["前排股集体低开低走。"],
        risk_labels=["高位加速"],
        score_breakdown=PredictionScoreBreakdown(
            review_confirmation=15,
            market_strength=20,
            front_row_quality=15,
            board_quality=5,
            catalyst=5,
            risk_penalty=-5,
            total=76,
        ),
        source_basis=["同花顺复盘", "东方财富涨停复盘"],
        evidence_notes=["两家复盘源共同确认 PCB 强势。"],
    )

    payload = prediction.model_dump(mode="json")

    assert payload["sector"] == "PCB"
    assert payload["confidence"] == "high"
    assert payload["front_row_stocks"][0]["name"] == "胜宏科技"
    assert payload["score_breakdown"]["total"] == 76


def _prediction_report(sectors: list[SectorCandidate]) -> ReportDTO:
    return ReportDTO(
        trade_date="2026-05-27",
        kind=ReportKind.CLOSE,
        title="2026-05-27 A股复盘",
        indices=[IndexSnapshot(name="上证指数", code="000001", close=4145.37, pct_change=0.5)],
        breadth=MarketBreadth(up_count=3200, down_count=1800, limit_up_count=86, limit_down_count=4),
        turnover_cny=12345.67,
        market_state_tags=["放量", "分化"],
        sectors=sectors,
        narrative=ReportNarrative(
            conclusion="",
            overview="",
            sector_commentary=[],
            watchlist=[],
            tomorrow="",
            risks=[],
        ),
        news=[],
    )


def _sector(
    *,
    name: str = "PCB",
    rank: int = 1,
    score: float = 82.0,
    pct_change: float = 4.5,
    top_stocks: list[StockCandidate] | None = None,
    news_summaries: list[str] | None = None,
    review_sources: list[str] | None = None,
    review_notes: list[str] | None = None,
) -> SectorCandidate:
    return SectorCandidate(
        name=name,
        score=score,
        rank=rank,
        pct_change=pct_change,
        reason="强度与复盘源共同确认",
        top_stocks=top_stocks or [],
        news_summaries=news_summaries or [],
        factor_scores={"limit_up": 80.0, "pct_change": 70.0},
        review_sources=review_sources or [],
        review_notes=review_notes or [],
    )


def test_double_source_sector_gets_high_confidence_prediction() -> None:
    report = _prediction_report(
        [
            _sector(
                top_stocks=[
                    StockCandidate(
                        code="300476.SZ",
                        name="胜宏科技",
                        pct_change=20.0,
                        tags=["同花顺复盘", "东方财富涨停复盘", "20CM"],
                    ),
                    StockCandidate(
                        code="600601.SH",
                        name="方正科技",
                        pct_change=10.0,
                        tags=["东方财富涨停复盘"],
                    ),
                ],
                news_summaries=["PCB 产业链催化延续。"],
                review_sources=["同花顺复盘", "东方财富涨停复盘"],
                review_notes=["PCB 方向前排强势，封板效率较高。"],
            )
        ]
    )

    predictions = build_next_day_predictions(report)

    assert predictions[0].sector == "PCB"
    assert predictions[0].continuation_probability is not None
    assert predictions[0].continuation_probability >= 70
    assert predictions[0].confidence == PredictionConfidence.HIGH
    assert predictions[0].source_basis == ["同花顺复盘", "东方财富涨停复盘"]


def test_no_curated_evidence_produces_insufficient_prediction() -> None:
    report = _prediction_report([_sector(review_sources=[], review_notes=[], top_stocks=[])])

    predictions = build_next_day_predictions(report)

    assert predictions[0].continuation_probability is None
    assert predictions[0].confidence == PredictionConfidence.INSUFFICIENT
    assert "证据不足" in predictions[0].headline


def test_front_row_stock_names_appear_in_trigger_conditions() -> None:
    report = _prediction_report(
        [
            _sector(
                top_stocks=[
                    StockCandidate(code="300476.SZ", name="胜宏科技", pct_change=20.0, tags=["同花顺复盘"]),
                    StockCandidate(code="600601.SH", name="方正科技", pct_change=10.0, tags=["东方财富涨停复盘"]),
                ],
                review_sources=["同花顺复盘"],
                review_notes=["PCB 前排强势。"],
            )
        ]
    )

    predictions = build_next_day_predictions(report)
    condition_text = "\n".join(predictions[0].trigger_conditions)

    assert "胜宏科技" in condition_text or "方正科技" in condition_text


def test_risk_labels_are_deterministic() -> None:
    report = _prediction_report(
        [
            _sector(
                review_sources=["同花顺复盘"],
                review_notes=["PCB 前排活跃。"],
                news_summaries=[],
                top_stocks=[],
            )
        ]
    )

    predictions = build_next_day_predictions(report)

    assert "单源确认" in predictions[0].risk_labels
    assert "催化不足" in predictions[0].risk_labels


def test_empty_report_generates_no_prediction_content() -> None:
    report = _prediction_report([])

    assert build_next_day_predictions(report) == []
