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


from app.rules.scoring import RawSectorInput, score_sectors


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
