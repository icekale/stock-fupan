import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from datetime import UTC, datetime

from app.db.models import WatchlistAlertEvent, WatchlistImport, WatchlistItemModel
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.main import app
from app.watchlist.service import WatchlistImportService


def test_watchlist_service_imports_text_to_db_and_snapshots(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistImportService(engine=engine, snapshot_root=tmp_path / "watchlists")

    result = service.import_text("600000\n000001\n", source_name="manual.txt")

    assert result.import_id == 1
    assert [item.symbol for item in result.items] == ["600000.SH", "000001.SZ"]
    assert result.item_count == 2
    with session_scope(engine) as session:
        imported = session.query(WatchlistImport).one()
        rows = session.query(WatchlistItemModel).order_by(WatchlistItemModel.display_order).all()
        assert imported.item_count == 2
        assert Path(imported.snapshot_path).exists()
        assert [row.symbol for row in rows] == ["600000.SH", "000001.SZ"]
    parsed = json.loads((tmp_path / "watchlists" / "imports" / "000001-parsed.json").read_text(encoding="utf-8"))
    assert parsed["items"][0]["symbol"] == "600000.SH"


def test_watchlist_latest_returns_empty_without_import(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistImportService(engine=engine, snapshot_root=tmp_path / "watchlists")

    latest = service.get_latest()

    assert latest.import_id is None
    assert latest.items == []


def test_watchlist_import_text_api_returns_items(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.post(
            "/api/watchlists/import-text",
            json={"content": "600000\n000001", "source_name": "manual.txt"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_count"] == 2
    assert [item["symbol"] for item in payload["items"]] == ["600000.SH", "000001.SZ"]
    get_settings.cache_clear()


def test_watchlist_pool_api_manages_groups_stocks_and_observation_plan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pool-api.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        initial = client.get("/api/watchlist-pool")
        assert initial.status_code == 200
        assert [group["name"] for group in initial.json()["groups"]] == ["自选"]

        group_response = client.post("/api/watchlist-pool/groups", json={"name": "MLCC"})
        assert group_response.status_code == 200
        group_id = group_response.json()["id"]

        stock_response = client.post(
            "/api/watchlist-pool/stocks",
            json={
                "symbol": "600563.SH",
                "name": "法拉电子",
                "group_ids": [group_id],
                "tags": ["趋势", "观察"],
                "status": "持有中",
                "entry_reason": "MLCC 景气观察",
                "planned_buy_price": "回踩MA10",
                "invalid_condition": "跌破MA20",
                "themes": ["MLCC"],
            },
        )
        assert stock_response.status_code == 200
        stock_payload = stock_response.json()
        assert stock_payload["symbol"] == "600563.SH"
        assert stock_payload["status"] == "持有中"
        assert stock_payload["entry_reason"] == "MLCC 景气观察"
        assert [group["name"] for group in stock_payload["groups"]] == ["MLCC"]

        update_response = client.patch(
            f"/api/watchlist-pool/stocks/{stock_payload['id']}",
            json={
                "group_ids": [],
                "tags": ["复盘"],
                "status": "观察中",
                "today_risk_hint": "放量滞涨需复核",
            },
        )
        assert update_response.status_code == 200
        assert update_response.json()["groups"] == []
        assert update_response.json()["tags"] == ["复盘"]
        assert update_response.json()["today_risk_hint"] == "放量滞涨需复核"

        group_only_response = client.patch(
            f"/api/watchlist-pool/stocks/{stock_payload['id']}",
            json={"group_ids": [group_id]},
        )
        assert group_only_response.status_code == 200
        assert group_only_response.json()["entry_reason"] == "MLCC 景气观察"
        assert group_only_response.json()["planned_buy_price"] == "回踩MA10"
        assert group_only_response.json()["today_risk_hint"] == "放量滞涨需复核"

        delete_response = client.delete(f"/api/watchlist-pool/groups/{group_id}")
        assert delete_response.status_code == 200
        pool = client.get("/api/watchlist-pool").json()
        assert [stock["symbol"] for stock in pool["stocks"]] == ["600563.SH"]
        assert [group["name"] for group in pool["groups"]] == ["自选"]
    get_settings.cache_clear()


def test_watchlist_alert_event_actions_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'alert-actions.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        with session_scope(app.state.engine) as session:
            session.add(
                WatchlistAlertEvent(
                    stock_id=None,
                    symbol="600563.SH",
                    name="法拉电子",
                    event_type="risk",
                    severity="high",
                    status="active",
                    trigger_key="600563.SH:risk:test",
                    payload_hash="test-hash",
                    trigger_reason="跌破MA5",
                    ai_comment=None,
                    rule_snapshot={"rule_id": "test"},
                    market_snapshot={"trade_date": "2026-06-15"},
                    source_status={"tickflow": "ready"},
                    notification_status={},
                    first_seen_at=datetime(2026, 6, 15, 10, 0, tzinfo=UTC),
                    last_seen_at=datetime(2026, 6, 15, 10, 0, tzinfo=UTC),
                )
            )

        alert_id = client.get("/api/watchlist-alerts").json()["items"][0]["id"]

        ack_response = client.post(f"/api/watchlist-alerts/{alert_id}/ack")
        assert ack_response.status_code == 200
        assert ack_response.json()["status"] == "acknowledged"

        mute_response = client.post(f"/api/watchlist-alerts/{alert_id}/mute", json={"days": 3})
        assert mute_response.status_code == 200
        assert mute_response.json()["status"] == "muted"
        assert mute_response.json()["muted_until"] is not None
    get_settings.cache_clear()


def test_watchlist_alert_run_and_schedule_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'alerts.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        import_response = client.post(
            "/api/watchlists/import-text",
            json={"content": "600519 贵州茅台", "source_name": "manual.txt"},
        )
        assert import_response.status_code == 200

        run_response = client.post(
            "/api/watchlist-alerts/run",
            json={"mode": "daily_review", "trade_date": "2026-06-15"},
        )
        assert run_response.status_code == 200
        assert run_response.json()["status"] == "completed"

        list_response = client.get("/api/watchlist-alerts")
        assert list_response.status_code == 200
        assert "items" in list_response.json()

        update_response = client.put(
            "/api/watchlist-alert-schedule/status",
            json={
                "enabled": True,
                "morning_time": "10:00",
                "afternoon_time": "14:30",
                "review_time": "19:30",
                "timezone": "Asia/Shanghai",
            },
        )
        assert update_response.status_code == 200
        assert update_response.json()["enabled"] is True

        status_response = client.get("/api/watchlist-alert-schedule/status")
        assert status_response.status_code == 200
        assert status_response.json()["enabled"] is True
    get_settings.cache_clear()


def test_manual_watchlist_alert_run_does_not_advance_schedule(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'manual-alerts.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        client.put(
            "/api/watchlist-alert-schedule/status",
            json={
                "enabled": True,
                "morning_time": "10:00",
                "afternoon_time": "14:30",
                "review_time": "19:30",
                "timezone": "Asia/Shanghai",
            },
        )
        response = client.post(
            "/api/watchlist-alerts/run",
            json={"mode": "daily_review", "trade_date": "2026-06-15"},
        )
        status_response = client.get("/api/watchlist-alert-schedule/status")

    assert response.status_code == 200
    assert status_response.json()["last_run_at"] is None
    assert status_response.json()["last_result"] is None
    get_settings.cache_clear()


def test_watchlist_alert_run_rejects_invalid_request(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'invalid-alerts.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        bad_mode = client.post(
            "/api/watchlist-alerts/run",
            json={"mode": "bad_mode", "trade_date": "2026-06-15"},
        )
        bad_date = client.post(
            "/api/watchlist-alerts/run",
            json={"mode": "daily_review", "trade_date": "20260615"},
        )

    assert bad_mode.status_code == 422
    assert bad_date.status_code == 422
    get_settings.cache_clear()
