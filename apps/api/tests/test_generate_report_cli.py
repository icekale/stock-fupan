from pathlib import Path

import pytest

from app.config import get_settings
from app.db.models import Report, ReportKindModel, ReportStatusModel
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.providers.factory import ProviderBundle
from app.providers.llm import FakeLLMProvider
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.providers.runtime_config import RuntimeProviderConfigInput, save_runtime_provider_config
from app.providers.tickflow import FakeTickFlowProvider
from app.services import report_generator as report_generator_module
from app.services.weekly_report_generator import WeeklyGeneratedReport
from app.services.assets import AssetPaths


@pytest.fixture(autouse=True)
def isolate_settings_and_png_export(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    monkeypatch.setenv("MARKET_PROVIDER", "fake")
    monkeypatch.setenv("NEWS_PROVIDER", "fake")
    monkeypatch.setenv("TICKFLOW_PROVIDER", "fake")
    monkeypatch.setenv("REVIEW_SOURCES_ENABLED", "false")

    def fake_export_png(html_path: Path, output_path: Path) -> None:
        assert html_path.exists()
        output_path.write_bytes(b"fake-png")

    def fake_export_pdf(html_path: Path, output_path: Path) -> None:
        assert html_path.exists()
        output_path.write_bytes(b"fake-pdf")

    monkeypatch.setattr(report_generator_module, "export_png", fake_export_png, raising=False)
    monkeypatch.setattr(report_generator_module, "export_pdf", fake_export_pdf, raising=False)
    yield
    get_settings.cache_clear()


def _fake_bundle() -> ProviderBundle:
    return ProviderBundle(
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        ocr_provider=object(),
        tickflow_provider=FakeTickFlowProvider(),
        review_source_provider=None,
    )


def test_generate_report_cli_writes_report_and_prints_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.cli import generate_report

    monkeypatch.setattr(generate_report, "create_provider_bundle", lambda settings, runtime_config=None: _fake_bundle())

    exit_code = generate_report.main([
        "--date",
        "2026-05-26",
        "--reports-root",
        str(tmp_path),
    ])

    captured = capsys.readouterr()
    report_html = tmp_path / "2026-05-26" / "close" / "v001" / "report.html"
    report_pdf = tmp_path / "2026-05-26" / "close" / "v001" / "report.pdf"
    snapshot = tmp_path / "2026-05-26" / "close" / "v001" / "snapshot.json"
    assert exit_code == 0
    assert report_html.exists()
    assert report_pdf.exists()
    assert snapshot.exists()
    assert f"HTML: {report_html}" in captured.out
    assert f"PDF: {report_pdf}" in captured.out
    assert f"Snapshot: {snapshot}" in captured.out
    assert "Validation: ok" in captured.out
    assert "Quality gate: blocked" in captured.out
    assert "Provider market: success" in captured.out
    assert "sk-" not in captured.out
    assert "tk_" not in captured.out


def test_generate_report_cli_can_write_midday_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cli import generate_report

    monkeypatch.setattr(generate_report, "create_provider_bundle", lambda settings, runtime_config=None: _fake_bundle())

    exit_code = generate_report.main([
        "--date",
        "2026-05-26",
        "--kind",
        "midday",
        "--reports-root",
        str(tmp_path),
    ])

    assert exit_code == 0
    assert (tmp_path / "2026-05-26" / "midday" / "v001" / "2026-05-26-午间复盘.html").exists()
    assert (tmp_path / "2026-05-26" / "midday" / "v001" / "2026-05-26-午间复盘.pdf").exists()


def test_generate_report_cli_can_write_weekly_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cli import generate_report

    def fake_weekly(start_date: str, end_date: str, reports_root: Path, settings: object):
        root = reports_root / f"{start_date}_{end_date}" / "weekly" / "v001"
        root.mkdir(parents=True)
        assets = AssetPaths(root=root, version="v001")
        assets.report_html.write_text("<html>weekly</html>", encoding="utf-8")
        assets.report_png.write_bytes(b"png")
        assets.report_pdf.write_bytes(b"pdf")
        (root / f"{start_date}_{end_date}-周报复盘.html").write_text("weekly", encoding="utf-8")
        return WeeklyGeneratedReport(
            trade_date=f"{start_date}_{end_date}",
            start_date=start_date,
            end_date=end_date,
            assets=assets,
            validation_errors=[],
            provider_status={},
            summary={"algorithm_versions": {"weekly_report": "weekly_report_daily_dimensions_v2"}},
        )

    monkeypatch.setattr(generate_report, "_generate_weekly_report", fake_weekly)

    exit_code = generate_report.main([
        "--date",
        "2026-05-29",
        "--kind",
        "weekly",
        "--reports-root",
        str(tmp_path),
    ])

    assert exit_code == 0
    assert (tmp_path / "2026-05-25_2026-05-29" / "weekly" / "v001" / "2026-05-25_2026-05-29-周报复盘.html").exists()


def test_generate_report_cli_returns_nonzero_for_invalid_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.cli import generate_report

    monkeypatch.setattr(generate_report, "create_provider_bundle", lambda settings, runtime_config=None: _fake_bundle())
    monkeypatch.setattr(
        generate_report,
        "validate_generated_report",
        lambda result: (False, ["示例校验失败"]),
    )

    exit_code = generate_report.main([
        "--date",
        "2026-05-26",
        "--reports-root",
        str(tmp_path),
    ])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Validation: failed" in captured.out
    assert "- 示例校验失败" in captured.out


def test_generate_report_cli_persists_report_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cli import generate_report

    reports_root = tmp_path / "reports"
    database_url = f"sqlite:///{tmp_path / 'reports.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(generate_report, "create_provider_bundle", lambda settings, runtime_config=None: _fake_bundle())

    exit_code = generate_report.main([
        "--date",
        "2026-05-26",
        "--reports-root",
        str(reports_root),
    ])

    engine = create_sqlite_engine(database_url)
    with session_scope(engine) as session:
        persisted = session.query(Report).one()

    assert exit_code == 0
    assert persisted.trade_date == "2026-05-26"
    assert persisted.kind == ReportKindModel.CLOSE
    assert persisted.status == ReportStatusModel.READY_FOR_REVIEW
    assert persisted.asset_dir == str(reports_root / "2026-05-26" / "close" / "v001")
    assert persisted.quality_score is not None
    assert persisted.quality_score < 70
    assert persisted.publish_status == "blocked"
    assert persisted.quality_summary.startswith("不可发布草稿")
    assert persisted.quality_gate["publish_status"] == "blocked"


def test_generate_report_cli_uses_runtime_provider_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cli import generate_report

    reports_root = tmp_path / "reports"
    database_url = f"sqlite:///{tmp_path / 'reports.db'}"
    engine = create_sqlite_engine(database_url)
    init_db(engine)
    save_runtime_provider_config(
        engine,
        RuntimeProviderConfigInput(
            market_provider="fake",
            news_provider="fake",
            review_sources=["a_stock_dragon_tiger"],
            fallback_enabled=True,
        ),
    )
    captured_review_sources: list[list[str] | None] = []

    def fake_create_provider_bundle(settings: object, runtime_config: object | None = None) -> ProviderBundle:
        captured_review_sources.append(
            list(runtime_config.review_sources) if runtime_config is not None else None
        )
        return _fake_bundle()

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(generate_report, "create_provider_bundle", fake_create_provider_bundle)

    exit_code = generate_report.main([
        "--date",
        "2026-05-26",
        "--reports-root",
        str(reports_root),
    ])

    assert exit_code == 0
    assert captured_review_sources == [["a_stock_dragon_tiger"]]


def test_load_local_env_files_prefers_api_env_over_root_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cli.generate_report import _load_local_env_files

    repo_root = tmp_path / "repo"
    api_dir = repo_root / "apps" / "api"
    api_dir.mkdir(parents=True)
    (repo_root / ".env").write_text("REPORT_BRAND_NAME=root-brand\n", encoding="utf-8")
    (api_dir / ".env").write_text("REPORT_BRAND_NAME=api-brand\n", encoding="utf-8")
    monkeypatch.chdir(api_dir)
    monkeypatch.delenv("REPORT_BRAND_NAME", raising=False)

    _load_local_env_files()

    assert get_settings().report_brand_name == "api-brand"
