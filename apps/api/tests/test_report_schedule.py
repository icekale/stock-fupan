from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.db.models import Report, ReportKindModel, ReportScheduleConfig, ReportStatusModel
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.services.report_schedule import run_due_report_schedule


class RecordingGenerator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_close_report(self, trade_date: str):
        self.calls.append(trade_date)
        return None


def test_run_due_report_schedule_generates_close_report_after_scheduled_time(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'schedule.db'}")
    init_db(engine)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'schedule.db'}",
        reports_root=tmp_path / "reports",
        report_schedule_enabled=False,
    )
    with session_scope(engine) as session:
        session.add(ReportScheduleConfig(enabled=True, time="19:00", timezone="Asia/Shanghai"))

    generator = RecordingGenerator()
    status = run_due_report_schedule(
        engine=engine,
        settings=settings,
        generate_close_report=generator.generate_close_report,
        now=datetime(2026, 6, 2, 11, 1, tzinfo=UTC),
    )

    assert generator.calls == ["2026-06-02"]
    assert status["last_result"] == {
        "status": "generated",
        "trade_date": "2026-06-02",
        "kind": "close",
    }


def test_run_due_report_schedule_skips_existing_close_report(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'schedule.db'}")
    init_db(engine)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'schedule.db'}",
        reports_root=tmp_path / "reports",
        report_schedule_enabled=False,
    )
    with session_scope(engine) as session:
        session.add(ReportScheduleConfig(enabled=True, time="19:00", timezone="Asia/Shanghai"))
        session.add(
            Report(
                trade_date="2026-06-02",
                kind=ReportKindModel.CLOSE,
                version="v001",
                status=ReportStatusModel.READY_FOR_REVIEW,
                asset_dir=str(tmp_path / "reports" / "2026-06-02" / "close" / "v001"),
                algorithm_versions={},
            )
        )

    generator = RecordingGenerator()
    status = run_due_report_schedule(
        engine=engine,
        settings=settings,
        generate_close_report=generator.generate_close_report,
        now=datetime(2026, 6, 2, 11, 1, tzinfo=UTC),
    )

    assert generator.calls == []
    assert status["last_result"] == {
        "status": "skipped_existing",
        "trade_date": "2026-06-02",
        "kind": "close",
    }


def test_run_due_report_schedule_records_failed_generation(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'schedule.db'}")
    init_db(engine)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'schedule.db'}",
        reports_root=tmp_path / "reports",
        report_schedule_enabled=False,
    )
    with session_scope(engine) as session:
        session.add(ReportScheduleConfig(enabled=True, time="19:00", timezone="Asia/Shanghai"))

    def fail_generate(_trade_date: str):
        raise RuntimeError("provider failed")

    status = run_due_report_schedule(
        engine=engine,
        settings=settings,
        generate_close_report=fail_generate,
        now=datetime(2026, 6, 2, 11, 1, tzinfo=UTC),
    )

    assert status["last_result"] == {
        "status": "failed",
        "trade_date": "2026-06-02",
        "kind": "close",
        "reason": "provider failed",
    }
