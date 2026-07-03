from app.services.morning_auction.data_sources import InMemoryMorningAuctionDataSource
from app.services.morning_auction.features import build_feature_row
from app.services.morning_auction.schemas import AuctionSnapshot, DailyBar


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


def test_feature_row_filters_current_day_bar_when_auction_date_is_available() -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()
    bars = source.daily_bars("600001.SH", end_date="2026-07-03", lookback=3)
    auction = source.auction_snapshot("600001.SH", trade_date="2026-07-03")

    prior_only = build_feature_row(
        symbol="600001.SH",
        market_cap_float=8_000_000_000,
        daily_bars=bars[:2],
        auction=auction,
        sector_strength=78.0,
        capital_strength=62.0,
    )
    unsliced = build_feature_row(
        symbol="600001.SH",
        market_cap_float=8_000_000_000,
        daily_bars=bars,
        auction=auction,
        sector_strength=78.0,
        capital_strength=62.0,
    )

    assert unsliced["prev_return"] == 2.0408
    assert unsliced["prev_return"] == prior_only["prev_return"]
    assert unsliced["prev_return"] != 3.0303


def test_feature_row_handles_zero_denominators_and_nulls() -> None:
    row = build_feature_row(
        symbol="600001.SH",
        market_cap_float=None,
        daily_bars=[
            DailyBar(
                trade_date="2026-07-02",
                open=0.0,
                high=0.0,
                low=0.0,
                close=10.0,
                volume=0.0,
                amount=0.0,
            )
        ],
        auction=AuctionSnapshot(
            trade_date="2026-07-03",
            symbol="600001.SH",
            snapshot_time="09:25:00",
            indicative_price=10.8,
            prev_close=0.0,
            auction_volume=0.0,
            auction_amount=None,
        ),
        sector_strength=None,
        capital_strength=None,
    )

    assert row["market_cap_float"] is None
    assert row["prev_return"] is None
    assert row["auction_return"] is None
    assert row["auction_volume_ratio"] is None
    assert row["auction_amount_ratio"] is None
    assert row["bid_ask_imbalance"] is None
    assert row["unmatched_buy_ratio"] is None
    assert row["risk_score"] == 0.0


def test_feature_row_computes_imbalance_unmatched_ratio_and_risk_score() -> None:
    row = build_feature_row(
        symbol="600001.SH",
        market_cap_float=8_000_000_000,
        daily_bars=[
            DailyBar(
                trade_date="2026-07-01",
                open=10.0,
                high=10.1,
                low=9.5,
                close=10.0,
                volume=1_000_000,
                amount=10_000_000,
            ),
            DailyBar(
                trade_date="2026-07-02",
                open=10.0,
                high=10.0,
                low=9.5,
                close=9.6,
                volume=1_000_000,
                amount=9_600_000,
            ),
        ],
        auction=AuctionSnapshot(
            trade_date="2026-07-03",
            symbol="600001.SH",
            snapshot_time="09:25:00",
            indicative_price=10.7,
            prev_close=10.0,
            auction_volume=100_000,
            auction_amount=1_070_000,
            bid_volume=300_000,
            ask_volume=100_000,
            unmatched_volume=25_000,
        ),
        sector_strength=78.0,
        capital_strength=62.0,
    )

    assert row["bid_ask_imbalance"] == 0.5
    assert row["unmatched_buy_ratio"] == 0.25
    assert row["risk_score"] == 30.0
