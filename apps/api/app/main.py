from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.db.models import Report, ReportKindModel, ReportStatusModel
from app.db.session import get_engine, init_db, session_scope
from app.providers.llm import FakeLLMProvider
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.services.report_generator import ReportGenerator


class CreateCloseReportRequest(BaseModel):
    trade_date: str


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


@app.post("/api/reports/close")
def create_close_report(request: CreateCloseReportRequest) -> dict[str, object]:
    settings = get_settings()
    generator = ReportGenerator(
        reports_root=Path(settings.reports_root),
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
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
    }
