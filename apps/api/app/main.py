from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.db.models import Report, ReportKindModel, ReportStatusModel
from app.db.session import get_engine, init_db, session_scope
from app.providers.factory import create_provider_bundle
from app.services.report_generator import ReportGenerator
from app.watchlist.service import WatchlistImportService


class CreateCloseReportRequest(BaseModel):
    trade_date: str


class ImportWatchlistTextRequest(BaseModel):
    content: str
    source_name: str = "manual.txt"


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


@app.post("/api/watchlists/import-text")
def import_watchlist_text(request: ImportWatchlistTextRequest) -> dict[str, object]:
    result = _watchlist_service().import_text(request.content, source_name=request.source_name)
    return result.model_dump(mode="json")


@app.post("/api/watchlists/import-file")
async def import_watchlist_file(file: UploadFile) -> dict[str, object]:
    content = (await file.read()).decode("utf-8-sig", errors="ignore")
    result = _watchlist_service().import_text(content, source_name=file.filename or "upload.txt")
    return result.model_dump(mode="json")


@app.get("/api/watchlists/latest")
def get_latest_watchlist() -> dict[str, object]:
    return _watchlist_service().get_latest().model_dump(mode="json")


@app.post("/api/reports/close")
def create_close_report(request: CreateCloseReportRequest) -> dict[str, object]:
    settings = get_settings()
    with create_provider_bundle(settings) as providers:
        generator = ReportGenerator(
            reports_root=Path(settings.reports_root),
            market_provider=providers.market_provider,
            news_provider=providers.news_provider,
            llm_provider=providers.llm_provider,
            structured_review_provider=settings.structured_review_provider,
            structured_review_fallback_enabled=settings.structured_review_fallback_enabled,
        )
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
                kind=ReportKindModel.CLOSE,
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
        },
        "provider_status": result.provider_status,
    }
