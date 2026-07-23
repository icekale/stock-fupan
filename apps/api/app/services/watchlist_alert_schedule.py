from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import Engine, select

from app.db.models import WatchlistAlertScheduleConfig
from app.db.session import session_scope


class WatchlistAlertScheduleUpdate(BaseModel):
    enabled: bool
    morning_time: str = "10:00"
    afternoon_time: str = "14:30"
    review_time: str = "19:30"
    timezone: str = "Asia/Shanghai"


def get_watchlist_alert_schedule_status(engine: Engine, settings: object) -> dict[str, object]:
    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        session.flush()
        return _status_payload(config)


def update_watchlist_alert_schedule_status(
    engine: Engine,
    settings: object,
    update: WatchlistAlertScheduleUpdate,
) -> dict[str, object]:
    _parse_schedule_time(update.morning_time)
    _parse_schedule_time(update.afternoon_time)
    _parse_schedule_time(update.review_time)
    ZoneInfo(update.timezone)
    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        config.enabled = update.enabled
        config.morning_time = update.morning_time
        config.afternoon_time = update.afternoon_time
        config.review_time = update.review_time
        config.timezone = update.timezone
        session.flush()
        return _status_payload(config)


def run_due_watchlist_alert_schedule(
    engine: Engine,
    settings: object,
    run_scan,
    now: datetime | None = None,
) -> dict[str, object]:
    current_utc = _as_utc(now or datetime.now(UTC))
    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        if not config.enabled:
            return _status_payload(config)
        mode = _due_mode(config, current_utc)
        if mode is None:
            return _status_payload(config)
        trade_date = current_utc.astimezone(ZoneInfo(config.timezone)).date().isoformat()

    try:
        result = run_scan(mode, trade_date)
        last_result = {
            "status": str(result.get("status", "completed")),
            "mode": mode,
            "trade_date": trade_date,
        }
    except Exception as exc:
        last_result = {
            "status": "failed",
            "mode": mode,
            "trade_date": trade_date,
            "reason": str(exc) or exc.__class__.__name__,
        }

    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        config.last_run_at = current_utc
        config.last_result = last_result
        session.flush()
        return _status_payload(config)


def _get_or_create_config_in_session(
    session,
    settings: object,
) -> WatchlistAlertScheduleConfig:
    config = (
        session.execute(select(WatchlistAlertScheduleConfig).order_by(WatchlistAlertScheduleConfig.id))
        .scalars()
        .first()
    )
    if config is not None:
        return config
    config = WatchlistAlertScheduleConfig(
        enabled=bool(getattr(settings, "watchlist_alert_schedule_enabled", False)),
        morning_time=str(getattr(settings, "watchlist_alert_morning_time", "10:00")),
        afternoon_time=str(getattr(settings, "watchlist_alert_afternoon_time", "14:30")),
        review_time=str(getattr(settings, "watchlist_alert_review_time", "19:30")),
        timezone=str(getattr(settings, "watchlist_alert_timezone", "Asia/Shanghai")),
    )
    session.add(config)
    return config


def _status_payload(config: WatchlistAlertScheduleConfig) -> dict[str, object]:
    return {
        "enabled": config.enabled,
        "morning_time": config.morning_time,
        "afternoon_time": config.afternoon_time,
        "review_time": config.review_time,
        "timezone": config.timezone,
        "last_run_at": _as_utc(config.last_run_at).isoformat() if config.last_run_at else None,
        "last_result": config.last_result,
    }


def _due_mode(config: WatchlistAlertScheduleConfig, now: datetime) -> str | None:
    tz = ZoneInfo(config.timezone)
    local = now.astimezone(tz)
    last_mode = None
    if config.last_run_at is not None:
        last_run_at = _as_utc(config.last_run_at).astimezone(tz)
        if last_run_at.date() == local.date():
            last_mode = (config.last_result or {}).get("mode")
    for mode, value in _schedule_times(config):
        if last_mode is not None and _mode_order(mode) <= _mode_order(str(last_mode)):
            continue
        hour, minute = _parse_schedule_time(value)
        scheduled = datetime.combine(local.date(), time(hour=hour, minute=minute), tzinfo=tz)
        if local >= scheduled:
            return mode
    return None


def _schedule_times(config: WatchlistAlertScheduleConfig) -> list[tuple[str, str]]:
    return [
        ("intraday_morning", config.morning_time),
        ("intraday_afternoon", config.afternoon_time),
        ("daily_review", config.review_time),
    ]


def _mode_order(mode: str) -> int:
    order = {
        "intraday_morning": 0,
        "intraday_afternoon": 1,
        "daily_review": 2,
    }
    return order.get(mode, -1)


def _parse_schedule_time(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("time must use HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("time must use HH:MM")
    return hour, minute


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
