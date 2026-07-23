from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base


def create_sqlite_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.replace("sqlite:///", "", 1))
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, connect_args={"check_same_thread": False})


def get_engine() -> Engine:
    return create_sqlite_engine(get_settings().database_url)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_report_quality_columns(engine)
    _ensure_watchlist_stock_columns(engine)
    _ensure_watchlist_alert_constraints(engine)


def _ensure_report_quality_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(reports)"))
        }
        if "quality_score" not in columns:
            connection.execute(text("ALTER TABLE reports ADD COLUMN quality_score INTEGER"))
        if "publish_status" not in columns:
            connection.execute(text("ALTER TABLE reports ADD COLUMN publish_status VARCHAR(32)"))
        if "quality_summary" not in columns:
            connection.execute(text("ALTER TABLE reports ADD COLUMN quality_summary VARCHAR(512)"))
        if "quality_gate" not in columns:
            connection.execute(text("ALTER TABLE reports ADD COLUMN quality_gate JSON"))


def _ensure_watchlist_stock_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        if "watchlist_stocks" not in tables:
            return
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(watchlist_stocks)"))
        }
        if "status" not in columns:
            connection.execute(
                text("ALTER TABLE watchlist_stocks ADD COLUMN status VARCHAR(32) DEFAULT '观察中'")
            )


def _ensure_watchlist_alert_constraints(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        if "watchlist_alert_events" not in tables:
            return
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_watchlist_alert_events_trigger_payload "
                "ON watchlist_alert_events (trigger_key, payload_hash)"
            )
        )


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
