import httpx
import pytest

from app.cli import morning_auction
from app.services.morning_auction.artifacts import read_jsonl
from app.services.morning_auction.dataset import build_samples_for_trade_date
from app.services.morning_auction.free_stockdb import (
    FreeStockDbError,
    FreeStockDbHttpClient,
    FreeStockDbMorningAuctionDataSource,
)
from app.services.morning_auction.schemas import DailyBar


def test_free_stockdb_daily_bars_maps_rows_and_sorts_ascending() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "date": 20260625,
                    "code": "600633",
                    "name": "浙数文化",
                    "open": 10.45,
                    "high": 10.62,
                    "low": 10.37,
                    "close": 10.45,
                    "volume": 18_031_500,
                    "amount": 189_010_000,
                    "turnover": 1.42,
                },
                {
                    "date": 20260624,
                    "code": "600633",
                    "name": "浙数文化",
                    "open": 10.75,
                    "high": 10.83,
                    "low": 10.43,
                    "close": 10.52,
                    "volume": 20_890_000,
                    "amount": 221_000_000,
                    "turnover": 1.65,
                },
            ],
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    source = FreeStockDbMorningAuctionDataSource(
        base_url="http://stockdb.local:7899",
        http_client=http_client,
    )

    bars = source.daily_bars("600633.SH", end_date="2026-06-25", lookback=2)

    assert [bar.trade_date for bar in bars] == ["2026-06-24", "2026-06-25"]
    assert bars[-1].open == 10.45
    assert bars[-1].turnover_rate == 1.42
    params = dict(requests[0].url.params)
    assert params["cmd"] == "vals"
    assert params["t"] == "日k"
    assert params["k1"] == "key:600633"
    assert params["k2"].endswith(",20260625")


def test_free_stockdb_minute_bars_maps_rows_and_sorts_ascending() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "date": 20260702093100,
                    "code": "600633",
                    "open": 10.62,
                    "high": 10.64,
                    "low": 10.57,
                    "close": 10.60,
                    "volume": 774_400,
                    "amount": 8_213_335,
                },
                {
                    "date": 20260702093000,
                    "code": "600633",
                    "open": 10.40,
                    "high": 10.62,
                    "low": 10.40,
                    "close": 10.62,
                    "volume": 488_500,
                    "amount": 5_132_208,
                },
            ],
        )

    source = FreeStockDbMorningAuctionDataSource(
        base_url="http://stockdb.local:7899",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    bars = source.minute_bars(
        "600633.SH",
        start_time="2026-07-02 09:25:00",
        end_time="2026-07-02 10:00:00",
    )

    assert [bar.trade_time for bar in bars] == ["2026-07-02 09:30:00", "2026-07-02 09:31:00"]
    assert bars[0].open == 10.40
    assert bars[0].amount == 5_132_208
    params = dict(requests[0].url.params)
    assert params == {
        "cmd": "vals",
        "t": "分钟k",
        "k1": "key:600633",
        "k2": "fwd:20260702092500,20260702100000",
    }


def test_free_stockdb_candidate_universe_maps_full_market_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {
            "cmd": "vals",
            "t": "日k",
            "k1": "all:",
            "k2": "key:20260625",
        }
        return httpx.Response(
            200,
            json=[
                {
                    "date": 20260625,
                    "code": "600633",
                    "name": "浙数文化",
                    "is_st": False,
                    "float_mv": 13_251_000_000,
                },
                {
                    "date": 20260625,
                    "code": "000001",
                    "name": "平安银行",
                    "is_st": False,
                    "float_mv": 202_210_000_000,
                },
                {
                    "date": 20260625,
                    "code": "920992",
                    "name": "中科美菱",
                    "is_st": False,
                    "float_mv": 1_178_000_000,
                },
            ],
        )

    source = FreeStockDbMorningAuctionDataSource(
        base_url="http://stockdb.local:7899",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    universe = source.candidate_universe("2026-06-25")

    assert universe == [
        {
            "symbol": "600633.SH",
            "name": "浙数文化",
            "is_st": False,
            "is_suspended": False,
            "listed_days": 9999,
            "market_cap_float": 13_251_000_000.0,
        },
        {
            "symbol": "000001.SZ",
            "name": "平安银行",
            "is_st": False,
            "is_suspended": False,
            "listed_days": 9999,
            "market_cap_float": 202_210_000_000.0,
        },
        {
            "symbol": "920992.BJ",
            "name": "中科美菱",
            "is_st": False,
            "is_suspended": False,
            "listed_days": 9999,
            "market_cap_float": 1_178_000_000.0,
        },
    ]


def test_free_stockdb_candidate_universe_can_use_symbol_subset() -> None:
    requested_k1: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requested_k1.append(params["k1"])
        code = params["k1"].removeprefix("key:")
        return httpx.Response(
            200,
            json=[
                {
                    "date": 20260625,
                    "code": code,
                    "name": "样本股份",
                    "is_st": False,
                    "float_mv": 1_000_000_000,
                }
            ],
        )

    source = FreeStockDbMorningAuctionDataSource(
        base_url="http://stockdb.local:7899",
        symbols=["600633.SH", "000001"],
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    universe = source.candidate_universe("2026-06-25")

    assert requested_k1 == ["key:600633", "key:000001"]
    assert [candidate["symbol"] for candidate in universe] == ["600633.SH", "000001.SZ"]


def test_free_stockdb_prefetch_daily_window_reuses_cached_rows() -> None:
    requests: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requests.append(params)
        if params["k1"] != "all:" or not params["k2"].startswith("fwd:"):
            raise AssertionError(f"unexpected uncached request: {params}")
        return httpx.Response(
            200,
            json=[
                {
                    "date": 20260624,
                    "code": "600633",
                    "name": "浙数文化",
                    "open": 9.7,
                    "high": 10.0,
                    "low": 9.5,
                    "close": 9.8,
                    "volume": 20_890_000,
                    "amount": 221_000_000,
                    "turnover": 1.65,
                    "is_st": False,
                    "float_mv": 13_251_000_000,
                },
                {
                    "date": 20260625,
                    "code": "600633",
                    "name": "浙数文化",
                    "open": 10.0,
                    "high": 10.6,
                    "low": 9.9,
                    "close": 10.4,
                    "volume": 18_031_500,
                    "amount": 189_010_000,
                    "turnover": 1.42,
                    "is_st": False,
                    "float_mv": 13_251_000_000,
                },
            ],
        )

    source = FreeStockDbMorningAuctionDataSource(
        base_url="http://stockdb.local:7899",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    source.prefetch_daily_window(start_date="2026-06-25", end_date="2026-06-25", lookback=2)
    universe = source.candidate_universe("2026-06-25")
    bars = source.daily_bars("600633.SH", end_date="2026-06-25", lookback=2)

    assert len(requests) == 1
    assert requests[0]["cmd"] == "vals"
    assert requests[0]["t"] == "日k"
    assert requests[0]["k1"] == "all:"
    assert requests[0]["k2"].endswith(",20260705")
    assert universe[0]["symbol"] == "600633.SH"
    assert [bar.trade_date for bar in bars] == ["2026-06-24", "2026-06-25"]


def test_free_stockdb_source_builds_cold_start_samples_without_auction_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params["k1"] == "all:":
            return httpx.Response(
                200,
                json=[
                    {
                        "date": 20260625,
                        "code": "600633",
                        "name": "浙数文化",
                        "is_st": False,
                        "float_mv": 13_251_000_000,
                    }
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "date": 20260625,
                    "code": "600633",
                    "name": "浙数文化",
                    "open": 10.0,
                    "high": 10.6,
                    "low": 9.9,
                    "close": 10.4,
                    "volume": 18_031_500,
                    "amount": 189_010_000,
                    "turnover": 1.42,
                },
                {
                    "date": 20260624,
                    "code": "600633",
                    "name": "浙数文化",
                    "open": 9.7,
                    "high": 10.0,
                    "low": 9.5,
                    "close": 9.8,
                    "volume": 20_890_000,
                    "amount": 221_000_000,
                    "turnover": 1.65,
                },
            ],
        )

    source = FreeStockDbMorningAuctionDataSource(
        base_url="http://stockdb.local:7899",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    samples = build_samples_for_trade_date(source, trade_date="2026-06-25", lookback=2)

    assert len(samples) == 1
    assert samples[0].symbol == "600633.SH"
    assert samples[0].main_label is True
    assert samples[0].features["auction_data_available"] == 0
    assert source.auction_snapshot("600633.SH", trade_date="2026-06-25") is None
    assert source.sector_strength("600633.SH", trade_date="2026-06-25") is None
    assert source.capital_strength("600633.SH", trade_date="2026-06-25") is None


def test_free_stockdb_rejects_non_positive_lookback() -> None:
    source = FreeStockDbMorningAuctionDataSource(base_url="http://stockdb.local:7899")

    with pytest.raises(ValueError, match="lookback must be positive"):
        source.daily_bars("600633.SH", end_date="2026-06-25", lookback=0)


def test_free_stockdb_raises_focused_error_for_bad_payload() -> None:
    client = FreeStockDbHttpClient(
        base_url="http://stockdb.local:7899",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"bad": True}))
        ),
    )

    with pytest.raises(FreeStockDbError, match="expected list payload"):
        client.vals(table="日k", k1="key:600633", k2="key:20260625")


def test_cli_build_dataset_writes_free_stockdb_samples(tmp_path, monkeypatch) -> None:
    created: dict[str, object] = {}

    def source_factory(**kwargs):
        source = _CliFreeStockDbSource()
        created.update(kwargs)
        created["source"] = source
        return source

    monkeypatch.setattr(morning_auction, "FreeStockDbMorningAuctionDataSource", source_factory)
    output_path = tmp_path / "samples.jsonl"

    exit_code = morning_auction.main(
        [
            "build-dataset",
            "--source",
            "free-stockdb",
            "--base-url",
            "http://stockdb.local:7899",
            "--start-date",
            "2026-06-25",
            "--end-date",
            "2026-06-25",
            "--lookback",
            "2",
            "--symbols",
            "600633,000001.SZ",
            "--output",
            str(output_path),
        ]
    )

    rows = read_jsonl(output_path)
    assert exit_code == 0
    assert created["base_url"] == "http://stockdb.local:7899"
    assert created["symbols"] == ["600633", "000001.SZ"]
    assert created["timeout_seconds"] == 60.0
    assert created["source"].prefetch_calls == [("2026-06-25", "2026-06-25", 2)]
    assert rows[0]["trade_date"] == "2026-06-25"
    assert rows[0]["symbol"] == "600633.SH"
    assert rows[0]["main_label"] is True
    assert rows[0]["features"]["auction_data_available"] == 0


class _CliFreeStockDbSource:
    def __init__(self) -> None:
        self.prefetch_calls: list[tuple[str, str, int]] = []

    def prefetch_daily_window(self, *, start_date, end_date, lookback: int) -> None:
        self.prefetch_calls.append((start_date.isoformat(), end_date.isoformat(), lookback))

    def candidate_universe(self, trade_date: str) -> list[dict[str, object]]:
        return [
            {
                "symbol": "600633.SH",
                "name": "浙数文化",
                "is_st": False,
                "listed_days": 9999,
                "is_suspended": False,
                "market_cap_float": 13_251_000_000,
            }
        ]

    def daily_bars(self, symbol: str, *, end_date: str, lookback: int) -> list[DailyBar]:
        return [
            DailyBar(
                trade_date="2026-06-24",
                open=9.7,
                high=10.0,
                low=9.5,
                close=9.8,
                volume=20_890_000,
                amount=221_000_000,
                turnover_rate=1.65,
            ),
            DailyBar(
                trade_date="2026-06-25",
                open=10.0,
                high=10.6,
                low=9.9,
                close=10.4,
                volume=18_031_500,
                amount=189_010_000,
                turnover_rate=1.42,
            ),
        ]

    def next_daily_bar(self, symbol: str, *, trade_date: str) -> DailyBar | None:
        return None

    def auction_snapshot(self, symbol: str, *, trade_date: str):
        return None

    def sector_strength(self, symbol: str, *, trade_date: str):
        return None

    def capital_strength(self, symbol: str, *, trade_date: str):
        return None
