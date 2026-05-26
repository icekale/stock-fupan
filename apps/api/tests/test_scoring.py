import math

from app.rules.scoring import RawSectorInput, score_sectors
from app.schemas.report import (
    IndexSnapshot,
    MarketBreadth,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    SectorCandidate,
    StockCandidate,
)


def test_report_dto_serializes_core_fields() -> None:
    dto = ReportDTO(
        trade_date="2026-05-26",
        kind=ReportKind.CLOSE,
        title="2026.05.26 A股复盘",
        indices=[
            IndexSnapshot(name="上证指数", code="000001", pct_change=1.2, close=3100.5),
        ],
        breadth=MarketBreadth(up_count=3200, down_count=1800, limit_up_count=86, limit_down_count=8),
        turnover_cny=12345.67,
        market_state_tags=["放量", "分化"],
        sectors=[
            SectorCandidate(
                name="机器人",
                score=86.5,
                rank=1,
                pct_change=5.88,
                reason="涨停扩散",
                top_stocks=[
                    StockCandidate(
                        code="300001",
                        name="示例股份",
                        pct_change=20.0,
                        turnover_cny=12.3,
                        tags=["20cm"],
                    )
                ],
                news_summaries=["机器人产业链催化增强"],
            )
        ],
        narrative=ReportNarrative(
            conclusion="市场高热分化。",
            overview="成交放大。",
            sector_commentary=["机器人方向最强。"],
            watchlist=["观察核心容量股承接。"],
            tomorrow="关注分歧后的承接。",
            risks=["高位分歧加大。"],
        ),
    )

    dumped = dto.model_dump()

    assert dumped["kind"] == "close"
    assert dumped["sectors"][0]["top_stocks"][0]["name"] == "示例股份"
    assert dumped["narrative"]["risks"] == ["高位分歧加大。"]


def test_score_sectors_ranks_by_short_term_strength() -> None:
    sectors = [
        RawSectorInput(
            name="低位防御",
            pct_change=2.0,
            limit_up_count=1,
            stock_up_ratio=0.55,
            turnover_change=0.1,
            news_weight=0.1,
        ),
        RawSectorInput(
            name="机器人",
            pct_change=5.88,
            limit_up_count=8,
            stock_up_ratio=0.82,
            turnover_change=0.35,
            news_weight=0.8,
        ),
    ]

    scored = score_sectors(sectors)

    assert [sector.name for sector in scored] == ["机器人", "低位防御"]
    assert scored[0].rank == 1
    assert scored[0].algorithm_version == "sector_score_v1"
    assert scored[0].factor_scores["limit_up"] > scored[1].factor_scores["limit_up"]


def test_score_sectors_caps_to_top_n() -> None:
    sectors = [
        RawSectorInput(
            name=f"板块{i}",
            pct_change=float(i),
            limit_up_count=i,
            stock_up_ratio=0.5,
            turnover_change=0.1,
            news_weight=0.0,
        )
        for i in range(8)
    ]

    scored = score_sectors(sectors, top_n=5)

    assert len(scored) == 5
    assert scored[0].name == "板块7"


def test_score_sectors_returns_empty_for_non_positive_top_n() -> None:
    sectors = [
        RawSectorInput(
            name=f"板块{i}",
            pct_change=5.0,
            limit_up_count=8,
            stock_up_ratio=0.8,
            turnover_change=0.3,
            news_weight=0.5,
        )
        for i in range(2)
    ]

    assert score_sectors(sectors, top_n=0) == []
    assert score_sectors(sectors, top_n=-1) == []


def test_score_sectors_orders_ties_by_name() -> None:
    sectors = [
        RawSectorInput(
            name="B板块",
            pct_change=1.0,
            limit_up_count=2,
            stock_up_ratio=0.5,
            turnover_change=0.1,
            news_weight=0.0,
        ),
        RawSectorInput(
            name="A板块",
            pct_change=1.0,
            limit_up_count=2,
            stock_up_ratio=0.5,
            turnover_change=0.1,
            news_weight=0.0,
        ),
    ]

    scored = score_sectors(sectors)

    assert [sector.name for sector in scored] == ["A板块", "B板块"]


def test_score_sectors_treats_non_finite_inputs_as_minimum() -> None:
    sectors = [
        RawSectorInput(
            name="异常值",
            pct_change=float("inf"),
            limit_up_count=10,
            stock_up_ratio=float("nan"),
            turnover_change=float("-inf"),
            news_weight=float("inf"),
        )
    ]

    scored = score_sectors(sectors)

    assert scored[0].factor_scores == {
        "pct_change": 0.0,
        "limit_up": 100.0,
        "breadth": 0.0,
        "turnover": 0.0,
        "news": 0.0,
    }
    assert scored[0].score == 35.0
    assert math.isfinite(scored[0].score)
    assert math.isfinite(scored[0].pct_change)
    assert all(math.isfinite(value) for value in scored[0].factor_scores.values())


def test_score_sectors_calculates_expected_factor_scores() -> None:
    sectors = [
        RawSectorInput(
            name="公式校验",
            pct_change=4.0,
            limit_up_count=5,
            stock_up_ratio=0.6,
            turnover_change=0.2,
            news_weight=0.3,
        )
    ]

    scored = score_sectors(sectors)

    assert scored[0].factor_scores == {
        "pct_change": 50.0,
        "limit_up": 50.0,
        "breadth": 60.0,
        "turnover": 50.0,
        "news": 30.0,
    }
    expected_score = round(
        50.0 * 0.35 + 50.0 * 0.20 + 50.0 * 0.20 + 60.0 * 0.15 + 30.0 * 0.10,
        2,
    )
    assert scored[0].score == expected_score
