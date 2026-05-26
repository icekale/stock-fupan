from pathlib import Path

from sqlalchemy import text

from app.db.models import Report, ReportKindModel, ReportStatusModel
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.providers.llm import FakeLLMProvider
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.rules.scoring import score_sectors
from app.rules.validation import validate_narrative_facts
from app.schemas.report import ReportDTO, ReportKind, SectorCandidate
from app.services.report_generator import ReportGenerator


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
    report_seed = market_snapshot.to_report_seed(news_items)
    narrative = llm.generate_narrative(report_seed)
    scored_sectors = score_sectors(market_snapshot.raw_sectors)
    report = ReportDTO(
        trade_date=market_snapshot.trade_date,
        kind=ReportKind.CLOSE,
        title="2026.05.26 A股复盘",
        indices=market_snapshot.indices,
        breadth=market_snapshot.breadth,
        turnover_cny=market_snapshot.turnover_cny,
        market_state_tags=market_snapshot.market_state_tags,
        sectors=[
            SectorCandidate(
                name=sector.name,
                score=sector.score,
                rank=sector.rank,
                pct_change=sector.pct_change,
                reason="fake provider contract",
                factor_scores=sector.factor_scores,
            )
            for sector in scored_sectors
        ],
        narrative=narrative,
        news=news_items,
    )
    validation = validate_narrative_facts(report)

    assert market_snapshot.trade_date == "2026-05-26"
    assert market_snapshot.raw_sectors[0].name == "机器人"
    assert news_items[0].matched_sector == "机器人"
    assert set(report_seed) == {
        "trade_date",
        "indices",
        "breadth",
        "turnover_cny",
        "market_state_tags",
        "raw_sectors",
        "news",
    }
    assert report_seed["raw_sectors"][0] == {
        "name": "机器人",
        "pct_change": 5.88,
        "limit_up_count": 8,
        "stock_up_ratio": 0.82,
        "turnover_change": 0.35,
        "news_weight": 0.8,
    }
    assert report_seed["raw_sectors"][0] is not market_snapshot.raw_sectors[0].__dict__
    assert scored_sectors[0].name == "机器人"
    assert scored_sectors[0].rank == 1
    assert narrative.conclusion
    assert validation.is_valid
    assert validation.errors == []


def test_report_generator_writes_snapshot_files(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    assert result.report.trade_date == "2026-05-26"
    assert result.report.sectors[0].name == "机器人"
    assert result.validation.is_valid
    assert result.assets.report_dto.exists()
    assert result.assets.snapshot.exists()
    assert result.assets.news_raw.exists()
    assert result.assets.llm_calls.exists()
