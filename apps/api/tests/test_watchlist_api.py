import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.models import WatchlistImport, WatchlistItemModel
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
