from datetime import UTC, datetime, timedelta

from app.db.models import WatchlistAlertEvent
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.services.notification import NotificationMessage, NotificationResult
from app.services.watchlist_alerts import (
    WatchlistAlertInput,
    build_watchlist_alert_events,
    dispatch_watchlist_alert_notifications,
    list_watchlist_alert_events,
    upsert_watchlist_alert_events,
)
from app.services.watchlist_ai_review import RuleWatchlistAIReviewProvider


def _alert_input(
    symbol: str = "600519.SH",
    status: str = "持有中",
    pct_change: float = -5.2,
) -> WatchlistAlertInput:
    return WatchlistAlertInput(
        stock_id=1,
        symbol=symbol,
        name="贵州茅台",
        status=status,
        groups=["自选"],
        tags=[],
        entry_reason="趋势观察",
        planned_buy_price="回踩MA10",
        invalid_condition="跌破MA5",
        themes=["白酒"],
        last_review_conclusion="",
        today_risk_hint="",
        quote={
            "last_price": 100.0,
            "pct_change": pct_change,
            "turnover_rate": 8.0,
            "capital_strength": "",
        },
        metrics={
            "close": 100.0,
            "ma5": 105.0,
            "ma10": 98.0,
            "ma20": 95.0,
            "volume_ratio_5d": 1.2,
            "is_200d_high": False,
            "sector_strength_score": 0,
            "sector_limit_up_count": 0,
        },
        risk_signals=[],
    )


class RecordingNotificationService:
    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    def send_all(self, message: NotificationMessage) -> list[NotificationResult]:
        self.messages.append(message)
        return [NotificationResult(channel="test", status="sent", detail="sent")]


class FailedNotificationService:
    def send_all(self, message: NotificationMessage) -> list[NotificationResult]:
        return [NotificationResult(channel="test", status="failed", detail="timeout")]


def test_alert_engine_creates_high_risk_for_holding_ma_break():
    events = build_watchlist_alert_events(
        items=[_alert_input()],
        trade_date="2026-06-15",
        mode="intraday_morning",
        source_status={"tickflow": "ready"},
        now=datetime(2026, 6, 15, 10, 0, tzinfo=UTC),
    )

    assert [(event.event_type, event.severity) for event in events] == [("risk", "high")]
    assert events[0].trigger_key == "600519.SH:risk:plan_invalid_or_ma_break"
    assert "跌破MA5" in events[0].trigger_reason


def test_alert_engine_requires_momentum_plus_volume_for_opportunity():
    item = _alert_input(status="观察中", pct_change=2.0)
    item.metrics["close"] = 106.0
    item.metrics["ma5"] = 105.0
    item.metrics["volume_ratio_5d"] = 1.0
    item.metrics["sector_strength_score"] = 0

    events = build_watchlist_alert_events(
        items=[item],
        trade_date="2026-06-15",
        mode="daily_review",
        source_status={"tickflow": "ready"},
        now=datetime(2026, 6, 15, 19, 30, tzinfo=UTC),
    )

    assert [event.event_type for event in events] == []


def test_alert_engine_creates_opportunity_for_momentum_volume_resonance():
    item = _alert_input(status="观察中", pct_change=4.0)
    item.metrics["close"] = 108.0
    item.metrics["ma5"] = 105.0
    item.metrics["volume_ratio_5d"] = 1.8

    events = build_watchlist_alert_events(
        items=[item],
        trade_date="2026-06-15",
        mode="daily_review",
        source_status={"tickflow": "ready"},
        now=datetime(2026, 6, 15, 19, 30, tzinfo=UTC),
    )

    assert [(event.event_type, event.severity) for event in events] == [
        ("opportunity", "medium")
    ]
    assert events[0].trigger_key == "600519.SH:opportunity:momentum_volume"


def test_upsert_watchlist_alert_events_dedupes_by_trigger_key_and_payload_hash(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    init_db(engine)
    first_seen = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)
    second_seen = datetime(2026, 6, 15, 14, 30, tzinfo=UTC)
    first = build_watchlist_alert_events(
        items=[_alert_input()],
        trade_date="2026-06-15",
        mode="intraday_morning",
        source_status={"tickflow": "ready"},
        now=first_seen,
    )
    second = build_watchlist_alert_events(
        items=[_alert_input(pct_change=-5.7)],
        trade_date="2026-06-15",
        mode="intraday_afternoon",
        source_status={"tickflow": "ready"},
        now=second_seen,
    )
    second[0].market_snapshot["close"] = 99.5

    assert first[0].payload_hash == second[0].payload_hash

    created = upsert_watchlist_alert_events(engine, first)
    updated = upsert_watchlist_alert_events(engine, second)

    assert len(created) == 1
    assert len(updated) == 1
    with session_scope(engine) as session:
        rows = session.query(WatchlistAlertEvent).all()
        assert len(rows) == 1
        assert rows[0].first_seen_at == first_seen.replace(tzinfo=None)
        assert rows[0].last_seen_at == second_seen.replace(tzinfo=None)
        assert rows[0].market_snapshot["pct_change"] == -5.7
        assert rows[0].market_snapshot["close"] == 99.5
        assert rows[0].status == "active"
    listed = list_watchlist_alert_events(engine)
    assert [event["trigger_key"] for event in listed] == [
        "600519.SH:risk:plan_invalid_or_ma_break"
    ]
    assert listed[0]["last_seen_at"] == second_seen.isoformat()


def test_upsert_watchlist_alert_events_accepts_naive_datetimes(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    init_db(engine)
    first = build_watchlist_alert_events(
        items=[_alert_input()],
        trade_date="2026-06-15",
        mode="intraday_morning",
        source_status={"tickflow": "ready"},
        now=datetime(2026, 6, 15, 10, 0),
    )
    second = build_watchlist_alert_events(
        items=[_alert_input()],
        trade_date="2026-06-15",
        mode="intraday_afternoon",
        source_status={"tickflow": "ready"},
        now=datetime(2026, 6, 15, 14, 30),
    )

    upsert_watchlist_alert_events(engine, first)
    upsert_watchlist_alert_events(engine, second)

    listed = list_watchlist_alert_events(engine)
    assert len(listed) == 1
    assert listed[0]["last_seen_at"] == "2026-06-15T14:30:00+00:00"


def test_rule_ai_commentary_summarizes_alert_events():
    provider = RuleWatchlistAIReviewProvider()

    result = provider.generate_alert_commentary(
        {
            "events": [
                {
                    "symbol": "600519.SH",
                    "name": "贵州茅台",
                    "event_type": "risk",
                    "trigger_reason": "跌破MA5",
                }
            ]
        }
    )

    assert result["summary"] == "本次触发 1 条自选股提醒。"
    assert result["comments"]["600519.SH"].startswith("贵州茅台触发risk")


def test_dispatch_watchlist_alert_notifications_sends_and_marks_events(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    init_db(engine)
    now = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)
    risk = build_watchlist_alert_events(
        items=[_alert_input()],
        trade_date="2026-06-15",
        mode="intraday_morning",
        source_status={"tickflow": "ready"},
        now=now,
    )
    opportunity_item = _alert_input(symbol="000001.SZ", status="观察中", pct_change=4.0)
    opportunity_item.name = "平安银行"
    opportunity_item.metrics["close"] = 108.0
    opportunity_item.metrics["ma5"] = 105.0
    opportunity_item.metrics["volume_ratio_5d"] = 2.0
    opportunity = build_watchlist_alert_events(
        items=[opportunity_item],
        trade_date="2026-06-15",
        mode="daily_review",
        source_status={"tickflow": "ready"},
        now=now,
    )
    upsert_watchlist_alert_events(engine, risk + opportunity)
    notification_service = RecordingNotificationService()

    result = dispatch_watchlist_alert_notifications(
        engine,
        notification_service=notification_service,
        now=datetime(2026, 6, 15, 10, 5, tzinfo=UTC),
    )

    assert result["sent_count"] == 2
    assert [message.title for message in notification_service.messages] == [
        "高危风险提醒",
        "自选股机会提醒",
    ]
    assert "贵州茅台" in notification_service.messages[0].body
    assert "平安银行" in notification_service.messages[1].body
    with session_scope(engine) as session:
        rows = session.query(WatchlistAlertEvent).order_by(WatchlistAlertEvent.symbol).all()
        assert all(row.sent_at is not None for row in rows)
        assert all(row.notification_status["sent"] is True for row in rows)


def test_dispatch_watchlist_alert_notifications_keeps_failed_events_pending(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    init_db(engine)
    now = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)
    events = build_watchlist_alert_events(
        items=[_alert_input()],
        trade_date="2026-06-15",
        mode="intraday_morning",
        source_status={"tickflow": "ready"},
        now=now,
    )
    upsert_watchlist_alert_events(engine, events)

    result = dispatch_watchlist_alert_notifications(
        engine,
        notification_service=FailedNotificationService(),
        now=datetime(2026, 6, 15, 10, 5, tzinfo=UTC),
    )

    assert result["sent_count"] == 0
    with session_scope(engine) as session:
        row = session.query(WatchlistAlertEvent).one()
        assert row.sent_at is None
        assert row.notification_status["sent"] is False
        assert row.notification_status["channels"][0]["status"] == "failed"


def test_dispatch_watchlist_alert_notifications_skips_non_pending_events(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    init_db(engine)
    now = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)
    events = build_watchlist_alert_events(
        items=[
            _alert_input(symbol="600519.SH"),
            _alert_input(symbol="000001.SZ"),
            _alert_input(symbol="000002.SZ"),
        ],
        trade_date="2026-06-15",
        mode="intraday_morning",
        source_status={"tickflow": "ready"},
        now=now,
    )
    upsert_watchlist_alert_events(engine, events)
    with session_scope(engine) as session:
        rows = session.query(WatchlistAlertEvent).order_by(WatchlistAlertEvent.symbol).all()
        rows[0].sent_at = now
        rows[1].acknowledged_at = now
        rows[2].muted_until = now + timedelta(hours=1)

    notification_service = RecordingNotificationService()
    result = dispatch_watchlist_alert_notifications(
        engine,
        notification_service=notification_service,
        now=now,
    )

    assert result["sent_count"] == 0
    assert notification_service.messages == []


def test_dispatch_watchlist_alert_notifications_is_idempotent_after_success(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    init_db(engine)
    now = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)
    events = build_watchlist_alert_events(
        items=[_alert_input()],
        trade_date="2026-06-15",
        mode="intraday_morning",
        source_status={"tickflow": "ready"},
        now=now,
    )
    upsert_watchlist_alert_events(engine, events)
    notification_service = RecordingNotificationService()

    dispatch_watchlist_alert_notifications(engine, notification_service=notification_service, now=now)
    second = dispatch_watchlist_alert_notifications(
        engine,
        notification_service=notification_service,
        now=now + timedelta(minutes=1),
    )

    assert second["sent_count"] == 0
    assert len(notification_service.messages) == 1


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


def test_watchlist_alert_event_model_defaults_payloads(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    init_db(engine)
    seen_at = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)

    with session_scope(engine) as session:
        session.add(
            WatchlistAlertEvent(
                symbol="000001.SZ",
                name="平安银行",
                event_type="opportunity",
                severity="medium",
                trigger_key="000001.SZ:opportunity:momentum_volume",
                payload_hash="hash-2",
                trigger_reason="动量与量能共振",
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
        )

    with session_scope(engine) as session:
        row = session.query(WatchlistAlertEvent).filter_by(symbol="000001.SZ").one()
        assert row.stock_id is None
        assert row.status == "active"
        assert row.rule_snapshot == {}
        assert row.market_snapshot == {}
        assert row.source_status == {}
        assert row.notification_status == {}
        assert row.sent_at is None
        assert row.acknowledged_at is None
        assert row.muted_until is None
        assert row.created_at is not None
        assert row.updated_at is not None
