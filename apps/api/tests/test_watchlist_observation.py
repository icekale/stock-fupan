from app.providers.tickflow import WatchlistQuote
from app.services.watchlist_observation import build_watchlist_observation
from app.watchlist.parser import WatchlistItem


def test_build_watchlist_observation_sorts_strongest_and_weakest() -> None:
    items = [
        WatchlistItem(symbol="600000.SH", code="600000", exchange="SH", name="浦发银行"),
        WatchlistItem(symbol="000001.SZ", code="000001", exchange="SZ", name="平安银行"),
        WatchlistItem(symbol="300750.SZ", code="300750", exchange="SZ", name="宁德时代"),
    ]
    quotes = [
        WatchlistQuote(symbol="600000.SH", name="浦发银行", pct_change=1.2),
        WatchlistQuote(symbol="000001.SZ", name="平安银行", pct_change=-2.5),
        WatchlistQuote(symbol="300750.SZ", name="宁德时代", pct_change=4.8),
    ]

    observation = build_watchlist_observation(import_id=7, items=items, quotes=quotes, sectors=[])

    assert observation.import_id == 7
    assert observation.total_count == 3
    assert observation.quote_count == 3
    assert observation.strongest[0].symbol == "300750.SZ"
    assert observation.weakest[0].symbol == "000001.SZ"


def test_build_watchlist_observation_handles_empty_watchlist() -> None:
    observation = build_watchlist_observation(import_id=None, items=[], quotes=[], sectors=[])

    assert observation.total_count == 0
    assert observation.quote_count == 0
    assert observation.notes == ["未导入自选股"]
