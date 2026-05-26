from pathlib import Path

from sqlalchemy import text

from app.db.models import Report, ReportKindModel, ReportStatusModel
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.providers.llm import FakeLLMProvider
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider


def test_report_model_persists_asset_path(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)

    with session_scope(engine) as session:
        report = Report(
            trade_date="2026-05-26",
            kind=ReportKindModel.CLOSE,
            version="v001",
            status=ReportStatusModel.READY_FOR_REVIEW,
            asset_dir="/tmp/reports/2026-05-26/close/v001",
            algorithm_versions={"sector_score": "sector_score_v1"},
        )
        session.add(report)

    with session_scope(engine) as session:
        loaded = session.query(Report).one()

    assert loaded.trade_date == "2026-05-26"
    assert loaded.kind == ReportKindModel.CLOSE
    assert loaded.version == "v001"
    assert loaded.status == ReportStatusModel.READY_FOR_REVIEW
    assert loaded.asset_dir == "/tmp/reports/2026-05-26/close/v001"
    assert loaded.algorithm_versions["sector_score"] == "sector_score_v1"
    assert loaded.created_at is not None
    assert loaded.updated_at is not None

    with engine.connect() as connection:
        row = connection.execute(text("select kind, status from reports")).one()

    assert row.kind == "close"
    assert row.status == "ready_for_review"


def test_fake_providers_return_deterministic_payloads() -> None:
    market = FakeMarketDataProvider()
    news = FakeNewsProvider()
    llm = FakeLLMProvider()

    market_snapshot = market.get_close_snapshot("2026-05-26")
    news_items = news.search_sector_news("机器人", "2026-05-26")
    narrative = llm.generate_narrative(market_snapshot.to_report_seed(news_items))

    assert market_snapshot.trade_date == "2026-05-26"
    assert market_snapshot.raw_sectors[0].name == "机器人"
    assert news_items[0].matched_sector == "机器人"
    assert narrative.conclusion
