from app.rules.validation import validate_narrative_facts
from app.schemas.report import (
    IndexSnapshot,
    MarketBreadth,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    SectorCandidate,
    StockCandidate,
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


def test_validate_narrative_ignores_dates_codes_sections_and_prose_numbers() -> None:
    report = make_report(
        ReportNarrative(
            conclusion="2026-05-26复盘，第1部分关注000001，普通描述里有3个观察点。",
            overview="代码000001对应上证指数，明天再看2个方向。",
            sector_commentary=[],
            watchlist=[],
            tomorrow="第2节继续观察。",
            risks=[],
        )
    )

    result = validate_narrative_facts(report)

    assert not any(error.startswith("unknown number:") for error in result.errors)


def test_validate_narrative_accepts_signed_percent_and_trailing_zero_known_numbers() -> None:
    report = make_report(
        ReportNarrative(
            conclusion="上证指数上涨+1.20%，机器人涨幅+5.880％。",
            overview="涨停86.0只，成交额12,345.670亿元。",
            sector_commentary=[],
            watchlist=[],
            tomorrow="观察机器人方向。",
            risks=[],
        )
    )

    result = validate_narrative_facts(report)

    assert result.is_valid
    assert result.errors == []


def test_validate_narrative_accepts_turnover_in_wan_yi() -> None:
    report = make_report(
        ReportNarrative(
            conclusion="机器人是今日主线。",
            overview="成交额约1.23万亿。",
            sector_commentary=[],
            watchlist=[],
            tomorrow="观察机器人分歧承接。",
            risks=[],
        )
    )

    result = validate_narrative_facts(report)

    assert result.is_valid
    assert result.errors == []


def test_validate_narrative_flags_unknown_stock_and_index_names() -> None:
    report = make_report(
        ReportNarrative(
            conclusion="创业板指走强，未来科技涨停。",
            overview="上证指数上涨1.2%。",
            sector_commentary=[],
            watchlist=[],
            tomorrow="观察未来科技承接。",
            risks=[],
        )
    )

    result = validate_narrative_facts(report)

    assert "unknown index: 创业板指" in result.errors
    assert "unknown stock: 未来科技" in result.errors


def test_validate_narrative_accepts_known_top_stock_and_index_names() -> None:
    report = make_report(
        ReportNarrative(
            conclusion="上证指数上涨1.2%，机器人科技涨幅10.00%。",
            overview="代码000001与300001同步走强。",
            sector_commentary=[],
            watchlist=["关注机器人科技。"],
            tomorrow="观察机器人方向。",
            risks=[],
        )
    )
    report.sectors[0].top_stocks = [
        StockCandidate(code="300001", name="机器人科技", pct_change=10.0)
    ]

    result = validate_narrative_facts(report)

    assert result.is_valid
    assert result.errors == []


def test_validate_narrative_dedupes_unknown_values_and_avoids_sector_overlap() -> None:
    report = make_report(
        ReportNarrative(
            conclusion="电力设备活跃，未来科技涨停99只。",
            overview="未来科技继续涨停99只。",
            sector_commentary=[],
            watchlist=[],
            tomorrow="观察未来科技。",
            risks=[],
        )
    )

    result = validate_narrative_facts(report)

    assert result.errors.count("unknown sector: 电力") == 0
    assert result.errors.count("unknown stock: 未来科技") == 1
    assert result.errors.count("unknown number: 99") == 1
