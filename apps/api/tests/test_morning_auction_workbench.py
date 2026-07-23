from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.morning_auction.schemas import DailyBar, MorningAuctionTrialEntry
from app.services.morning_auction.workbench import (
    MorningAuctionTrialStore,
    build_live_prediction_rows,
    prediction_items_from_scored_rows,
)


class FakeLiveSource:
    def __init__(self) -> None:
        self.daily_bar_end_dates: list[str] = []
        self.prefetch_args: dict[str, object] | None = None

    def prefetch_daily_window(self, *, start_date: str, end_date: str, lookback: int) -> None:
        self.prefetch_args = {
            "start_date": start_date,
            "end_date": end_date,
            "lookback": lookback,
        }

    def candidate_universe(self, trade_date: str) -> list[dict[str, object]]:
        if trade_date == "2026-07-03":
            return [
                {
                    "symbol": "600001.SH",
                    "name": "样本股份",
                    "is_st": False,
                    "is_suspended": False,
                    "listed_days": 999,
                    "market_cap_float": 1_000_000_000,
                }
            ]
        return []

    def daily_bars(self, symbol: str, *, end_date: str, lookback: int) -> list[DailyBar]:
        self.daily_bar_end_dates.append(end_date)
        return [
            DailyBar(
                trade_date="2026-07-02",
                open=10,
                high=10.5,
                low=9.8,
                close=10,
                volume=1_000_000,
                amount=10_000_000,
                turnover_rate=2.1,
            ),
            DailyBar(
                trade_date="2026-07-03",
                open=10.2,
                high=11.2,
                low=10.1,
                close=11,
                volume=1_500_000,
                amount=16_000_000,
                turnover_rate=3.2,
            ),
        ]

    def auction_snapshot(self, symbol: str, *, trade_date: str):
        return None

    def sector_strength(self, symbol: str, *, trade_date: str):
        return None

    def capital_strength(self, symbol: str, *, trade_date: str):
        return None


def test_build_live_prediction_rows_uses_previous_available_daily_bar() -> None:
    source = FakeLiveSource()

    rows, feature_end_date = build_live_prediction_rows(
        source,
        trade_date="2026-07-06",
        lookback=2,
    )

    assert feature_end_date == "2026-07-03"
    assert source.prefetch_args == {
        "start_date": "2026-07-03",
        "end_date": "2026-07-03",
        "lookback": 2,
    }
    assert source.daily_bar_end_dates == ["2026-07-03"]
    assert rows[0]["trade_date"] == "2026-07-06"
    assert rows[0]["feature_end_date"] == "2026-07-03"
    assert rows[0]["prev_close_price"] == 11
    assert rows[0]["open_price"] is None
    assert rows[0]["data_quality"] == ["no_auction_snapshot", "uses_previous_daily_bar"]


def test_prediction_items_marks_top_n_selected_and_keeps_guard_rule() -> None:
    items = prediction_items_from_scored_rows(
        [
            {
                "symbol": "600001.SH",
                "name": "强势一号",
                "prob_3pct": 0.91,
                "prev_close_price": 11,
                "feature_end_date": "2026-07-03",
                "data_quality": ["no_auction_snapshot"],
            },
            {
                "symbol": "600002.SH",
                "name": "强势二号",
                "prob_3pct": 0.83,
                "prev_close_price": 8,
                "feature_end_date": "2026-07-03",
                "data_quality": ["no_auction_snapshot"],
            },
        ],
        top_n=1,
        max_items=2,
    )

    assert items[0].symbol == "600001.SH"
    assert items[0].rank == 1
    assert items[0].bucket == "selected"
    assert items[0].guard_rule == "10:00收益<0则退出，否则持有到T+1收盘"
    assert items[1].bucket == "attack"


def test_morning_auction_trial_store_upserts_entries(tmp_path: Path) -> None:
    store = MorningAuctionTrialStore(tmp_path / "trial_log.json")

    created = store.upsert(
        MorningAuctionTrialEntry(
            trade_date="2026-07-06",
            symbol="600001.SH",
            name="样本股份",
            rank=1,
            prob_3pct=0.91,
            mode="live_small",
            planned_capital=3000,
            status="planned",
        )
    )
    updated = store.upsert(
        MorningAuctionTrialEntry(
            trade_date="2026-07-06",
            symbol="600001.SH",
            name="样本股份",
            rank=1,
            prob_3pct=0.91,
            mode="live_small",
            planned_capital=3000,
            entry_price=11.2,
            shares=200,
            status="entered",
        )
    )

    assert created.id == "2026-07-06:600001.SH"
    assert updated.id == created.id
    assert store.list_entries("2026-07-06")[0].entry_price == 11.2
    assert len(store.list_entries()) == 1


def test_morning_auction_trial_api_uses_injected_store() -> None:
    store = MorningAuctionTrialStore(Path(":memory-not-used:"))
    app.state.morning_auction_trial_store = store
    client = TestClient(app)
    try:
        response = client.post(
            "/api/morning-auction/trials",
            json={
                "trade_date": "2026-07-06",
                "symbol": "600001.SH",
                "name": "样本股份",
                "rank": 1,
                "prob_3pct": 0.91,
                "mode": "paper",
                "status": "planned",
            },
        )
        list_response = client.get("/api/morning-auction/trials?trade_date=2026-07-06")
    finally:
        delattr(app.state, "morning_auction_trial_store")

    assert response.status_code == 200
    assert response.json()["id"] == "2026-07-06:600001.SH"
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["symbol"] == "600001.SH"
