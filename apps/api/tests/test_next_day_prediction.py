from app.providers.review_sources import ReviewSourceResult
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
        market_quality_basis=["东方财富涨停复盘：封板率64.21%"],
        primary_basis=["TickFlow行情：强度82.0、排名1、板块涨幅+4.50%", "Anspire新闻：1条催化"],
        secondary_basis=["辅助复盘：同花顺复盘、东方财富涨停复盘"],
    )

    payload = prediction.model_dump(mode="json")

    assert payload["sector"] == "PCB"
    assert payload["confidence"] == "high"
    assert payload["front_row_stocks"][0]["name"] == "胜宏科技"
    assert payload["score_breakdown"]["total"] == 76
    assert payload["market_quality_basis"] == ["东方财富涨停复盘：封板率64.21%"]
    assert payload["primary_basis"] == ["TickFlow行情：强度82.0、排名1、板块涨幅+4.50%", "Anspire新闻：1条催化"]
    assert payload["secondary_basis"] == ["辅助复盘：同花顺复盘、东方财富涨停复盘"]


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


def test_tickflow_and_anspire_are_primary_sources_for_prediction() -> None:
    report = _prediction_report(
        [
            _sector(
                score=86.0,
                pct_change=4.8,
                top_stocks=[
                    StockCandidate(
                        code="300476.SZ",
                        name="胜宏科技",
                        pct_change=20.0,
                        turnover_cny=9_800_000_000,
                        tags=["TickFlow前排"],
                    ),
                    StockCandidate(
                        code="600601.SH",
                        name="方正科技",
                        pct_change=10.0,
                        turnover_cny=2_100_000_000,
                        tags=["TickFlow前排"],
                    ),
                ],
                review_sources=[],
                review_notes=[],
                news_summaries=["PCB 产业链催化延续。"],
            )
        ]
    )

    prediction = build_next_day_predictions(report)[0]

    assert prediction.continuation_probability is not None
    assert prediction.score_breakdown is not None
    assert prediction.score_breakdown.market_strength > prediction.score_breakdown.review_confirmation
    assert "TickFlow行情：强度86.0、排名1、板块涨幅+4.80%" in prediction.primary_basis
    assert "Anspire新闻：1条催化" in prediction.primary_basis
    assert prediction.secondary_basis == []
    assert "复盘源缺失" in prediction.risk_labels


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


def test_front_row_stock_observations_use_available_evidence() -> None:
    report = _prediction_report(
        [
            _sector(
                top_stocks=[
                    StockCandidate(
                        code="000539.SZ",
                        name="粤电力Ａ",
                        pct_change=10.04,
                        turnover_cny=1_247_563_400,
                        turnover_rate=7.2,
                        capital_strength="温和放量",
                        tags=["TickFlow前排"],
                    ),
                    StockCandidate(
                        code="688676.SH",
                        name="金盘科技",
                        pct_change=7.98,
                        turnover_cny=3_893_087_200,
                        turnover_rate=22.5,
                        capital_strength="高换手强承接",
                        tags=["TickFlow前排"],
                    ),
                    StockCandidate(
                        code="600312.SH",
                        name="平高电气",
                        pct_change=0.76,
                        turnover_cny=578_004_600,
                        tags=["TickFlow前排"],
                    ),
                ],
                review_sources=["同花顺复盘"],
                review_notes=["电力方向前排强势。"],
            )
        ]
    )

    stocks = build_next_day_predictions(report)[0].front_row_stocks

    assert stocks[0].observation == "涨幅约10.04%、成交约12.48亿、换手约7.20%，位于前排领涨位，观察竞价溢价与开盘承接，确认是否继续维持队形。"
    assert stocks[1].observation == "涨幅约7.98%、成交约38.93亿、换手约22.50%，高换手强承接，观察放量强势后是否继续保持主动承接。"
    assert stocks[2].observation == "涨幅约0.76%，属于前排中的跟随位，观察是否补涨转强或掉队。"
    assert len({stock.observation for stock in stocks}) == 3


def test_capital_strength_boosts_prediction_and_adds_primary_basis() -> None:
    report = _prediction_report(
        [
            _sector(
                score=72.0,
                pct_change=4.2,
                top_stocks=[
                    StockCandidate(
                        code="688981.SH",
                        name="中芯国际",
                        pct_change=12.3,
                        turnover_cny=18_000_000_000,
                        turnover_rate=9.8,
                        capital_strength="强",
                        tags=["TickFlow前排"],
                    ),
                    StockCandidate(
                        code="600584.SH",
                        name="长电科技",
                        pct_change=10.01,
                        turnover_cny=4_200_000_000,
                        turnover_rate=16.2,
                        capital_strength="强",
                        tags=["TickFlow前排"],
                    ),
                ],
                review_sources=[],
                review_notes=[],
                news_summaries=["先进封装订单景气度延续。"],
            )
        ]
    )

    prediction = build_next_day_predictions(report)[0]

    assert prediction.score_breakdown is not None
    assert prediction.score_breakdown.capital_strength > 0
    assert any("前排成交额合计222.00亿" in item for item in prediction.primary_basis)
    assert any("平均换手13.00%" in item for item in prediction.primary_basis)


def test_limit_up_front_row_observations_include_position_context() -> None:
    report = _prediction_report(
        [
            _sector(
                top_stocks=[
                    StockCandidate(code="000539.SZ", name="粤电力Ａ", pct_change=10.04, tags=["TickFlow前排"]),
                    StockCandidate(code="001299.SZ", name="美能能源", pct_change=10.02, tags=["TickFlow前排"]),
                    StockCandidate(code="600726.SH", name="华电能源", pct_change=9.99, tags=["TickFlow前排"]),
                    StockCandidate(code="600744.SH", name="华银电力", pct_change=9.97, tags=["TickFlow前排"]),
                ],
                review_sources=["同花顺复盘"],
                review_notes=["电力方向前排强势。"],
            )
        ]
    )

    observations = [stock.observation for stock in build_next_day_predictions(report)[0].front_row_stocks]

    assert "领涨位" in observations[0]
    assert "同梯队" in observations[1]
    assert "扩散位" in observations[3]
    assert len(set(observations)) == 4


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


def test_board_efficiency_from_review_sources_adjusts_probability() -> None:
    sector = _sector(
        review_sources=["同花顺复盘"],
        review_notes=["PCB 前排活跃。"],
        news_summaries=["PCB 产业链催化延续。"],
        top_stocks=[StockCandidate(code="300476.SZ", name="胜宏科技", pct_change=20.0, tags=["同花顺复盘"])],
    )
    report = _prediction_report([sector])

    strong = build_next_day_predictions(
        report,
        review_source_results=[
            ReviewSourceResult(
                source="东方财富涨停复盘",
                source_url="https://stock.eastmoney.com/a/cztfp.html",
                status="success",
                board_efficiency="64.21%",
            )
        ],
    )[0]
    weak = build_next_day_predictions(
        report,
        review_source_results=[
            ReviewSourceResult(
                source="东方财富涨停复盘",
                source_url="https://stock.eastmoney.com/a/cztfp.html",
                status="success",
                board_efficiency="45.00%",
            )
        ],
    )[0]

    assert strong.score_breakdown is not None
    assert weak.score_breakdown is not None
    assert strong.score_breakdown.board_quality == 5
    assert weak.score_breakdown.board_quality == -5
    assert strong.continuation_probability == weak.continuation_probability + 10
    assert strong.source_basis == ["同花顺复盘"]
    assert strong.market_quality_basis == ["东方财富涨停复盘：封板率64.21%"]


def test_board_efficiency_prefers_actionable_review_source_value() -> None:
    sector = _sector(
        review_sources=["同花顺复盘"],
        review_notes=["PCB 前排活跃。"],
        news_summaries=["PCB 产业链催化延续。"],
        top_stocks=[StockCandidate(code="300476.SZ", name="胜宏科技", pct_change=20.0, tags=["同花顺复盘"])],
    )
    report = _prediction_report([sector])

    prediction = build_next_day_predictions(
        report,
        review_source_results=[
            ReviewSourceResult(
                source="同花顺复盘",
                source_url="https://stock.10jqka.com.cn/fupan/",
                status="success",
                board_efficiency="一般",
            ),
            ReviewSourceResult(
                source="东方财富涨停复盘",
                source_url="https://stock.eastmoney.com/a/cztfp.html",
                status="success",
                board_efficiency="64.21%",
            ),
        ],
    )[0]

    assert prediction.score_breakdown is not None
    assert prediction.score_breakdown.board_quality == 5
    assert prediction.market_quality_basis == ["东方财富涨停复盘：封板率64.21%"]
