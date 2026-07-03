from pathlib import Path

import pytest

from app.services.morning_auction.artifacts import read_jsonl, write_jsonl
from app.services.morning_auction.data_sources import InMemoryMorningAuctionDataSource
from app.services.morning_auction.dataset import build_samples_for_trade_date
from app.services.morning_auction.schemas import AuctionSnapshot, DailyBar


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
    source = _source_with_current_bar(
        DailyBar(
            trade_date="2026-07-03",
            open=10.1,
            high=10.3,
            low=9.9,
            close=10.5,
            volume=1_100_000,
            amount=11_220_000,
        ),
        include_auction=True,
    )

    samples = build_samples_for_trade_date(source, trade_date="2026-07-03", lookback=3)

    assert len(samples) == 1
    assert samples[0].symbol == "600001.SH"
    assert samples[0].prev_close_price == 10.0
    assert samples[0].open_price == 10.1
    assert samples[0].close_price == 10.5
    assert samples[0].main_label is True
    assert samples[0].features["auction_data_available"] == 1
    assert samples[0].features["auction_volume_ratio"] == 1.052632


def test_build_samples_for_trade_date_adds_t1_executable_returns_and_labels() -> None:
    source = _source_with_current_bar(
        DailyBar(
            trade_date="2026-07-03",
            open=10.0,
            high=10.3,
            low=9.9,
            close=10.2,
            volume=1_100_000,
            amount=11_220_000,
        ),
        next_bar=DailyBar(
            trade_date="2026-07-06",
            open=10.4,
            high=10.8,
            low=10.1,
            close=10.6,
            volume=1_200_000,
            amount=12_420_000,
        ),
    )

    sample = build_samples_for_trade_date(source, trade_date="2026-07-03", lookback=3)[0]

    assert sample.next_open_price == 10.4
    assert sample.next_close_price == 10.6
    assert sample.t1_open_return == 0.04
    assert sample.t1_close_return == 0.06
    assert sample.t1_open_label is True
    assert sample.t1_close_label is True
    assert sample.t1_risk_label is False


def test_build_samples_for_trade_date_skips_when_current_bar_is_missing() -> None:
    source = InMemoryMorningAuctionDataSource(
        universe=[{"symbol": "600001.SH", "name": "Fixture Stock"}],
        bars_by_symbol={
            "600001.SH": [
                DailyBar(
                    trade_date="2026-07-01",
                    open=9.8,
                    high=10.0,
                    low=9.7,
                    close=9.9,
                    volume=900_000,
                    amount=8_910_000,
                ),
                DailyBar(
                    trade_date="2026-07-02",
                    open=9.9,
                    high=10.1,
                    low=9.8,
                    close=10.0,
                    volume=950_000,
                    amount=9_500_000,
                ),
            ]
        },
        auctions_by_key={},
    )

    samples = build_samples_for_trade_date(source, trade_date="2026-07-03", lookback=3)

    assert samples == []


def test_build_samples_for_trade_date_rejects_st_like_name_when_flag_is_false() -> None:
    source = _source_with_current_bar(
        DailyBar(
            trade_date="2026-07-03",
            open=10.1,
            high=10.3,
            low=9.9,
            close=10.5,
            volume=1_100_000,
            amount=11_220_000,
        ),
        name="*ST Fixture",
    )

    samples = build_samples_for_trade_date(source, trade_date="2026-07-03", lookback=3)

    assert samples == []


@pytest.mark.parametrize(
    ("symbol", "name", "expected_count"),
    [
        ("600001.SH", "普通沪市", 1),
        ("000001.SZ", "普通深市", 1),
        ("300001.SZ", "普通创业板", 1),
        ("688001.SH", "普通科创板", 1),
        ("159546.SZ", "集成电路ETF国泰", 0),
        ("560780.SH", "半导体设备ETF广发", 0),
        ("920992.BJ", "中科美菱", 0),
        ("000004.SZ", "国华退", 0),
        ("002808.SZ", "恒久退", 0),
    ],
)
def test_build_samples_for_trade_date_keeps_only_common_a_share_universe(
    symbol: str,
    name: str,
    expected_count: int,
) -> None:
    source = _source_with_current_bar(
        DailyBar(
            trade_date="2026-07-03",
            open=10.1,
            high=10.3,
            low=9.9,
            close=10.5,
            volume=1_100_000,
            amount=11_220_000,
        ),
        symbol=symbol,
        name=name,
    )

    samples = build_samples_for_trade_date(source, trade_date="2026-07-03", lookback=3)

    assert len(samples) == expected_count


@pytest.mark.parametrize(
    "field,value",
    [
        ("open", 0.0),
        ("close", 0.0),
        ("volume", 0.0),
        ("amount", 0.0),
    ],
)
def test_build_samples_for_trade_date_skips_invalid_current_label_bar(
    field: str,
    value: float,
) -> None:
    current_bar = DailyBar(
        trade_date="2026-07-03",
        open=10.1,
        high=10.3,
        low=9.9,
        close=10.5,
        volume=1_100_000,
        amount=11_220_000,
    ).model_copy(update={field: value})
    source = _source_with_current_bar(current_bar)

    samples = build_samples_for_trade_date(source, trade_date="2026-07-03", lookback=3)

    assert samples == []


def test_jsonl_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    rows = [{"symbol": "600001.SH", "value": 1}, {"symbol": "600002.SH", "value": 2}]

    write_jsonl(path, rows)

    assert read_jsonl(path) == rows


def _source_with_current_bar(
    current_bar: DailyBar,
    *,
    symbol: str = "600001.SH",
    name: str = "Fixture Co",
    include_auction: bool = False,
    next_bar: DailyBar | None = None,
) -> InMemoryMorningAuctionDataSource:
    trade_date = "2026-07-03"
    auctions_by_key = {}
    if include_auction:
        auctions_by_key[(symbol, trade_date)] = AuctionSnapshot(
            trade_date=trade_date,
            symbol=symbol,
            name=name,
            snapshot_time="09:25:00",
            indicative_price=10.1,
            prev_close=10.0,
            auction_volume=1_000_000,
            auction_amount=10_100_000,
        )

    return InMemoryMorningAuctionDataSource(
        universe=[{"symbol": symbol, "name": name, "is_st": False}],
        bars_by_symbol={
            symbol: [
                DailyBar(
                    trade_date="2026-07-01",
                    open=9.8,
                    high=10.0,
                    low=9.7,
                    close=9.9,
                    volume=900_000,
                    amount=8_910_000,
                ),
                DailyBar(
                    trade_date="2026-07-02",
                    open=9.9,
                    high=10.1,
                    low=9.8,
                    close=10.0,
                    volume=950_000,
                    amount=9_500_000,
                ),
                current_bar,
                *([next_bar] if next_bar is not None else []),
            ]
        },
        auctions_by_key=auctions_by_key,
        sector_by_key={(symbol, trade_date): 78.0},
        capital_by_key={(symbol, trade_date): 62.0},
    )
