import pytest

from app.services.morning_auction.data_sources import InMemoryMorningAuctionDataSource


def test_in_memory_data_source_returns_daily_bars_and_auction_snapshots() -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()

    bars = source.daily_bars("600001.SH", end_date="2026-07-03", lookback=3)
    auction = source.auction_snapshot("600001.SH", trade_date="2026-07-03")
    universe = source.candidate_universe("2026-07-03")

    assert [bar.trade_date for bar in bars] == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert auction is not None
    assert auction.snapshot_time == "09:25:00"
    assert auction.auction_amount == 10_100_000
    assert auction.auction_volume == 1_000_000
    assert auction.indicative_price == 10.1
    assert auction.prev_close == 10.0
    assert universe[0]["symbol"] == "600001.SH"
    assert source.sector_strength("600001.SH", trade_date="2026-07-03") == 78.0
    assert source.capital_strength("600001.SH", trade_date="2026-07-03") == 62.0


@pytest.mark.parametrize("lookback", [0, -1])
def test_in_memory_data_source_rejects_non_positive_lookback(lookback: int) -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()

    with pytest.raises(ValueError, match="lookback must be positive"):
        source.daily_bars("600001.SH", end_date="2026-07-03", lookback=lookback)
