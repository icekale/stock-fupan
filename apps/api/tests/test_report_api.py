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
from app.providers.market import (
    FakeMarketDataProvider,
    FallbackMarketDataProvider,
    MarketBreadth,
    MarketCloseSnapshot,
)
from app.rules.scoring import RawSectorInput
from app.providers.news import FakeNewsProvider
from app.providers.review_sources import ReviewSourceResult, ReviewStockEvidence, ReviewThemeEvidence
from app.providers.tickflow import FakeTickFlowProvider, WatchlistQuote
from app.renderers.html_renderer import render_mobile_report_html
from app.rules.scoring import score_sectors
from app.rules.validation import validate_narrative_facts
from app.schemas.report import (
    IndexSnapshot,
    NextDayPrediction,
    PredictionConfidence,
    PredictionStockFocus,
    ReportDTO,
    ReportKind,
    SectorCandidate,
)
from app.services import report_generator as report_generator_module
from app.services.assets import write_json
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


def test_mobile_report_renderer_uses_reference_article_visual_system(tmp_path: Path) -> None:
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

    expected_reference_markers = [
        'maximum-scale=1.0, user-scalable=no',
        'class="article-wrap"',
        'class="article-card"',
        'class="header-date"',
        'class="header-title"',
        'class="header-sub"',
        'class="preamble"',
        'class="table-wrap"',
        'class="point-list"',
        'class="footer-disclaimer"',
        "--navy:",
        "--gold:",
        "--table-hdr:",
    ]
    old_visual_markers = [
        'class="page"',
        'class="paper"',
        'class="hero"',
        "module-card",
        "sector-card",
    ]

    for marker in expected_reference_markers:
        assert marker in html
    for marker in old_visual_markers:
        assert marker not in html


def test_mobile_report_renderer_uses_responsive_wide_article_layout(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")
    html = render_mobile_report_html(result.report)

    assert "max-width: 1080px;" in html
    assert "padding: 28px 24px 48px;" in html
    assert "font-size: 15.5px;" in html
    assert "min-width: 760px;" in html
    assert "@media screen and (max-width: 720px)" in html
    assert "max-width: 640px;" not in html


def test_mobile_report_renderer_groups_sector_detail_into_scannable_blocks(
    tmp_path: Path,
) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")
    html = render_mobile_report_html(result.report)

    assert 'class="sector-block"' in html
    assert 'class="sector-meta"' in html
    assert 'class="sector-grid"' in html
    assert 'class="insight-card"' in html
    assert 'class="insight-card action-card"' in html
    assert "01 前排个股" in html
    assert "02 板块逻辑" in html
    assert "03 次日动作" in html


def test_mobile_report_renderer_uses_daily_summary_board(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")
    html = render_mobile_report_html(result.report)

    assert 'class="summary-board"' in html
    assert 'class="summary-main"' in html
    assert 'class="summary-side"' in html
    assert 'class="metric-grid"' in html
    assert 'class="metric-card"' in html
    assert "今日结论" in html
    assert "明日观察" in html
    assert "盘面温度" in html
    assert "结构标签" in html


def test_mobile_report_html_renders_next_day_prediction_section(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")
    result.report.next_day_predictions = [
        NextDayPrediction(
            sector="PCB",
            rank=1,
            continuation_probability=76,
            confidence=PredictionConfidence.HIGH,
            headline="PCB延续概率较高，重点观察前排分歧承接。",
            front_row_stocks=[
                PredictionStockFocus(
                    code="300476.SZ",
                    name="胜宏科技",
                    pct_change=20.0,
                    role="前排强势股",
                    source_tags=["同花顺复盘", "东方财富涨停复盘"],
                    observation="观察胜宏科技竞价是否强于板块平均。",
                )
            ],
            trigger_conditions=["观察胜宏科技竞价是否强于板块平均。"],
            invalidation_conditions=["胜宏科技低开低走。"],
            risk_labels=["高位加速", "单源确认"],
            source_basis=["同花顺复盘"],
            primary_basis=["TickFlow行情：强度82.0、排名1、板块涨幅+4.50%", "Anspire新闻：1条催化"],
            secondary_basis=["辅助复盘：同花顺复盘"],
            market_quality_basis=["东方财富涨停复盘：封板率64.21%"],
        )
    ]

    html = render_mobile_report_html(result.report)

    assert "次日强势概率与观察条件" in html
    assert "PCB" in html
    assert "76%" in html
    assert "观察胜宏科技竞价是否强于板块平均" in html
    assert "同花顺复盘" in html
    assert "市场质量" in html
    assert "东方财富涨停复盘：封板率64.21%" in html
    assert "主源" in html
    assert "TickFlow行情" in html
    assert "Anspire新闻" in html
    assert "辅助源" in html
    assert "辅助复盘：同花顺复盘" in html
    assert "未形成板块双源确认" in html
    assert "prediction-stock-table" in html
    assert "observation-cell" in html


def test_mobile_report_renderer_unifies_component_polish_and_sources(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")
    html = render_mobile_report_html(result.report)

    assert "--surface-soft:" in html
    assert "--shadow-soft:" in html
    assert "box-shadow: var(--shadow-soft);" in html
    assert ".table-wrap table" in html
    assert 'class="source-grid"' in html
    assert 'class="source-item"' in html
    assert 'class="source-name"' in html
    assert "主要来源" in html


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


class FrontlineStockMarketProvider(ConflictingRawAndScoredMarketProvider):
    def get_sector_frontline_stocks(self, sector_name: str) -> list[WatchlistQuote]:
        if sector_name != "半导体":
            return []
        return [
            WatchlistQuote(
                symbol="688981.SH",
                name="中芯国际",
                pct_change=12.3,
                turnover_cny=18_000_000_000,
            ),
            WatchlistQuote(
                symbol="600584.SH",
                name="长电科技",
                pct_change=10.01,
                turnover_cny=4_200_000_000,
            ),
        ]


def test_report_generator_merges_tickflow_frontline_stocks_into_strong_sectors(
    tmp_path: Path,
) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FrontlineStockMarketProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    semiconductor = next(sector for sector in result.report.sectors if sector.name == "半导体")
    assert [stock.name for stock in semiconductor.top_stocks[:2]] == ["中芯国际", "长电科技"]
    assert semiconductor.top_stocks[0].code == "688981.SH"
    assert semiconductor.top_stocks[0].turnover_cny == 18_000_000_000
    assert "TickFlow前排" in semiconductor.top_stocks[0].tags
    snapshot = json.loads(result.assets.snapshot.read_text(encoding="utf-8"))
    snapshot_sector = next(
        sector for sector in snapshot["report"]["sectors"] if sector["name"] == "半导体"
    )
    assert snapshot_sector["top_stocks"][0]["name"] == "中芯国际"


def test_report_generator_reads_frontline_stocks_through_market_fallback_wrapper(
    tmp_path: Path,
) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FallbackMarketDataProvider(
            primary=FrontlineStockMarketProvider(),
            fallback=FakeMarketDataProvider(),
            fallback_enabled=True,
        ),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    semiconductor = next(sector for sector in result.report.sectors if sector.name == "半导体")
    assert semiconductor.top_stocks[0].name == "中芯国际"


class TodayPowerMarketProvider:
    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=[IndexSnapshot(name="上证指数", code="000001", close=4145.37, pct_change=0.5)],
            breadth=MarketBreadth(up_count=3200, down_count=1800, limit_up_count=86, limit_down_count=4),
            turnover_cny=12345.67,
            market_state_tags=["放量", "分化"],
            raw_sectors=[
                RawSectorInput(
                    name="电力",
                    pct_change=4.2,
                    limit_up_count=5,
                    stock_up_ratio=0.76,
                    turnover_change=0.38,
                    news_weight=0.5,
                )
            ],
        )

    def get_sector_frontline_stocks(self, sector_name: str) -> list[WatchlistQuote]:
        if sector_name != "电力":
            return []
        return [
            WatchlistQuote(symbol="000539.SZ", name="粤电力Ａ", pct_change=10.04, turnover_cny=1_247_563_400)
        ]


class HistoricalThemeTickFlowProvider:
    provider_name = "tickflow"

    def __init__(self) -> None:
        self.requested_symbols: list[str] = []

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        self.requested_symbols.extend(symbols)
        quotes = {
            "600584.SH": WatchlistQuote(
                symbol="600584.SH",
                name="长电科技",
                pct_change=-3.2,
                turnover_cny=8_800_000_000,
                quote_time="2026-05-27T15:00:00+08:00",
            ),
            "002896.SZ": WatchlistQuote(
                symbol="002896.SZ",
                name="中大力德",
                pct_change=4.6,
                turnover_cny=1_200_000_000,
                quote_time="2026-05-27T15:00:00+08:00",
            ),
            "688183.SH": WatchlistQuote(
                symbol="688183.SH",
                name="生益电子",
                pct_change=-1.8,
                turnover_cny=2_400_000_000,
                quote_time="2026-05-27T15:00:00+08:00",
            ),
        }
        return [quotes[symbol] for symbol in symbols if symbol in quotes]


def test_report_generator_tracks_previous_strong_themes_not_in_today_top(tmp_path: Path) -> None:
    previous_snapshot = {
        "report": {
            "trade_date": "2026-05-26",
            "sectors": [
                {
                    "name": "先进封装",
                    "score": 91.0,
                    "rank": 1,
                    "pct_change": 7.8,
                    "top_stocks": [
                        {"code": "600584.SH", "name": "长电科技", "pct_change": 10.0},
                        {"code": "002185.SZ", "name": "华天科技", "pct_change": 10.0},
                    ],
                }
            ],
            "structured_review": {
                "sustainability_ranking": [
                    {"rank": 1, "sector": "先进封装", "rating": "high", "reason": "前排核心强势"}
                ],
                "sector_reviews": [
                    {
                        "sector": "存储芯片",
                        "sustainability": "low",
                        "strengths": [],
                        "weaknesses": ["昨日已明显转弱"],
                        "watch_items": ["观察是否弱修复"],
                    }
                ],
            },
        }
    }
    previous_dir = tmp_path / "2026-05-26" / "close" / "v001"
    write_json(previous_dir / "snapshot.json", previous_snapshot)

    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=TodayPowerMarketProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-27")

    assert [sector.name for sector in result.report.sectors] == ["电力"]
    assert result.report.structured_review is not None
    tracked = result.report.structured_review.historical_theme_reviews
    assert tracked[0].theme == "先进封装"
    assert tracked[0].judgement == "降级观察"
    assert "长电科技" in tracked[0].evidence[0]

    html = result.assets.report_html.read_text(encoding="utf-8")
    assert "前期强势主线跟踪" in html
    assert "先进封装" in html
    assert "降级观察" in html
    assert "今日未进入强势前排" in html


def test_report_generator_tracks_previous_reference_html_themes(tmp_path: Path) -> None:
    tickflow = HistoricalThemeTickFlowProvider()
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=TodayPowerMarketProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        previous_review_html_path=Path("/Users/kale/Downloads/2026-05-26_structured_review.html"),
        tickflow_provider=tickflow,
    )

    result = generator.generate_close_report("2026-05-27")

    assert result.report.structured_review is not None
    themes = [item.theme for item in result.report.structured_review.historical_theme_reviews]
    assert "先进封装/半导体设备" in themes
    assert "人形机器人" in themes
    assert "PCB前排核心" in themes
    assert "存储芯片" in themes
    advanced = result.report.structured_review.historical_theme_reviews[0]
    assert advanced.judgement == "降级观察"
    assert any("长电科技" in item for item in advanced.evidence)
    robot = next(item for item in result.report.structured_review.historical_theme_reviews if item.theme == "人形机器人")
    pcb = next(item for item in result.report.structured_review.historical_theme_reviews if item.theme == "PCB前排核心")
    assert any("中大力德" in item for item in robot.evidence)
    assert any("宝鼎科技" in item for item in pcb.evidence)
    assert all("连板晋级率" not in item for item in [*robot.evidence, *pcb.evidence])
    assert "600584.SH" in tickflow.requested_symbols
    assert "002896.SZ" in tickflow.requested_symbols
    assert any("长电科技 600584.SH 今日-3.20%" in item for item in advanced.current_stock_checks)
    assert any("中大力德 002896.SZ 今日+4.60%" in item for item in robot.current_stock_checks)

    html = result.assets.report_html.read_text(encoding="utf-8")
    assert "当日核心股校验" in html
    assert "长电科技 600584.SH 今日-3.20%" in html


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
    assert result.provider_status["market_tickflow"] == result.provider_status["market"]
    assert result.provider_status["watchlist_tickflow"] == {
        "provider": "tickflow",
        "status": "disabled",
        "fallback_used": False,
        "reason": "自选股模块未开启",
    }
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
    assert result.provider_status["watchlist_tickflow"] == {
        "provider": "fake_tickflow",
        "status": "success",
        "fallback_used": False,
        "reason": None,
    }
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

    electric = next(sector for sector in result.report.sectors if sector.name == "电力")
    assert electric.review_sources == []
