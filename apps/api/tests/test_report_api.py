import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.main import app
from app.db.models import Report, ReportKindModel, ReportStatusModel
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.providers.llm import FakeLLMProvider, LLMFallbackError
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.providers.tickflow import FakeTickFlowProvider
from app.renderers.html_renderer import render_mobile_report_html
from app.rules.scoring import score_sectors
from app.rules.validation import validate_narrative_facts
from app.schemas.report import ReportDTO, ReportKind, SectorCandidate
from app.services import report_generator as report_generator_module
from app.services.report_generator import ReportGenerator
from app.watchlist.parser import WatchlistItem
from app.watchlist.service import WatchlistImportResult


@pytest.fixture(autouse=True)
def isolate_settings_and_png_export(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()

    def fake_export_png(html_path: Path, output_path: Path) -> None:
        assert html_path.exists()
        output_path.write_bytes(b"fake-png")

    monkeypatch.setattr(report_generator_module, "export_png", fake_export_png, raising=False)
    yield
    get_settings.cache_clear()


def test_create_close_report_api_returns_generated_report(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path))

    with TestClient(app) as client:
        response = client.post("/api/reports/close", json={"trade_date": "2026-05-26"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["report"]["trade_date"] == "2026-05-26"
    assert payload["report"]["sectors"][0]["name"] == "机器人"
    assert payload["validation"]["is_valid"] is True
    assert payload["assets"]["version"] == "v001"


def test_create_close_report_api_returns_provider_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path))
    monkeypatch.setenv("MARKET_PROVIDER", "fake")
    monkeypatch.setenv("NEWS_PROVIDER", "fake")

    with TestClient(app) as client:
        response = client.post("/api/reports/close", json={"trade_date": "2026-05-26"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_status"]["market"] == {
        "provider": "fake",
        "status": "success",
        "fallback_used": False,
        "reason": None,
    }
    assert payload["provider_status"]["news"][0]["sector"] == "机器人"

    snapshot_path = Path(payload["assets"]["root"]) / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["provider_status"] == payload["provider_status"]


def test_create_close_report_api_persists_report_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    reports_root = tmp_path / "reports"
    database_url = f"sqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setenv("REPORTS_ROOT", str(reports_root))
    monkeypatch.setenv("DATABASE_URL", database_url)

    with TestClient(app) as client:
        response = client.post("/api/reports/close", json={"trade_date": "2026-05-26"})

    assert response.status_code == 200
    engine = create_sqlite_engine(database_url)
    with session_scope(engine) as session:
        persisted = session.query(Report).one()

    assert persisted.trade_date == "2026-05-26"
    assert persisted.kind == ReportKindModel.CLOSE
    assert persisted.version == "v001"
    assert persisted.status == ReportStatusModel.READY_FOR_REVIEW
    assert persisted.asset_dir == str(reports_root / "2026-05-26" / "close" / "v001")
    assert persisted.algorithm_versions["sector_score"] == "sector_score_v1"


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
    assert result.assets.report_html.exists()


def test_report_generator_writes_structured_review_to_report_and_snapshot(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    assert result.report.structured_review is not None
    assert result.report.structured_review.topic == "放量分化 · 机器人领涨 · PCB轮动"
    assert result.report.structured_review.prediction_review.source == "manual_placeholder"

    report_dto = json.loads(result.assets.report_dto.read_text(encoding="utf-8"))
    snapshot = json.loads(result.assets.snapshot.read_text(encoding="utf-8"))
    assert result.report.structured_review.after_hours_news.domestic_catalysts
    assert result.report.structured_review.capital_rotation.actual_path
    assert report_dto["structured_review"]["tomorrow_judgement"]["most_likely_to_continue"] == "机器人"
    assert report_dto["structured_review"]["practical_conclusion"]["headline"].startswith("明日最实战")
    assert snapshot["report"]["structured_review"] == report_dto["structured_review"]
    assert snapshot["report"]["structured_review"]["index_mid_term_outlook"]["scenario_table"][0][
        "scenario"
    ] == "强势延续"


def test_report_generator_exports_png(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    assert result.assets.report_png.exists()
    assert result.assets.report_png.read_bytes() == b"fake-png"


def test_report_generator_writes_neutral_llm_metadata(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    llm_calls = json.loads(result.assets.llm_calls.read_text(encoding="utf-8"))
    assert llm_calls[0]["provider"] == "unknown"
    assert llm_calls[0]["model"] == "unknown"


def test_mobile_report_renderer_contains_core_sections(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")
    html = render_mobile_report_html(
        result.report,
        brand_name="复盘测试",
        disclaimer_enabled=True,
    )

    expected_titles = [
        "昨日预判验证",
        "先给结论",
        "盘面总览",
        "各板块详细分析",
        "盘后 / 隔夜消息梳理",
        "板块持续性排序",
        "资金轮动路径分析",
        "明日可介入标的与仓位建议",
        "去弱留强排序",
        "最实战的结论",
        "上证指数中期走势研判",
    ]

    assert "2026-05-26 A股复盘" in html
    for title in expected_titles:
        assert title in html
    assert "自选股观察" not in html
    assert "科技内部" in html
    assert "非投资建议" in html


class BrokenStructuredReviewLLM(FakeLLMProvider):
    provider_name = "openai"

    def generate_structured_review(self, seed: dict[str, object]):
        raise LLMFallbackError("OPENAI_API_KEY 未配置")


def test_report_generator_writes_structured_review_status_on_llm_fallback(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=BrokenStructuredReviewLLM(),
        structured_review_provider="llm",
        structured_review_fallback_enabled=True,
    )

    result = generator.generate_close_report("2026-05-26")

    assert result.structured_review_status == {
        "provider": "llm",
        "status": "fallback",
        "fallback_used": True,
        "reason": "OPENAI_API_KEY 未配置",
    }
    snapshot = json.loads(result.assets.snapshot.read_text(encoding="utf-8"))
    assert snapshot["structured_review_status"] == result.structured_review_status
class StaticWatchlistService:
    called = False

    def get_latest(self):
        self.called = True
        return WatchlistImportResult(
            import_id=1,
            item_count=2,
            items=[
                WatchlistItem(symbol="600000.SH", code="600000", exchange="SH", name="浦发银行"),
                WatchlistItem(symbol="000001.SZ", code="000001", exchange="SZ", name="平安银行"),
            ],
            warnings=[],
        )


class ExplodingTickFlowProvider:
    def get_quotes(self, symbols: list[str]):
        raise AssertionError(f"TickFlow should not be called: {symbols}")


def test_report_generator_disables_watchlist_by_default(tmp_path: Path) -> None:
    watchlist_service = StaticWatchlistService()
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        watchlist_service=watchlist_service,
        tickflow_provider=ExplodingTickFlowProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    assert watchlist_service.called is False
    assert result.report.watchlist_observation is None
    assert result.provider_status["tickflow"] == {
        "provider": "tickflow",
        "status": "disabled",
        "fallback_used": False,
        "reason": "自选股模块未开启",
    }
    html = render_mobile_report_html(result.report)
    assert "自选股观察" not in html


def test_report_generator_writes_watchlist_observation_and_tickflow_status_when_enabled(
    tmp_path: Path,
) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        watchlist_service=StaticWatchlistService(),
        tickflow_provider=FakeTickFlowProvider(),
        watchlist_enabled=True,
    )

    result = generator.generate_close_report("2026-05-26")

    assert result.report.watchlist_observation is not None
    assert result.report.watchlist_observation.total_count == 2
    assert result.provider_status["tickflow"] == {
        "provider": "fake_tickflow",
        "status": "success",
        "fallback_used": False,
        "reason": None,
    }
    snapshot = json.loads(result.assets.snapshot.read_text(encoding="utf-8"))
    assert snapshot["report"]["watchlist_observation"]["total_count"] == 2
    assert snapshot["provider_status"]["tickflow"] == result.provider_status["tickflow"]


def test_mobile_report_renderer_contains_watchlist_section(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        watchlist_service=StaticWatchlistService(),
        tickflow_provider=FakeTickFlowProvider(),
        watchlist_enabled=True,
    )

    result = generator.generate_close_report("2026-05-26")
    html = render_mobile_report_html(result.report)

    assert "自选股观察" in html
    assert "600000.SH" in html
