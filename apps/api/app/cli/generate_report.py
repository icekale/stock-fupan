import argparse
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

from dotenv import dotenv_values

from app.config import get_settings
from app.db.models import Report, ReportKindModel, ReportStatusModel
from app.db.session import create_sqlite_engine, init_db
from app.db.session import session_scope
from app.providers.factory import create_provider_bundle
from app.services.report_generator import GeneratedReport, ReportGenerator
from app.services.weekly_report_generator import (
    TickFlowWeeklyDataClient,
    WeeklyGeneratedReport,
    WeeklyReportGenerator,
    WEEKLY_REPORT_ALGORITHM_VERSION,
)
from app.watchlist.service import WatchlistImportService


def validate_generated_report(result: GeneratedReport) -> tuple[bool, list[str]]:
    return result.validation.is_valid, result.validation.errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a local A-share review report.")
    parser.add_argument("--date", required=True, help="Trade date in YYYY-MM-DD format.")
    parser.add_argument("--kind", choices=("close", "midday", "weekly"), default="close", help="Report kind.")
    parser.add_argument("--reports-root", help="Override REPORTS_ROOT for this run.")
    args = parser.parse_args(argv)

    _load_local_env_files()
    get_settings.cache_clear()
    settings = get_settings()
    reports_root = Path(args.reports_root) if args.reports_root else Path(settings.reports_root)
    if args.kind == "weekly":
        start_date, end_date = _week_range(args.date)
        result = _generate_weekly_report(start_date, end_date, reports_root, settings)
        _persist_weekly_report_metadata(settings, result, is_valid=not result.validation_errors)
        _print_weekly_result(result)
        return 0 if not result.validation_errors else 1

    watchlist_service = _create_watchlist_service(settings)

    with create_provider_bundle(settings) as providers:
        generator = ReportGenerator(
            reports_root=reports_root,
            market_provider=providers.market_provider,
            news_provider=providers.news_provider,
            llm_provider=providers.llm_provider,
            structured_review_provider=settings.structured_review_provider,
            structured_review_fallback_enabled=settings.structured_review_fallback_enabled,
            watchlist_service=watchlist_service,
            tickflow_provider=providers.tickflow_provider,
            watchlist_enabled=settings.report_watchlist_enabled,
            review_source_provider=providers.review_source_provider,
            previous_review_html_path=settings.previous_review_html_path,
        )
        result = (
            generator.generate_midday_report(args.date)
            if args.kind == "midday"
            else generator.generate_close_report(args.date)
        )

    is_valid, errors = validate_generated_report(result)
    _persist_report_metadata(settings, result, is_valid)
    _print_result(result, is_valid, errors)
    return 0 if is_valid else 1


def _create_watchlist_service(settings: object) -> WatchlistImportService | None:
    if not getattr(settings, "report_watchlist_enabled", False):
        return None
    engine = create_sqlite_engine(str(settings.database_url))
    init_db(engine)
    return WatchlistImportService(
        engine=engine,
        snapshot_root=Path(settings.watchlist_snapshot_root),
    )


def _week_range(end_date: str) -> tuple[str, str]:
    parsed = date.fromisoformat(end_date)
    start = parsed - timedelta(days=parsed.weekday())
    return start.isoformat(), parsed.isoformat()


def _generate_weekly_report(
    start_date: str,
    end_date: str,
    reports_root: Path,
    settings: object,
) -> WeeklyGeneratedReport:
    client = TickFlowWeeklyDataClient(
        api_key=getattr(settings, "tickflow_api_key", ""),
        base_url=getattr(settings, "tickflow_base_url", "https://api.tickflow.org"),
        timeout_seconds=getattr(settings, "provider_timeout_seconds", 120),
    )
    news_provider = create_provider_bundle(settings).news_provider
    generator = WeeklyReportGenerator(
        reports_root=reports_root,
        tickflow_client=client,
        news_provider=news_provider,
    )
    return generator.generate_weekly_report(start_date, end_date)


def _persist_report_metadata(settings: object, result: GeneratedReport, is_valid: bool) -> None:
    engine = create_sqlite_engine(str(settings.database_url))
    init_db(engine)
    status = ReportStatusModel.READY_FOR_REVIEW if is_valid else ReportStatusModel.VALIDATION_FAILED
    with session_scope(engine) as session:
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


def _persist_weekly_report_metadata(
    settings: object,
    result: WeeklyGeneratedReport,
    is_valid: bool,
) -> None:
    engine = create_sqlite_engine(str(settings.database_url))
    init_db(engine)
    status = ReportStatusModel.READY_FOR_REVIEW if is_valid else ReportStatusModel.VALIDATION_FAILED
    with session_scope(engine) as session:
        session.add(
            Report(
                trade_date=result.trade_date,
                kind=ReportKindModel.WEEKLY,
                version=result.assets.version,
                status=status,
                asset_dir=str(result.assets.root),
                algorithm_versions={"weekly_report": WEEKLY_REPORT_ALGORITHM_VERSION},
                **_quality_gate_db_fields(_not_applicable_quality_gate()),
            )
        )


def _load_local_env_files() -> None:
    protected_keys = set(os.environ)
    cwd_env = Path.cwd() / ".env"
    root_env = Path.cwd().parents[1] / ".env" if len(Path.cwd().parents) > 1 else None
    if root_env is not None and root_env.exists():
        _load_env_file(root_env, protected_keys)
    if cwd_env.exists():
        _load_env_file(cwd_env, protected_keys)


def _load_env_file(path: Path, protected_keys: set[str]) -> None:
    for key, value in dotenv_values(path).items():
        if value is None or key in protected_keys:
            continue
        os.environ[key] = value


def _print_result(result: GeneratedReport, is_valid: bool, errors: list[str]) -> None:
    print(f"HTML: {result.assets.report_html}")
    print(f"PDF: {result.assets.report_pdf}")
    print(f"Snapshot: {result.assets.snapshot}")
    print(f"Validation: {'ok' if is_valid else 'failed'}")
    for error in errors:
        print(f"- {error}")
    _print_quality_gate(result.report.quality_gate)
    _print_provider_status(result.provider_status)
    print(f"Structured review: {result.structured_review_status.get('provider')}")


def _print_weekly_result(result: WeeklyGeneratedReport) -> None:
    print(f"HTML: {result.assets.report_html}")
    print(f"PDF: {result.assets.report_pdf}")
    print(f"Snapshot: {result.assets.snapshot}")
    print(f"Validation: {'ok' if not result.validation_errors else 'failed'}")
    for error in result.validation_errors:
        print(f"- {error}")
    _print_quality_gate(_not_applicable_quality_gate())


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


def _not_applicable_quality_gate() -> dict[str, object]:
    return {
        "score": None,
        "publish_status": "not_applicable",
        "label": "暂不评分",
        "summary": "该报告类型暂不接入质量门禁",
        "hard_failures": [],
        "warnings": [],
        "provider_summary": {},
    }


def _print_quality_gate(quality_gate: object | None) -> None:
    payload = _quality_gate_payload(quality_gate)
    if not payload:
        print("Quality gate: not_scored")
        return
    status = payload.get("publish_status")
    score = payload.get("score")
    label = payload.get("label") or payload.get("summary") or ""
    score_text = "unscored" if score is None else f"{score}/100"
    print(f"Quality gate: {status} {score_text} - {label}")
    for issue in payload.get("hard_failures") or []:
        if isinstance(issue, dict):
            print(f"- hard: {issue.get('code')} {issue.get('message')}")
    for issue in payload.get("warnings") or []:
        if isinstance(issue, dict):
            print(f"- warning: {issue.get('code')} {issue.get('message')}")


def _print_provider_status(provider_status: dict[str, object]) -> None:
    market_status = provider_status.get("market")
    if isinstance(market_status, dict):
        print(f"Provider market: {_format_status(market_status)}")

    market_tickflow_status = provider_status.get("market_tickflow")
    if isinstance(market_tickflow_status, dict):
        print(f"Provider tickflow[market]: {_format_status(market_tickflow_status)}")

    watchlist_tickflow_status = provider_status.get("watchlist_tickflow")
    if isinstance(watchlist_tickflow_status, dict):
        print(f"Provider tickflow[watchlist]: {_format_status(watchlist_tickflow_status)}")

    news_statuses = provider_status.get("news")
    if isinstance(news_statuses, list):
        for status in news_statuses:
            if isinstance(status, dict):
                sector = status.get("sector", "unknown")
                print(f"Provider news[{sector}]: {_format_status(status)}")

    review_statuses = provider_status.get("review_sources")
    if isinstance(review_statuses, list):
        for status in review_statuses:
            if isinstance(status, dict):
                source = status.get("source", status.get("provider", "unknown"))
                print(f"Provider review[{source}]: {_format_status(status)}")


def _format_status(status: dict[str, object]) -> str:
    value = str(status.get("status", "unknown"))
    if status.get("fallback_used"):
        value += " fallback"
    reason = status.get("reason")
    if reason:
        value += f" ({reason})"
    return value


if __name__ == "__main__":
    raise SystemExit(main())
