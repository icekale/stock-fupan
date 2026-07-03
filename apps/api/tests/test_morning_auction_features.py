from app.services.morning_auction.data_sources import InMemoryMorningAuctionDataSource
from app.services.morning_auction.features import build_feature_row


def test_feature_row_uses_prior_bars_and_auction_snapshot() -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()
    bars = source.daily_bars("600001.SH", end_date="2026-07-03", lookback=3)
    auction = source.auction_snapshot("600001.SH", trade_date="2026-07-03")

    row = build_feature_row(
        symbol="600001.SH",
        market_cap_float=8_000_000_000,
        daily_bars=bars[:2],
        auction=auction,
        sector_strength=78.0,
        capital_strength=62.0,
    )

    assert row["auction_data_available"] == 1
    assert row["auction_return"] == 1.0
    assert row["prev_return"] == 2.0408
    assert row["close_vs_ma5"] == 0.0
    assert row["sector_strength"] == 78.0
    assert row["capital_strength"] == 62.0


def test_feature_row_marks_missing_auction_data() -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()
    bars = source.daily_bars("600001.SH", end_date="2026-07-03", lookback=3)

    row = build_feature_row(
        symbol="600001.SH",
        market_cap_float=8_000_000_000,
        daily_bars=bars[:2],
        auction=None,
        sector_strength=None,
        capital_strength=None,
    )

    assert row["auction_data_available"] == 0
    assert row["auction_return"] is None
    assert row["sector_strength"] is None
