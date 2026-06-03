import math

from app.rules.scoring import RawSectorInput, score_sectors
from app.schemas.report import (
    DragonTigerSeat,
    DragonTigerStock,
    DragonTigerSummary,
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


def test_report_dto_serializes_dragon_tiger_summary() -> None:
    report = ReportDTO(
        trade_date="2026-06-03",
        kind=ReportKind.CLOSE,
        title="2026-06-03-全日盘后复盘",
        indices=[IndexSnapshot(name="上证指数", code="000001", close=3100.5, pct_change=1.2)],
        breadth=MarketBreadth(up_count=3000, down_count=1800, limit_up_count=60, limit_down_count=3),
        turnover_cny=12000,
        market_state_tags=["结构性修复"],
        sectors=[],
        narrative=ReportNarrative(
            conclusion="短线情绪回暖。",
            overview="指数修复。",
            sector_commentary=[],
            watchlist=[],
            tomorrow="观察承接。",
            risks=[],
        ),
        news=[],
        dragon_tiger=DragonTigerSummary(
            trade_date="2026-06-03",
            source="a-stock-data 东财龙虎榜",
            source_url="https://data.eastmoney.com/stock/lhb.html",
            status="success",
            total_records=91,
            positive_net_count=55,
            negative_net_count=36,
            net_buy_total_wan=268081.1,
            institution_net_buy_wan=19867.4,
            connect_net_buy_wan=82845.9,
            mainline_match_count=2,
            mainline_match_names=["通富微电", "亨通光电"],
            sentiment="strong",
            strength="high",
            conclusion="龙虎榜净买集中在核心方向。",
            risk_notes=["若次日前排高开低走，说明分歧扩大。"],
            top_net_buy=[
                DragonTigerStock(
                    code="002156",
                    name="通富微电",
                    reason="日涨幅偏离值达到7%的前5只证券",
                    close=70.22,
                    change_pct=9.9937,
                    turnover_pct=11.6315,
                    net_buy_wan=162241.5,
                    buy_wan=250982.5,
                    sell_wan=88740.9,
                    seats_buy=[
                        DragonTigerSeat(
                            name="深股通专用",
                            buy_wan=123598.9,
                            sell_wan=40753.0,
                            net_wan=82845.9,
                            role="northbound",
                        )
                    ],
                    seats_sell=[],
                    tags=["净买额Top"],
                )
            ],
            top_net_sell=[],
            highlighted_stocks=[],
        ),
    )

    dumped = report.model_dump(mode="json")

    assert dumped["dragon_tiger"]["status"] == "success"
    assert dumped["dragon_tiger"]["top_net_buy"][0]["name"] == "通富微电"
    assert dumped["dragon_tiger"]["top_net_buy"][0]["seats_buy"][0]["role"] == "northbound"


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
