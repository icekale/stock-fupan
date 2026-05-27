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
from app.providers.market import FakeMarketDataProvider, MarketBreadth, MarketCloseSnapshot
from app.rules.scoring import RawSectorInput
from app.providers.news import FakeNewsProvider
from app.providers.review_sources import ReviewSourceResult, ReviewStockEvidence, ReviewThemeEvidence
from app.providers.tickflow import FakeTickFlowProvider
from app.renderers.html_renderer import render_mobile_report_html
from app.rules.scoring import score_sectors
from app.rules.validation import validate_narrative_facts
from app.schemas.report import IndexSnapshot, ReportDTO, ReportKind, SectorCandidate
from app.services import report_generator as report_generator_module
from app.services.report_generator import ReportGenerator
from app.watchlist.parser import WatchlistItem
from app.watchlist.service import WatchlistImportResult


@pytest.fixture(autouse=True)
def isolate_settings_and_png_export(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    monkeypatch.setenv("MARKET_PROVIDER", "fake")
    monkeypatch.setenv("NEWS_PROVIDER", "fake")
    monkeypatch.setenv("REVIEW_SOURCES_ENABLED", "false")

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
    assert "next_day_predictions" in payload["report"]
    assert payload["report"]["algorithm_versions"]["next_day_prediction"] == "next_day_prediction_v0_5"
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
    assert result.report.next_day_predictions
    assert result.report.algorithm_versions["next_day_prediction"] == "next_day_prediction_v0_5"

    report_dto = json.loads(result.assets.report_dto.read_text(encoding="utf-8"))
    snapshot = json.loads(result.assets.snapshot.read_text(encoding="utf-8"))
    assert result.report.structured_review.after_hours_news.domestic_catalysts
    assert result.report.structured_review.capital_rotation.actual_path
    assert report_dto["structured_review"]["tomorrow_judgement"]["most_likely_to_continue"] == "机器人"
    assert report_dto["structured_review"]["practical_conclusion"]["headline"].startswith("明日最实战")
    assert snapshot["report"]["structured_review"] == report_dto["structured_review"]
    assert report_dto["next_day_predictions"] == snapshot["report"]["next_day_predictions"]
    assert snapshot["report"]["algorithm_versions"]["next_day_prediction"] == "next_day_prediction_v0_5"
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
        "偏差原因",
        "先给结论",
        "对明日的核心判断",
        "盘面总览",
        "指数数据",
        "市场情绪",
        "市场结构特征",
        "各板块详细分析",
        "板块逻辑分析",
        "持续性分析",
        "下个交易日看法",
        "盘后 / 隔夜消息梳理",
        "板块持续性排序",
        "资金轮动路径分析",
        "实际轮动路径",
        "关键发现",
        "明日可介入标的与仓位建议",
        "去弱留强排序",
        "最实战的结论",
        "上证指数中期走势研判",
    ]

    assert "2026-05-26 A股复盘" in html
    for title in expected_titles:
        assert title in html
    assert "自选股观察" not in html
    assert "轮动强度" in html
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


class ConflictingRawAndScoredMarketProvider:
    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=[
                IndexSnapshot(name="上证指数", code="000001", close=3100.5, pct_change=1.2)
            ],
            breadth=MarketBreadth(up_count=3000, down_count=2000, limit_up_count=40, limit_down_count=5),
            turnover_cny=12000,
            market_state_tags=["分化", "放量"],
            raw_sectors=[
                RawSectorInput(
                    name="会展服务",
                    pct_change=5.23,
                    limit_up_count=0,
                    stock_up_ratio=0.2,
                    turnover_change=-0.2,
                    news_weight=0.0,
                ),
                RawSectorInput(
                    name="半导体",
                    pct_change=3.85,
                    limit_up_count=3,
                    stock_up_ratio=0.9,
                    turnover_change=0.8,
                    news_weight=0.8,
                ),
                RawSectorInput(
                    name="机器人",
                    pct_change=4.86,
                    limit_up_count=2,
                    stock_up_ratio=0.8,
                    turnover_change=0.5,
                    news_weight=0.6,
                ),
                RawSectorInput(
                    name="PCB",
                    pct_change=3.6,
                    limit_up_count=2,
                    stock_up_ratio=0.75,
                    turnover_change=0.5,
                    news_weight=0.6,
                ),
                RawSectorInput(
                    name="有色金属",
                    pct_change=3.3,
                    limit_up_count=2,
                    stock_up_ratio=0.7,
                    turnover_change=0.4,
                    news_weight=0.5,
                ),
                RawSectorInput(
                    name="电力",
                    pct_change=2.9,
                    limit_up_count=1,
                    stock_up_ratio=0.8,
                    turnover_change=0.6,
                    news_weight=0.5,
                ),
            ],
        )


def test_report_generator_narrative_uses_final_ranked_sectors(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=ConflictingRawAndScoredMarketProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")
    narrative_text = "\n".join(result.report.narrative.sector_commentary)

    assert result.report.sectors[0].name == "半导体"
    assert "半导体" in narrative_text
    assert "会展服务" not in narrative_text
    assert result.validation.is_valid
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

class FakeReviewSourceProvider:
    def collect(self, trade_date: str) -> list[ReviewSourceResult]:
        return [
            ReviewSourceResult(
                source="同花顺复盘",
                source_url="https://stock.10jqka.com.cn/fupan/",
                status="success",
                mainstream_views=["贵金属", "PCB"],
                themes=[
                    ReviewThemeEvidence(name="PCB", pct_change=4.2, reason="前排加速", source="同花顺复盘"),
                    ReviewThemeEvidence(name="贵金属", pct_change=4.1, reason="低开高走", source="同花顺复盘"),
                ],
                hot_stocks=[
                    ReviewStockEvidence(name="招金黄金", code="1818HK", pct_change=10.0, source="同花顺复盘"),
                    ReviewStockEvidence(name="生益电子", code="688183", pct_change=20.0, source="同花顺复盘"),
                    ReviewStockEvidence(name="宝鼎科技", code="002552", pct_change=10.0, source="同花顺复盘"),
                ],
                market_notes=[
                    "贵金属、有色金属板块低开高走，招金黄金早盘涨停。",
                    "PCB概念股午后多数上扬，生益电子20cm涨停，宝鼎科技涨停。",
                ],
            ),
            ReviewSourceResult(
                source="东方财富涨停复盘",
                source_url="https://stock.eastmoney.com/a/cztfp.html",
                status="success",
                themes=[ReviewThemeEvidence(name="PCB", source="东方财富涨停复盘")],
                hot_stocks=[ReviewStockEvidence(name="生益电子", pct_change=20.0, source="东方财富涨停复盘")],
                market_notes=["涨停复盘：PCB概念股集体爆发 生益电子20CM涨停"],
            ),
        ]


def test_report_generator_merges_curated_review_sources_into_strong_theme(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        review_source_provider=FakeReviewSourceProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    pcb = next(sector for sector in result.report.sectors if sector.name == "PCB")
    assert "同花顺复盘" in pcb.review_sources
    assert "东方财富涨停复盘" in pcb.review_sources
    assert any(stock.name == "生益电子" for stock in pcb.top_stocks)
    assert not any(stock.name == "招金黄金" for stock in pcb.top_stocks)
    assert any("PCB概念股午后多数上扬" in note for note in pcb.review_notes)
    assert result.provider_status["review_sources"][0]["source"] == "同花顺复盘"


class WeakThemeReviewSourceProvider:
    def collect(self, trade_date: str) -> list[ReviewSourceResult]:
        return [
            ReviewSourceResult(
                source="同花顺复盘",
                source_url="https://stock.10jqka.com.cn/fupan/",
                status="success",
                themes=[ReviewThemeEvidence(name="电力", pct_change=-0.45, source="同花顺复盘")],
                hot_stocks=[],
                market_notes=[],
            )
        ]


def test_report_generator_does_not_confirm_strong_theme_from_weak_review_source_theme(
    tmp_path: Path,
) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=ConflictingRawAndScoredMarketProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        review_source_provider=WeakThemeReviewSourceProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    assert all(sector.name != "电力" for sector in result.report.sectors)


class MixedThemeReviewSourceProvider:
    def collect(self, trade_date: str) -> list[ReviewSourceResult]:
        return [
            ReviewSourceResult(
                source="同花顺复盘",
                source_url="https://stock.10jqka.com.cn/fupan/",
                status="success",
                themes=[
                    ReviewThemeEvidence(name="PCB", source="同花顺复盘"),
                    ReviewThemeEvidence(name="有色金属", source="同花顺复盘"),
                ],
                hot_stocks=[
                    ReviewStockEvidence(name="生益电子", code="688183", pct_change=20.0, source="同花顺复盘"),
                    ReviewStockEvidence(name="宝鼎科技", code="002552", pct_change=10.0, source="同花顺复盘"),
                    ReviewStockEvidence(name="招金黄金", code="603000", pct_change=10.0, source="同花顺复盘"),
                    ReviewStockEvidence(name="西部黄金", code="601069", pct_change=7.8, source="同花顺复盘"),
                ],
                market_notes=[
                    "贵金属、有色金属板块低开高走，招金黄金早盘涨停，西部黄金涨幅居前。",
                    "PCB概念股午后多数上扬，生益电子20cm涨停，宝鼎科技涨停。",
                ],
            )
        ]


def test_report_generator_uses_curated_review_sources_as_primary_sector_gate(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=ConflictingRawAndScoredMarketProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        review_source_provider=MixedThemeReviewSourceProvider(),
    )

    result = generator.generate_close_report("2026-05-26")
    narrative_text = "\n".join(
        [
            result.report.narrative.conclusion,
            *result.report.narrative.sector_commentary,
            result.report.narrative.tomorrow,
        ]
    )

    assert [sector.name for sector in result.report.sectors] == ["PCB", "有色金属"]
    assert [sector.rank for sector in result.report.sectors] == [1, 2]
    assert all(sector.review_sources for sector in result.report.sectors)
    assert "半导体" not in narrative_text
    assert "机器人" not in narrative_text
