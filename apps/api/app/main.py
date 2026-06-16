from collections.abc import AsyncIterator
import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
import logging
from pathlib import Path
import shutil
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.db.models import Report, ReportKindModel, ReportStatusModel
from app.db.session import get_engine, init_db, session_scope
from app.providers.factory import create_provider_bundle
from app.providers.ocr import OcrExtractError
from app.providers.runtime_config import (
    RuntimeProviderConfigInput,
    build_data_source_options_payload,
    config_status_items,
    get_runtime_provider_config,
    save_runtime_provider_config,
)
from app.services.assets import report_kind_label
from app.services.report_generator import ReportGenerator
from app.services.report_schedule import (
    ReportScheduleUpdate,
    get_report_schedule_status,
    run_due_report_schedule,
    update_report_schedule_status,
)
from app.services.tickflow_health import check_tickflow_health
from app.services.watchlist_alert_schedule import (
    WatchlistAlertScheduleUpdate,
    get_watchlist_alert_schedule_status,
    run_due_watchlist_alert_schedule,
    update_watchlist_alert_schedule_status,
)
from app.services.watchlist_alerts import (
    build_watchlist_alert_event_inputs,
    build_watchlist_alert_events,
    list_watchlist_alert_events,
    upsert_watchlist_alert_events,
)
from app.services.weekly_report_generator import (
    AStockWeeklyDataClient,
    WeeklyGeneratedReport,
    WeeklyReportGenerator,
    WEEKLY_REPORT_ALGORITHM_VERSION,
)
from app.watchlist.ocr_service import (
    OcrPreviewNotFoundError,
    UnsupportedOcrImageError,
    WatchlistOcrService,
)
from app.watchlist.service import WatchlistImportService


class CreateCloseReportRequest(BaseModel):
    trade_date: str


class ImportWatchlistTextRequest(BaseModel):
    content: str
    source_name: str = "manual.txt"


class ConfirmOcrPreviewRequest(BaseModel):
    preview_id: str


class ReportScheduleRequest(BaseModel):
    enabled: bool
    time: str = "19:00"
    timezone: str = "Asia/Shanghai"


class RunWatchlistAlertRequest(BaseModel):
    mode: str = "daily_review"
    trade_date: str


class WatchlistAlertScheduleRequest(BaseModel):
    enabled: bool
    morning_time: str = "10:00"
    afternoon_time: str = "14:30"
    review_time: str = "19:30"
    timezone: str = "Asia/Shanghai"


def _status_item(
    name: str,
    role: str,
    configured: bool,
    enabled: bool,
    status: str,
    detail: str,
) -> dict[str, object]:
    return {
        "name": name,
        "role": role,
        "configured": configured,
        "enabled": enabled,
        "status": status,
        "detail": detail,
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    init_db(engine)
    app.state.engine = engine
    app.state.report_schedule_task = asyncio.create_task(_report_schedule_loop())
    app.state.watchlist_alert_schedule_task = asyncio.create_task(_watchlist_alert_schedule_loop())
    try:
        yield
    finally:
        app.state.report_schedule_task.cancel()
        app.state.watchlist_alert_schedule_task.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.report_schedule_task
        with suppress(asyncio.CancelledError):
            await app.state.watchlist_alert_schedule_task


def _cors_allow_origins() -> list[str]:
    return [origin.strip() for origin in get_settings().cors_allow_origins.split(",") if origin.strip()]


app = FastAPI(title="A 股每日复盘 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHINA_TZ = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/tickflow/health")
def tickflow_health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return check_tickflow_health(
        api_key=settings.tickflow_api_key,
        base_url=settings.tickflow_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
    )


def _watchlist_service() -> WatchlistImportService:
    settings = get_settings()
    return WatchlistImportService(
        engine=app.state.engine,
        snapshot_root=Path(settings.watchlist_snapshot_root),
    )


def _watchlist_ocr_service() -> WatchlistOcrService:
    settings = get_settings()
    providers = create_provider_bundle(settings)
    return WatchlistOcrService(
        snapshot_root=Path(settings.watchlist_snapshot_root),
        ocr_provider=providers.ocr_provider,
        import_service=_watchlist_service(),
    )


async def _report_schedule_loop() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(_run_report_schedule_once)
        except Exception:
            logger.exception("report schedule tick failed")


async def _watchlist_alert_schedule_loop() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(_run_watchlist_alert_schedule_once)
        except Exception:
            logger.exception("watchlist alert schedule tick failed")


def _run_watchlist_alert_schedule_once() -> dict[str, object]:
    return run_due_watchlist_alert_schedule(
        engine=app.state.engine,
        settings=get_settings(),
        run_scan=lambda mode, trade_date: _run_watchlist_alert_scan(mode, trade_date),
    )


def _run_watchlist_alert_scan(mode: str, trade_date: str) -> dict[str, object]:
    items = build_watchlist_alert_event_inputs(app.state.engine)
    events = build_watchlist_alert_events(
        items=items,
        trade_date=trade_date,
        mode=mode,
        source_status={"tickflow": "not_checked"},
        now=datetime.now(UTC),
    )
    persisted = upsert_watchlist_alert_events(app.state.engine, events)
    return {
        "status": "completed",
        "mode": mode,
        "trade_date": trade_date,
        "item_count": len(items),
        "event_count": len(persisted),
    }


def _run_report_schedule_once() -> dict[str, object]:
    settings = get_settings()
    return run_due_report_schedule(
        engine=app.state.engine,
        settings=settings,
        generate_close_report=lambda trade_date: _generate_scheduled_close_report(trade_date, settings),
    )


def _generate_scheduled_close_report(trade_date: str, settings: object):
    runtime_config = get_runtime_provider_config(app.state.engine, settings)
    with create_provider_bundle(settings, runtime_config=runtime_config) as providers:
        generator = ReportGenerator(
            reports_root=Path(settings.reports_root),
            market_provider=providers.market_provider,
            news_provider=providers.news_provider,
            llm_provider=providers.llm_provider,
            structured_review_provider=settings.structured_review_provider,
            structured_review_fallback_enabled=settings.structured_review_fallback_enabled,
            watchlist_service=_watchlist_service(),
            quote_provider=providers.quote_provider,
            watchlist_enabled=settings.report_watchlist_enabled,
            review_source_provider=providers.review_source_provider,
            previous_review_html_path=settings.previous_review_html_path,
        )
        return generator.generate_close_report(trade_date)


@app.post("/api/watchlists/import-text")
def import_watchlist_text(request: ImportWatchlistTextRequest) -> dict[str, object]:
    result = _watchlist_service().import_text(request.content, source_name=request.source_name)
    return result.model_dump(mode="json")


@app.post("/api/watchlists/import-file")
async def import_watchlist_file(file: UploadFile) -> dict[str, object]:
    content = (await file.read()).decode("utf-8-sig", errors="ignore")
    result = _watchlist_service().import_text(content, source_name=file.filename or "upload.txt")
    return result.model_dump(mode="json")


@app.post("/api/watchlists/ocr-preview")
async def preview_watchlist_ocr(file: UploadFile) -> dict[str, object]:
    service = _watchlist_ocr_service()
    try:
        result = service.create_preview(
            image_bytes=await file.read(),
            mime_type=file.content_type or "application/octet-stream",
            filename=file.filename,
        )
    except UnsupportedOcrImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OcrExtractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        service.close()
    return result.model_dump(mode="json")


@app.post("/api/watchlists/ocr-confirm")
def confirm_watchlist_ocr(request: ConfirmOcrPreviewRequest) -> dict[str, object]:
    service = _watchlist_ocr_service()
    try:
        result = service.confirm_preview(request.preview_id)
    except OcrPreviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        service.close()
    return result.model_dump(mode="json")


@app.get("/api/watchlists/latest")
def get_latest_watchlist() -> dict[str, object]:
    return _watchlist_service().get_latest().model_dump(mode="json")


@app.get("/api/watchlist-alerts")
def get_watchlist_alerts() -> dict[str, object]:
    return {"items": list_watchlist_alert_events(app.state.engine)}


@app.post("/api/watchlist-alerts/run")
def run_watchlist_alerts(request: RunWatchlistAlertRequest) -> dict[str, object]:
    return _run_watchlist_alert_scan(request.mode, request.trade_date)


@app.get("/api/watchlist-alert-schedule/status")
def get_watchlist_alert_schedule() -> dict[str, object]:
    return get_watchlist_alert_schedule_status(app.state.engine, get_settings())


@app.put("/api/watchlist-alert-schedule/status")
def update_watchlist_alert_schedule(request: WatchlistAlertScheduleRequest) -> dict[str, object]:
    try:
        update = WatchlistAlertScheduleUpdate.model_validate(request.model_dump())
        return update_watchlist_alert_schedule_status(app.state.engine, get_settings(), update)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/config/status")
def get_config_status() -> dict[str, object]:
    settings = get_settings()
    config = get_runtime_provider_config(app.state.engine, settings)
    base_items = config_status_items(config, settings)
    watchlist_enabled = settings.report_watchlist_enabled
    ocr_is_fake = settings.ocr_provider == "fake"
    return {
        "items": [
            *base_items,
            _status_item(
                name="自选股模块",
                role="本地 · 自选股观察",
                configured=True,
                enabled=watchlist_enabled,
                status="local" if watchlist_enabled else "disabled",
                detail="REPORT_WATCHLIST_ENABLED=true" if watchlist_enabled else "REPORT_WATCHLIST_ENABLED=false",
            ),
            _status_item(
                name="OCR",
                role="本地 · 图片识别",
                configured=ocr_is_fake or bool(settings.openai_api_key),
                enabled=True,
                status="local" if ocr_is_fake else _external_status(True, bool(settings.openai_api_key)),
                detail=f"OCR_PROVIDER={settings.ocr_provider}",
            ),
        ]
    }


@app.get("/api/data-sources/options")
def get_data_source_options() -> dict[str, object]:
    settings = get_settings()
    config = get_runtime_provider_config(app.state.engine, settings)
    return build_data_source_options_payload(config, settings)


@app.put("/api/data-sources/options")
def update_data_source_options(request: RuntimeProviderConfigInput) -> dict[str, object]:
    try:
        config = save_runtime_provider_config(app.state.engine, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return build_data_source_options_payload(config, get_settings())


def _external_status(enabled: bool, configured: bool) -> str:
    if not enabled:
        return "disabled"
    if not configured:
        return "missing_key"
    return "ready"


@app.get("/api/reports")
def list_reports() -> dict[str, object]:
    with session_scope(app.state.engine) as session:
        rows = session.query(Report).order_by(Report.created_at.desc(), Report.id.desc()).limit(50).all()
        return {
            "items": [_report_list_item(row) for row in rows]
        }


def _report_list_item(row: Report) -> dict[str, object]:
    asset_dir = Path(row.asset_dir)
    html_path = asset_dir / "report.html"
    png_path = asset_dir / "report.png"
    pdf_path = asset_dir / "report.pdf"
    item = {
        "id": row.id,
        "trade_date": row.trade_date,
        "kind": row.kind.value,
        "kind_label": report_kind_label(row.kind.value),
        "version": row.version,
        "status": row.status.value,
        "asset_dir": row.asset_dir,
        "html": str(html_path),
        "png": str(png_path),
        "pdf": str(pdf_path) if pdf_path.exists() else None,
        "html_url": _asset_url(html_path),
        "png_url": _asset_url(png_path),
        "pdf_url": _asset_url(pdf_path) if pdf_path.exists() else None,
        "created_at": _china_time_iso(row.created_at),
        **_report_quality_list_fields(row),
    }
    return item


def _china_time_iso(value: object) -> str | None:
    if value is None:
        return None
    if not hasattr(value, "astimezone"):
        return None
    if getattr(value, "tzinfo", None) is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(CHINA_TZ).isoformat()


@app.get("/api/reports/asset")
def get_report_asset(path: str) -> FileResponse:
    asset_path = _validated_report_asset_path(path)
    return FileResponse(asset_path)


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: int) -> dict[str, object]:
    with session_scope(app.state.engine) as session:
        report = session.get(Report, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        asset_dir = _validated_report_dir_path(report.asset_dir)
        session.delete(report)

    if asset_dir.exists():
        shutil.rmtree(asset_dir)
    return {"deleted": True, "id": report_id}


@app.get("/api/report-schedule/status")
def report_schedule_status() -> dict[str, object]:
    return get_report_schedule_status(app.state.engine, get_settings())


@app.put("/api/report-schedule/status")
def update_report_schedule(request: ReportScheduleRequest) -> dict[str, object]:
    try:
        update = ReportScheduleUpdate(
            enabled=request.enabled,
            time=request.time,
            timezone=request.timezone,
        )
        return update_report_schedule_status(app.state.engine, get_settings(), update)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/reports/close")
def create_close_report(request: CreateCloseReportRequest) -> dict[str, object]:
    return _create_report_response(request, report_kind="close")


@app.post("/api/reports/midday")
def create_midday_report(request: CreateCloseReportRequest) -> dict[str, object]:
    return _create_report_response(request, report_kind="midday")


@app.post("/api/reports/weekly")
def create_weekly_report(request: CreateCloseReportRequest) -> dict[str, object]:
    settings = get_settings()
    start_date, end_date = _week_range(request.trade_date)
    result = _generate_weekly_report(start_date, end_date, Path(settings.reports_root), settings)
    status = (
        ReportStatusModel.READY_FOR_REVIEW
        if not result.validation_errors
        else ReportStatusModel.VALIDATION_FAILED
    )
    with session_scope(app.state.engine) as session:
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
    return _weekly_report_response(result)


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
    client = AStockWeeklyDataClient(
        timeout_seconds=getattr(settings, "provider_timeout_seconds", 120),
    )
    with create_provider_bundle(settings) as providers:
        generator = WeeklyReportGenerator(
            reports_root=reports_root,
            market_client=client,
            news_provider=providers.news_provider,
        )
        return generator.generate_weekly_report(start_date, end_date)


def _weekly_report_response(result: WeeklyGeneratedReport) -> dict[str, object]:
    label = report_kind_label("weekly")
    quality_gate = _not_applicable_quality_gate()
    return {
        "report": {
            "trade_date": result.trade_date,
            "kind": "weekly",
            "title": f"{result.start_date} 至 {result.end_date} {label}",
            "summary": result.summary,
            "algorithm_versions": {"weekly_report": WEEKLY_REPORT_ALGORITHM_VERSION},
            "quality_gate": quality_gate,
        },
        "validation": {
            "is_valid": not result.validation_errors,
            "errors": result.validation_errors,
        },
        "assets": {
            "root": str(result.assets.root),
            "version": result.assets.version,
            "html": str(result.assets.report_html),
            "png": str(result.assets.report_png),
            "pdf": str(result.assets.report_pdf),
            "named_html": str(result.assets.root / f"{result.trade_date}-{label}.html"),
            "named_png": str(result.assets.root / f"{result.trade_date}-{label}.png"),
            "named_pdf": str(result.assets.root / f"{result.trade_date}-{label}.pdf"),
            "html_url": _asset_url(result.assets.report_html),
            "png_url": _asset_url(result.assets.report_png),
            "pdf_url": _asset_url(result.assets.report_pdf),
        },
        "provider_status": result.provider_status,
    }


def _create_report_response(request: CreateCloseReportRequest, report_kind: str) -> dict[str, object]:
    settings = get_settings()
    runtime_config = get_runtime_provider_config(app.state.engine, settings)
    with create_provider_bundle(settings, runtime_config=runtime_config) as providers:
        generator = ReportGenerator(
            reports_root=Path(settings.reports_root),
            market_provider=providers.market_provider,
            news_provider=providers.news_provider,
            llm_provider=providers.llm_provider,
            structured_review_provider=settings.structured_review_provider,
            structured_review_fallback_enabled=settings.structured_review_fallback_enabled,
            watchlist_service=_watchlist_service(),
            quote_provider=providers.quote_provider,
            watchlist_enabled=settings.report_watchlist_enabled,
            review_source_provider=providers.review_source_provider,
            previous_review_html_path=settings.previous_review_html_path,
        )
        if report_kind == "midday":
            result = generator.generate_midday_report(request.trade_date)
        else:
            result = generator.generate_close_report(request.trade_date)
    status = (
        ReportStatusModel.READY_FOR_REVIEW
        if result.validation.is_valid
        else ReportStatusModel.VALIDATION_FAILED
    )

    with session_scope(app.state.engine) as session:
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

    return {
        "report": result.report.model_dump(mode="json"),
        "validation": {
            "is_valid": result.validation.is_valid,
            "errors": result.validation.errors,
        },
        "assets": {
            "root": str(result.assets.root),
            "version": result.assets.version,
            "html": str(result.assets.report_html),
            "png": str(result.assets.report_png),
            "pdf": str(result.assets.report_pdf),
            "named_html": str(result.assets.root / f"{result.report.trade_date}-{report_kind_label(result.report.kind.value)}.html"),
            "named_png": str(result.assets.root / f"{result.report.trade_date}-{report_kind_label(result.report.kind.value)}.png"),
            "named_pdf": str(result.assets.root / f"{result.report.trade_date}-{report_kind_label(result.report.kind.value)}.pdf"),
            "html_url": _asset_url(result.assets.report_html),
            "png_url": _asset_url(result.assets.report_png),
            "pdf_url": _asset_url(result.assets.report_pdf),
        },
        "provider_status": result.provider_status,
    }


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


def _report_quality_list_fields(row: Report) -> dict[str, object]:
    if row.publish_status:
        return {
            "quality_score": row.quality_score,
            "publish_status": row.publish_status,
            "quality_summary": row.quality_summary,
            "quality_gate": row.quality_gate,
        }
    if row.kind == ReportKindModel.CLOSE:
        return {
            "quality_score": None,
            "publish_status": "not_scored",
            "quality_summary": "旧版本报告未评分",
            "quality_gate": None,
        }
    return {
        "quality_score": None,
        "publish_status": "not_applicable",
        "quality_summary": "该报告类型暂不接入质量门禁",
        "quality_gate": None,
    }


def _asset_url(path: Path) -> str:
    return f"/api/reports/asset?path={quote(str(path), safe='')}"


def _validated_report_asset_path(path: str) -> Path:
    settings = get_settings()
    reports_root = Path(settings.reports_root).resolve(strict=False)
    asset_path = Path(path).resolve(strict=False)
    try:
        asset_path.relative_to(reports_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="asset path must stay under REPORTS_ROOT") from exc
    if not asset_path.exists() or asset_path.suffix not in {".html", ".png", ".pdf"}:
        raise HTTPException(status_code=404, detail="report asset not found")
    return asset_path


def _validated_report_dir_path(path: str) -> Path:
    settings = get_settings()
    reports_root = Path(settings.reports_root).resolve(strict=False)
    asset_dir = Path(path).resolve(strict=False)
    try:
        asset_dir.relative_to(reports_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="asset path must stay under REPORTS_ROOT") from exc
    return asset_dir
