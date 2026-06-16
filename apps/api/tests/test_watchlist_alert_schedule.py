from datetime import UTC, datetime

from app.db.session import create_sqlite_engine, init_db
from app.services.watchlist_alert_schedule import (
    WatchlistAlertScheduleUpdate,
    get_watchlist_alert_schedule_status,
    run_due_watchlist_alert_schedule,
    update_watchlist_alert_schedule_status,
)


class SettingsStub:
    watchlist_alert_schedule_enabled = True
    watchlist_alert_morning_time = "10:00"
    watchlist_alert_afternoon_time = "14:30"
    watchlist_alert_review_time = "19:30"
    watchlist_alert_timezone = "Asia/Shanghai"


def test_schedule_skips_before_due_time(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'schedule.db'}")
    init_db(engine)
    calls = []

    result = run_due_watchlist_alert_schedule(
        engine=engine,
        settings=SettingsStub(),
        run_scan=lambda mode, trade_date: calls.append((mode, trade_date)) or {"status": "completed"},
        now=datetime(2026, 6, 15, 1, 0, tzinfo=UTC),
    )

    assert calls == []
    assert result["enabled"] is True
    assert result["last_result"] is None


def test_schedule_runs_morning_scan_when_due(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'schedule.db'}")
    init_db(engine)
    calls = []

    result = run_due_watchlist_alert_schedule(
        engine=engine,
        settings=SettingsStub(),
        run_scan=lambda mode, trade_date: calls.append((mode, trade_date)) or {"status": "completed"},
        now=datetime(2026, 6, 15, 2, 1, tzinfo=UTC),
    )

    assert calls == [("intraday_morning", "2026-06-15")]
    assert result["last_result"]["mode"] == "intraday_morning"
    assert result["last_result"]["status"] == "completed"


def test_schedule_can_update_settings(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'schedule.db'}")
    init_db(engine)

    result = update_watchlist_alert_schedule_status(
        engine,
        SettingsStub(),
        WatchlistAlertScheduleUpdate(
            enabled=False,
            morning_time="09:45",
            afternoon_time="14:45",
            review_time="20:00",
            timezone="Asia/Shanghai",
        ),
    )

    assert result["enabled"] is False
    assert result["morning_time"] == "09:45"
    assert result["afternoon_time"] == "14:45"
    assert result["review_time"] == "20:00"
    assert get_watchlist_alert_schedule_status(engine, SettingsStub())["enabled"] is False
