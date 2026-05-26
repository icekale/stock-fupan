from app.rules.validation import validate_narrative_facts
from app.schemas.report import (
    IndexSnapshot,
    MarketBreadth,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    SectorCandidate,
)


def make_report(narrative: ReportNarrative) -> ReportDTO:
    return ReportDTO(
        trade_date="2026-05-26",
        kind=ReportKind.CLOSE,
        title="2026.05.26 A股复盘",
        indices=[IndexSnapshot(name="上证指数", code="000001", close=3100.5, pct_change=1.2)],
        breadth=MarketBreadth(up_count=3200, down_count=1800, limit_up_count=86, limit_down_count=8),
        turnover_cny=12345.67,
        market_state_tags=["放量"],
        sectors=[
            SectorCandidate(
                name="机器人",
                score=86.5,
                rank=1,
                pct_change=5.88,
                reason="涨停扩散",
            )
        ],
        narrative=narrative,
    )


def test_validate_narrative_accepts_known_facts() -> None:
    report = make_report(
        ReportNarrative(
            conclusion="上证指数上涨1.2%，机器人板块涨幅5.88%。",
            overview="两市涨停86只，成交额12345.67亿元。",
            sector_commentary=["机器人是今日主线。"],
            watchlist=["关注机器人方向。"],
            tomorrow="观察机器人分歧承接。",
            risks=["涨停86只后高位分歧。"],
        )
    )

    result = validate_narrative_facts(report)

    assert result.is_valid
    assert result.errors == []


def test_validate_narrative_flags_unknown_sector_and_number() -> None:
    report = make_report(
        ReportNarrative(
            conclusion="新能源是今日主线，涨停99只。",
            overview="成交额88888亿元。",
            sector_commentary=[],
            watchlist=[],
            tomorrow="观察。",
            risks=[],
        )
    )

    result = validate_narrative_facts(report)

    assert not result.is_valid
    assert "unknown sector: 新能源" in result.errors
    assert "unknown number: 99" in result.errors
    assert "unknown number: 88888" in result.errors
