from app.services.morning_auction.data_sources import InMemoryMorningAuctionDataSource


def test_in_memory_data_source_returns_daily_bars_and_auction_snapshots() -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()

    bars = source.daily_bars("600001.SH", end_date="2026-07-03", lookback=3)
    auction = source.auction_snapshot("600001.SH", trade_date="2026-07-03")
    universe = source.candidate_universe("2026-07-03")

    assert [bar.trade_date for bar in bars] == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert auction is not None
    assert auction.snapshot_time == "09:25:00"
    assert universe[0]["symbol"] == "600001.SH"
