from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import get_settings
from app.db.models import Report, ReportKindModel, ReportStatusModel
from app.db.session import get_engine, init_db, session_scope
from app.providers.factory import create_provider_bundle
from app.providers.ocr import OcrExtractError
from app.services.assets import report_kind_label
from app.services.report_generator import ReportGenerator
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
    yield


app = FastAPI(title="A 股每日复盘 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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


@app.get("/api/config/status")
def get_config_status() -> dict[str, object]:
    settings = get_settings()
    tickflow_enabled = settings.market_provider == "tickflow" or settings.tickflow_provider == "tickflow"
    anspire_enabled = settings.news_provider == "anspire"
    review_sources_enabled = settings.review_sources_enabled
    watchlist_enabled = settings.report_watchlist_enabled
    ocr_is_fake = settings.ocr_provider == "fake"
    return {
        "items": [
            _status_item(
                name="TickFlow",
                role="主源 · 行情",
                configured=bool(settings.tickflow_api_key),
                enabled=tickflow_enabled,
                status=_external_status(tickflow_enabled, bool(settings.tickflow_api_key)),
                detail=f"MARKET_PROVIDER={settings.market_provider} · TICKFLOW_PROVIDER={settings.tickflow_provider}",
            ),
            _status_item(
                name="Anspire",
                role="主源 · 新闻",
                configured=bool(settings.anspire_api_key),
                enabled=anspire_enabled,
                status=_external_status(anspire_enabled, bool(settings.anspire_api_key)),
                detail=f"NEWS_PROVIDER={settings.news_provider}",
            ),
            _status_item(
                name="同花顺复盘",
                role="辅助源 · 题材复盘",
                configured=bool(settings.ths_fupan_url),
                enabled=review_sources_enabled,
                status="ready" if review_sources_enabled else "disabled",
                detail="REVIEW_SOURCES_ENABLED=true" if review_sources_enabled else "REVIEW_SOURCES_ENABLED=false",
            ),
            _status_item(
                name="东方财富涨停复盘",
                role="辅助源 · 涨停质量",
                configured=bool(settings.eastmoney_ztfp_url),
                enabled=review_sources_enabled,
                status="ready" if review_sources_enabled else "disabled",
                detail="REVIEW_SOURCES_ENABLED=true" if review_sources_enabled else "REVIEW_SOURCES_ENABLED=false",
            ),
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
            "items": [
                {
                    "id": row.id,
                    "trade_date": row.trade_date,
                    "kind": row.kind.value,
                    "kind_label": report_kind_label(row.kind.value),
                    "version": row.version,
                    "status": row.status.value,
                    "asset_dir": row.asset_dir,
                    "html": str(Path(row.asset_dir) / "report.html"),
                    "png": str(Path(row.asset_dir) / "report.png"),
                    "html_url": _asset_url(Path(row.asset_dir) / "report.html"),
                    "png_url": _asset_url(Path(row.asset_dir) / "report.png"),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]
        }


@app.get("/api/reports/asset")
def get_report_asset(path: str) -> FileResponse:
    asset_path = _validated_report_asset_path(path)
    return FileResponse(asset_path)


@app.post("/api/reports/close")
def create_close_report(request: CreateCloseReportRequest) -> dict[str, object]:
    return _create_report_response(request, report_kind="close")


@app.post("/api/reports/midday")
def create_midday_report(request: CreateCloseReportRequest) -> dict[str, object]:
    return _create_report_response(request, report_kind="midday")


def _create_report_response(request: CreateCloseReportRequest, report_kind: str) -> dict[str, object]:
    settings = get_settings()
    with create_provider_bundle(settings) as providers:
        generator = ReportGenerator(
            reports_root=Path(settings.reports_root),
            market_provider=providers.market_provider,
            news_provider=providers.news_provider,
            llm_provider=providers.llm_provider,
            structured_review_provider=settings.structured_review_provider,
            structured_review_fallback_enabled=settings.structured_review_fallback_enabled,
            watchlist_service=_watchlist_service(),
            tickflow_provider=providers.tickflow_provider,
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
            "named_html": str(result.assets.root / f"{result.report.trade_date}-{report_kind_label(result.report.kind.value)}.html"),
            "named_png": str(result.assets.root / f"{result.report.trade_date}-{report_kind_label(result.report.kind.value)}.png"),
            "html_url": _asset_url(result.assets.report_html),
            "png_url": _asset_url(result.assets.report_png),
        },
        "provider_status": result.provider_status,
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
    if not asset_path.exists() or asset_path.suffix not in {".html", ".png"}:
        raise HTTPException(status_code=404, detail="report asset not found")
    return asset_path
