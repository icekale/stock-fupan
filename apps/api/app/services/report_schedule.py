from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import Engine, select

from app.config import Settings
from app.db.models import Report, ReportKindModel, ReportScheduleConfig, ReportStatusModel
from app.db.session import session_scope


DEFAULT_REPORT_KIND = "close"
USABLE_PUBLISH_STATUSES = {"publishable", "degraded"}


class ReportScheduleUpdate(BaseModel):
    enabled: bool
    time: str = "19:00"
    timezone: str = "Asia/Shanghai"


def get_report_schedule_status(engine: Engine, settings: Settings) -> dict[str, object]:
    config = _get_or_create_config(engine, settings)
    return _status_payload(config)


def update_report_schedule_status(
    engine: Engine,
    settings: Settings,
    update: ReportScheduleUpdate,
) -> dict[str, object]:
    _validate_schedule_time(update.time)
    ZoneInfo(update.timezone)
    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        config.enabled = update.enabled
        config.time = update.time
        config.timezone = update.timezone
        session.flush()
        return _status_payload(config)


def run_due_report_schedule(
    engine: Engine,
    settings: Settings,
    generate_close_report,
    now: datetime | None = None,
) -> dict[str, object]:
    current_utc = now or datetime.now(UTC)
    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        if not config.enabled:
            return _status_payload(config)
        due_trade_date = _due_trade_date(config, current_utc)
        if due_trade_date is None:
            return _status_payload(config)
        existing = session.execute(
            select(Report).where(
                Report.trade_date == due_trade_date,
                Report.kind == ReportKindModel.CLOSE,
                Report.publish_status.in_(USABLE_PUBLISH_STATUSES),
            )
        ).scalars().first()
        if existing is not None:
            config.last_run_at = current_utc
            config.last_result = {
                "status": f"skipped_existing_{existing.publish_status}",
                "trade_date": due_trade_date,
                "kind": DEFAULT_REPORT_KIND,
                "publish_status": existing.publish_status,
            }
            session.flush()
            return _status_payload(config)

    try:
        result = generate_close_report(due_trade_date)
    except Exception as exc:
        with session_scope(engine) as session:
            config = _get_or_create_config_in_session(session, settings)
            config.last_run_at = current_utc
            config.last_result = {
                "status": "failed",
                "trade_date": due_trade_date,
                "kind": DEFAULT_REPORT_KIND,
                "reason": str(exc) or exc.__class__.__name__,
            }
            session.flush()
            return _status_payload(config)

    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        if result is not None:
            status = (
                ReportStatusModel.READY_FOR_REVIEW
                if result.validation.is_valid
                else ReportStatusModel.VALIDATION_FAILED
            )
            session.add(
                Report(
                    trade_date=result.report.trade_date,
                    kind=ReportKindModel(result.report.kind.value),
                    version=result.assets.version,
                    status=status,
                    asset_dir=str(result.assets.root),
                    algorithm_versions=result.report.algorithm_versions,
                    **_quality_gate_db_fields(result.report.quality_gate),
                )
            )
        quality_gate = _quality_gate_payload(getattr(getattr(result, "report", None), "quality_gate", None))
        publish_status = quality_gate.get("publish_status") if quality_gate else None
        quality_score = quality_gate.get("score") if quality_gate else None
        quality_summary = quality_gate.get("summary") if quality_gate else None
        last_result = {
            "status": f"generated_{publish_status}" if publish_status else "generated",
            "trade_date": due_trade_date,
            "kind": DEFAULT_REPORT_KIND,
        }
        if publish_status:
            last_result.update(
                {
                    "publish_status": publish_status,
                    "quality_score": quality_score,
                    "quality_summary": quality_summary,
                }
            )
        config.last_run_at = current_utc
        config.last_result = last_result
        session.flush()
        return _status_payload(config)


def _quality_gate_db_fields(quality_gate: object | None) -> dict[str, object]:
    payload = _quality_gate_payload(quality_gate)
    return {
        "quality_score": payload.get("score") if payload else None,
        "publish_status": payload.get("publish_status") if payload else None,
        "quality_summary": payload.get("summary") if payload else None,
        "quality_gate": payload,
    }


def _quality_gate_payload(quality_gate: object | None) -> dict[str, object] | None:
    if quality_gate is None:
        return None
    if isinstance(quality_gate, dict):
        return quality_gate
    model_dump = getattr(quality_gate, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return None


def _get_or_create_config(engine: Engine, settings: Settings) -> ReportScheduleConfig:
    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        session.flush()
        return ReportScheduleConfig(
            id=config.id,
            enabled=config.enabled,
            kind=config.kind,
            time=config.time,
            timezone=config.timezone,
            last_run_at=config.last_run_at,
            last_result=config.last_result,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )


def _get_or_create_config_in_session(session, settings: Settings) -> ReportScheduleConfig:
    config = session.execute(select(ReportScheduleConfig).order_by(ReportScheduleConfig.id)).scalars().first()
    if config is not None:
        return config
    config = ReportScheduleConfig(
        enabled=settings.report_schedule_enabled,
        kind=DEFAULT_REPORT_KIND,
        time=settings.report_schedule_close_time,
        timezone=settings.report_schedule_timezone,
    )
    session.add(config)
    return config


def _status_payload(config: ReportScheduleConfig) -> dict[str, object]:
    return {
        "enabled": config.enabled,
        "kind": config.kind,
        "time": config.time,
        "timezone": config.timezone,
        "next_run_at": _next_run_at(config).isoformat() if config.enabled else None,
        "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
        "last_result": config.last_result,
    }


def _next_run_at(config: ReportScheduleConfig, now: datetime | None = None) -> datetime:
    tz = ZoneInfo(config.timezone)
    current = now.astimezone(tz) if now else datetime.now(tz)
    hour, minute = _parse_schedule_time(config.time)
    scheduled = datetime.combine(current.date(), time(hour=hour, minute=minute), tzinfo=tz)
    if scheduled <= current:
        scheduled += timedelta(days=1)
    return scheduled.astimezone(UTC)


def _due_trade_date(config: ReportScheduleConfig, now: datetime) -> str | None:
    tz = ZoneInfo(config.timezone)
    current = now.astimezone(tz)
    hour, minute = _parse_schedule_time(config.time)
    scheduled = datetime.combine(current.date(), time(hour=hour, minute=minute), tzinfo=tz)
    if current < scheduled:
        return None
    if config.last_run_at is not None and config.last_run_at.astimezone(tz).date() == current.date():
        return None
    return current.date().isoformat()


def _validate_schedule_time(value: str) -> None:
    _parse_schedule_time(value)


def _parse_schedule_time(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("time must use HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("time must use HH:MM")
    return hour, minute
