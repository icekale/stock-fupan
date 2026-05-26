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
