from pathlib import Path

import pytest

from app.services.morning_auction.artifacts import read_jsonl, write_jsonl
from app.services.morning_auction.data_sources import InMemoryMorningAuctionDataSource
from app.services.morning_auction.dataset import build_samples_for_trade_date


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


def test_build_samples_for_trade_date_uses_prior_bars_for_features() -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()

    samples = build_samples_for_trade_date(source, trade_date="2026-07-03", lookback=3)

    assert len(samples) == 1
    assert samples[0].symbol == "600001.SH"
    assert samples[0].open_price == 10.0
    assert samples[0].close_price == 10.2
    assert samples[0].main_label is False
    assert samples[0].features["auction_data_available"] == 1


def test_jsonl_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    rows = [{"symbol": "600001.SH", "value": 1}, {"symbol": "600002.SH", "value": 2}]

    write_jsonl(path, rows)

    assert read_jsonl(path) == rows
