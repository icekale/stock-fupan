from datetime import UTC, datetime

from app.db.models import WatchlistAlertEvent
from app.db.session import create_sqlite_engine, init_db, session_scope


def test_watchlist_alert_event_model_persists_payload(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    init_db(engine)
    seen_at = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)

    with session_scope(engine) as session:
        session.add(
            WatchlistAlertEvent(
                stock_id=1,
                symbol="600519.SH",
                name="贵州茅台",
                event_type="risk",
                severity="high",
                status="active",
                trigger_key="600519.SH:risk:ma_break",
                payload_hash="hash-1",
                trigger_reason="跌破MA5",
                ai_comment="跌破MA5，先处理风险",
                rule_snapshot={"rule_id": "ma_break"},
                market_snapshot={"pct_change": -5.1},
                source_status={"tickflow": "ready"},
                notification_status={"sent": False},
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
        )

    with session_scope(engine) as session:
        row = session.query(WatchlistAlertEvent).one()
        assert row.symbol == "600519.SH"
        assert row.event_type == "risk"
        assert row.severity == "high"
        assert row.trigger_key == "600519.SH:risk:ma_break"
        assert row.rule_snapshot["rule_id"] == "ma_break"
