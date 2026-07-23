from app.rules.validation import ValidationResult
from app.schemas.report import (
    IndexSnapshot,
    MarketBreadth,
    NewsItem,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    SectorCandidate,
    StockCandidate,
)
from app.schemas.structured_review import HistoricalThemeReview


def make_report(kind: ReportKind = ReportKind.CLOSE) -> ReportDTO:
    return ReportDTO(
        trade_date="2026-06-03",
        kind=kind,
        title="2026-06-03-全日盘后复盘",
        indices=[IndexSnapshot(name="上证指数", code="000001", close=4100.0, pct_change=1.0)],
        breadth=MarketBreadth(up_count=3200, down_count=1800, limit_up_count=80, limit_down_count=5),
        turnover_cny=12000.0,
        market_state_tags=["放量"],
        sectors=[
            SectorCandidate(
                name="机器人",
                score=88,
                rank=1,
                pct_change=5.2,
                reason="综合评分靠前",
                top_stocks=[StockCandidate(code="300001", name="机器人科技", pct_change=10.0)],
                news_summaries=["机器人产业催化"],
            ),
            SectorCandidate(
                name="半导体",
                score=80,
                rank=2,
                pct_change=3.2,
                reason="综合评分靠前",
                top_stocks=[StockCandidate(code="300002", name="半导体科技", pct_change=8.0)],
                news_summaries=["半导体产业催化"],
            ),
        ],
        news=[
            NewsItem(
                title="机器人产业催化",
                url="https://example.com/robot",
                source="Anspire",
                summary="机器人产业催化",
                matched_sector="机器人",
            ),
            NewsItem(
                title="半导体产业催化",
                url="https://example.com/chip",
                source="Anspire",
                summary="半导体产业催化",
                matched_sector="半导体",
            ),
        ],
        previous_strong_themes=[
            HistoricalThemeReview(
                theme="机器人",
                previous_status="昨日持续性高",
                current_status="今日继续进入前排",
                judgement="延续确认",
                evidence=["昨日机器人方向强势"],
            )
        ],
        narrative=ReportNarrative(
            conclusion="机器人和半导体领涨。",
            overview="市场放量。",
            sector_commentary=["机器人方向有前排承接。"],
            watchlist=[],
            tomorrow="观察分歧承接。",
            risks=[],
        ),
    )


def success_provider_status() -> dict[str, object]:
    return {
        "market": {"provider": "tickflow", "status": "success", "fallback_used": False, "reason": None},
        "news": [
            {"sector": "机器人", "provider": "anspire", "status": "success", "fallback_used": False},
            {"sector": "半导体", "provider": "anspire", "status": "success", "fallback_used": False},
        ],
        "review_sources": [
            {"source": "同花顺复盘", "status": "success", "reason": None, "theme_count": 2},
            {"source": "东方财富涨停复盘", "status": "success", "reason": None, "theme_count": 1},
        ],
    }


def test_quality_gate_marks_complete_close_report_publishable() -> None:
    from app.rules.quality_gate import evaluate_quality_gate

    result = evaluate_quality_gate(
        report=make_report(),
        validation=ValidationResult(is_valid=True, errors=[]),
        provider_status=success_provider_status(),
        structured_review_status={"provider": "rule", "status": "success", "fallback_used": False},
    )

    assert result.score == 100
    assert result.publish_status == "publishable"
    assert result.hard_failures == []
    assert result.warnings == []
    assert result.provider_summary["fake_fallback_used"] is False


def test_quality_gate_degrades_partial_news_and_review_source_failures() -> None:
    from app.rules.quality_gate import evaluate_quality_gate

    provider_status = success_provider_status()
    provider_status["news"] = [
        {"sector": "机器人", "provider": "anspire", "status": "success", "fallback_used": False},
        {"sector": "半导体", "provider": "anspire", "status": "failed", "fallback_used": False},
    ]
    provider_status["review_sources"] = [
        {"source": "同花顺复盘", "status": "success", "reason": None, "theme_count": 1},
        {"source": "东方财富涨停复盘", "status": "failed", "reason": "empty", "theme_count": 0},
    ]

    result = evaluate_quality_gate(
        report=make_report(),
        validation=ValidationResult(is_valid=True, errors=[]),
        provider_status=provider_status,
        structured_review_status={"provider": "rule", "status": "success", "fallback_used": False},
    )

    assert result.score == 90
    assert result.publish_status == "publishable"
    assert [issue.code for issue in result.warnings] == [
        "news_partial_failed",
        "review_sources_partial_failed",
    ]


def test_quality_gate_degrades_when_board_rank_source_fails() -> None:
    from app.rules.quality_gate import evaluate_quality_gate

    provider_status = success_provider_status()
    provider_status["review_sources"] = [
        {"source": "同花顺复盘", "status": "success", "reason": None, "theme_count": 1},
        {
            "source": "a-stock-data 东财板块排名",
            "status": "failed",
            "reason": "Server disconnected",
            "theme_count": 0,
        },
    ]

    result = evaluate_quality_gate(
        report=make_report(),
        validation=ValidationResult(is_valid=True, errors=[]),
        provider_status=provider_status,
        structured_review_status={"provider": "rule", "status": "success", "fallback_used": False},
    )

    assert result.publish_status == "degraded"
    assert result.score < 85
    assert "board_rank_source_failed" in [issue.code for issue in result.warnings]


def test_quality_gate_warns_when_enabled_dragon_tiger_source_fails() -> None:
    from app.rules.quality_gate import evaluate_quality_gate

    provider_status = success_provider_status()
    provider_status["review_sources"].append(
        {
            "source": "a-stock-data 东财龙虎榜",
            "source_url": "https://data.eastmoney.com/stock/lhb.html",
            "status": "failed",
            "reason": "东财龙虎榜无结果",
            "record_count": 0,
            "seat_detail_count": 0,
        }
    )

    result = evaluate_quality_gate(
        report=make_report(),
        validation=ValidationResult(is_valid=True, errors=[]),
        provider_status=provider_status,
        structured_review_status={"provider": "rule", "status": "success", "fallback_used": False},
    )

    assert any(issue.code == "dragon_tiger_source_failed" for issue in result.warnings)
    assert result.score is not None
    assert result.score <= 95


def test_quality_gate_does_not_warn_when_dragon_tiger_source_is_disabled() -> None:
    from app.rules.quality_gate import evaluate_quality_gate

    provider_status = success_provider_status()
    provider_status["review_sources"].append(
        {
            "source": "a-stock-data 东财龙虎榜",
            "status": "disabled",
            "reason": None,
            "record_count": 0,
            "seat_detail_count": 0,
        }
    )

    result = evaluate_quality_gate(
        report=make_report(),
        validation=ValidationResult(is_valid=True, errors=[]),
        provider_status=provider_status,
        structured_review_status={"provider": "rule", "status": "success", "fallback_used": False},
    )

    assert all(issue.code != "dragon_tiger_source_failed" for issue in result.warnings)
    assert result.score == 100


def test_quality_gate_blocks_fake_market_and_missing_front_row() -> None:
    from app.rules.quality_gate import evaluate_quality_gate

    report = make_report()
    report.sectors[0].top_stocks = []
    provider_status = success_provider_status()
    provider_status["market"] = {
        "provider": "fake",
        "status": "fallback",
        "fallback_used": True,
        "reason": "TickFlow HTTP 500",
    }

    result = evaluate_quality_gate(
        report=report,
        validation=ValidationResult(is_valid=True, errors=[]),
        provider_status=provider_status,
        structured_review_status={"provider": "rule", "status": "success", "fallback_used": False},
    )

    assert result.publish_status == "blocked"
    assert result.score < 70
    assert [issue.code for issue in result.hard_failures] == [
        "market_source_untrusted",
        "top_sector_missing_front_row",
    ]


def test_quality_gate_blocks_fact_validation_failures() -> None:
    from app.rules.quality_gate import evaluate_quality_gate

    result = evaluate_quality_gate(
        report=make_report(),
        validation=ValidationResult(is_valid=False, errors=["unknown stock: 未来科技"]),
        provider_status=success_provider_status(),
        structured_review_status={"provider": "rule", "status": "success", "fallback_used": False},
    )

    assert result.publish_status == "blocked"
    assert result.hard_failures[0].code == "fact_validation_failed"
    assert result.hard_failures[0].details == {"errors": ["unknown stock: 未来科技"]}


def test_quality_gate_marks_midday_and_weekly_not_applicable() -> None:
    from app.rules.quality_gate import evaluate_quality_gate

    for kind in (ReportKind.MIDDAY, ReportKind.WEEKLY):
        result = evaluate_quality_gate(
            report=make_report(kind=kind),
            validation=ValidationResult(is_valid=True, errors=[]),
            provider_status=success_provider_status(),
            structured_review_status={"provider": "rule", "status": "success", "fallback_used": False},
        )

        assert result.score is None
        assert result.publish_status == "not_applicable"
        assert result.summary == "该报告类型暂不接入质量门禁"
