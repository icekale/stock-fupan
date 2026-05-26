# A 股收盘复盘 v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v0.1 local web app that manually generates an A 股收盘复盘 report from mockable market/news/LLM providers, validates facts, supports human overrides, and exports HTML/PNG assets.

**Architecture:** Use a monorepo with FastAPI in `apps/api` and Next.js in `apps/web`. The backend owns provider adapters, rules, persistence, orchestration, report rendering, and Playwright PNG export; the frontend owns the step-based review workflow and consumes backend APIs. Keep providers mockable so tests do not require live AkShare, Anspire, or OpenAI credentials.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, SQLite, Jinja2, Playwright, pytest, Next.js, React, TypeScript, Tailwind, shadcn/ui-compatible components, pnpm, uv.

---

## File Structure

Create these files and keep responsibilities narrow:

```text
.
├── .env.example
├── .gitignore
├── docker-compose.yml
├── package.json
├── pnpm-workspace.yaml
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── db/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── models.py
│   │   │   │   └── session.py
│   │   │   ├── providers/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── market.py
│   │   │   │   ├── news.py
│   │   │   │   └── llm.py
│   │   │   ├── renderers/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── html_renderer.py
│   │   │   │   ├── png_exporter.py
│   │   │   │   └── templates/
│   │   │   │       └── mobile_report.html.j2
│   │   │   ├── rules/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── scoring.py
│   │   │   │   └── validation.py
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   └── report.py
│   │   │   └── services/
│   │   │       ├── __init__.py
│   │   │       ├── assets.py
│   │   │       ├── overrides.py
│   │   │       └── report_generator.py
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_assets.py
│   │       ├── test_scoring.py
│   │       ├── test_validation.py
│   │       └── test_report_api.py
│   └── web/
│       ├── package.json
│       ├── next.config.ts
│       ├── postcss.config.mjs
│       ├── tailwind.config.ts
│       ├── tsconfig.json
│       ├── app/
│       │   ├── globals.css
│       │   ├── layout.tsx
│       │   └── page.tsx
│       ├── components/
│       │   ├── ReportPreview.tsx
│       │   ├── Stepper.tsx
│       │   └── TaskProgress.tsx
│       └── lib/
│           ├── api.ts
│           └── types.ts
├── packages/
│   └── shared/
│       └── openapi/
│           └── .gitkeep
└── reports/
    └── .gitkeep
```

Do not implement v0.2/v0.3 features in this plan: no scheduler, no午盘, no自选股, no OCR, no Markdown/PDF export, no auth, no system health page.

---

### Task 1: Bootstrap Monorepo

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `docker-compose.yml`
- Create: `reports/.gitkeep`
- Create: `packages/shared/openapi/.gitkeep`
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/app/__init__.py`
- Create: `apps/api/app/main.py`
- Create: `apps/api/tests/conftest.py`

- [ ] **Step 1: Create root workspace files**

Write `.gitignore`:

```gitignore
.DS_Store
.env
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
node_modules/
.next/
dist/
build/
reports/**
!reports/.gitkeep
.superpowers/
apps/api/data/
apps/api/playwright-report/
apps/api/test-results/
```

Write `.env.example`:

```dotenv
APP_ENV=development
DATABASE_URL=sqlite:///./data/stock_review.db
REPORTS_ROOT=../../reports
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
ANSPIRE_API_KEY=
NEWS_PROVIDER=anspire
NEWS_TOP_K=10
NEWS_LOOKBACK_HOURS=36
REPORT_BRAND_NAME=
REPORT_BRAND_FOOTER=
REPORT_DISCLAIMER_ENABLED=true
```

Write `package.json`:

```json
{
  "name": "stock-review-monorepo",
  "private": true,
  "scripts": {
    "dev:web": "pnpm --filter @stock-review/web dev",
    "test:web": "pnpm --filter @stock-review/web test",
    "lint:web": "pnpm --filter @stock-review/web lint"
  },
  "packageManager": "pnpm@9.15.0"
}
```

Write `pnpm-workspace.yaml`:

```yaml
packages:
  - "apps/web"
  - "packages/*"
```

Write `docker-compose.yml`:

```yaml
services:
  api:
    build:
      context: ./apps/api
    env_file:
      - .env
    ports:
      - "8000:8000"
    volumes:
      - ./reports:/workspace/reports
      - ./apps/api/data:/workspace/apps/api/data
  web:
    image: node:22-alpine
    working_dir: /workspace
    command: sh -c "corepack enable && pnpm install && pnpm dev:web"
    ports:
      - "3000:3000"
    volumes:
      - .:/workspace
    environment:
      NEXT_PUBLIC_API_BASE_URL: http://localhost:8000
```

Create placeholder files:

```bash
mkdir -p reports packages/shared/openapi apps/api/app apps/api/tests
touch reports/.gitkeep packages/shared/openapi/.gitkeep apps/api/app/__init__.py
```

- [ ] **Step 2: Create FastAPI package config**

Write `apps/api/pyproject.toml`:

```toml
[project]
name = "stock-review-api"
version = "0.1.0"
description = "A-share daily review backend"
requires-python = ">=3.12"
dependencies = [
  "akshare>=1.16.0",
  "fastapi>=0.115.0",
  "httpx>=0.27.0",
  "jinja2>=3.1.4",
  "openai>=1.60.0",
  "playwright>=1.49.0",
  "pydantic>=2.10.0",
  "pydantic-settings>=2.7.0",
  "python-dotenv>=1.0.1",
  "sqlalchemy>=2.0.36",
  "uvicorn[standard]>=0.34.0"
]

[dependency-groups]
dev = [
  "pytest>=8.3.0",
  "pytest-asyncio>=0.25.0",
  "ruff>=0.9.0"
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 3: Create minimal API app**

Write `apps/api/app/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="A 股每日复盘 API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

Write `apps/api/tests/conftest.py`:

```python
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
```

- [ ] **Step 4: Install backend dependencies**

Run:

```bash
cd apps/api
uv sync
```

Expected: uv creates `.venv` and installs project dependencies.

- [ ] **Step 5: Verify health endpoint**

Run:

```bash
cd apps/api
uv run python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
response = client.get("/health")
assert response.status_code == 200
assert response.json() == {"status": "ok"}
print("health ok")
PY
```

Expected: prints `health ok`.

- [ ] **Step 6: Commit bootstrap**

```bash
git add .gitignore .env.example package.json pnpm-workspace.yaml docker-compose.yml reports/.gitkeep packages/shared/openapi/.gitkeep apps/api
git commit -m "chore: bootstrap stock review monorepo"
```

---

### Task 2: Define Report Schemas

**Files:**
- Create: `apps/api/app/schemas/__init__.py`
- Create: `apps/api/app/schemas/report.py`
- Test: `apps/api/tests/test_scoring.py`

- [ ] **Step 1: Write schema smoke test**

Write `apps/api/tests/test_scoring.py`:

```python
from app.schemas.report import (
    IndexSnapshot,
    MarketBreadth,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    SectorCandidate,
    StockCandidate,
)


def test_report_dto_serializes_core_fields() -> None:
    dto = ReportDTO(
        trade_date="2026-05-26",
        kind=ReportKind.CLOSE,
        title="2026.05.26 A股复盘",
        indices=[
            IndexSnapshot(name="上证指数", code="000001", pct_change=1.2, close=3100.5),
        ],
        breadth=MarketBreadth(up_count=3200, down_count=1800, limit_up_count=86, limit_down_count=8),
        turnover_cny=12345.67,
        market_state_tags=["放量", "分化"],
        sectors=[
            SectorCandidate(
                name="机器人",
                score=86.5,
                rank=1,
                pct_change=5.88,
                reason="涨停扩散",
                top_stocks=[
                    StockCandidate(
                        code="300001",
                        name="示例股份",
                        pct_change=20.0,
                        turnover_cny=12.3,
                        tags=["20cm"],
                    )
                ],
                news_summaries=["机器人产业链催化增强"],
            )
        ],
        narrative=ReportNarrative(
            conclusion="市场高热分化。",
            overview="成交放大。",
            sector_commentary=["机器人方向最强。"],
            watchlist=["观察核心容量股承接。"],
            tomorrow="关注分歧后的承接。",
            risks=["高位分歧加大。"],
        ),
    )

    dumped = dto.model_dump()

    assert dumped["kind"] == "close"
    assert dumped["sectors"][0]["top_stocks"][0]["name"] == "示例股份"
    assert dumped["narrative"]["risks"] == ["高位分歧加大。"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/test_scoring.py::test_report_dto_serializes_core_fields -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas'`.

- [ ] **Step 3: Implement report schemas**

Create `apps/api/app/schemas/__init__.py`:

```python
from app.schemas.report import (
    IndexSnapshot,
    LLMCallRecord,
    MarketBreadth,
    NewsItem,
    OverrideRecord,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    ReportStatus,
    SectorCandidate,
    StockCandidate,
)

__all__ = [
    "IndexSnapshot",
    "LLMCallRecord",
    "MarketBreadth",
    "NewsItem",
    "OverrideRecord",
    "ReportDTO",
    "ReportKind",
    "ReportNarrative",
    "ReportStatus",
    "SectorCandidate",
    "StockCandidate",
]
```

Create `apps/api/app/schemas/report.py`:

```python
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ReportKind(StrEnum):
    CLOSE = "close"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    VALIDATION_FAILED = "validation_failed"
    READY_FOR_REVIEW = "ready_for_review"
    EXPORTED = "exported"


class IndexSnapshot(BaseModel):
    name: str
    code: str
    close: float
    pct_change: float


class MarketBreadth(BaseModel):
    up_count: int
    down_count: int
    limit_up_count: int
    limit_down_count: int


class StockCandidate(BaseModel):
    code: str
    name: str
    pct_change: float
    turnover_cny: float | None = None
    tags: list[str] = Field(default_factory=list)


class NewsItem(BaseModel):
    title: str
    url: str
    source: str | None = None
    summary: str
    published_at: str | None = None
    matched_sector: str | None = None
    weight: float = 1.0


class SectorCandidate(BaseModel):
    name: str
    score: float
    rank: int
    pct_change: float
    reason: str
    top_stocks: list[StockCandidate] = Field(default_factory=list)
    news_summaries: list[str] = Field(default_factory=list)
    factor_scores: dict[str, float] = Field(default_factory=dict)
    confidence: str = "medium"


class ReportNarrative(BaseModel):
    conclusion: str
    overview: str
    sector_commentary: list[str]
    watchlist: list[str]
    tomorrow: str
    risks: list[str]


class OverrideRecord(BaseModel):
    target_type: str
    target_id: str
    action: str
    payload: dict[str, Any]


class LLMCallRecord(BaseModel):
    provider: str
    model: str
    prompt: str
    parameters: dict[str, Any]
    output: dict[str, Any]
    validation_errors: list[str] = Field(default_factory=list)


class ReportDTO(BaseModel):
    trade_date: str
    kind: ReportKind
    title: str
    indices: list[IndexSnapshot]
    breadth: MarketBreadth
    turnover_cny: float
    market_state_tags: list[str]
    sectors: list[SectorCandidate]
    narrative: ReportNarrative
    news: list[NewsItem] = Field(default_factory=list)
    overrides: list[OverrideRecord] = Field(default_factory=list)
    algorithm_versions: dict[str, str] = Field(
        default_factory=lambda: {
            "sector_score": "sector_score_v1",
            "news_weight": "news_weight_v1",
            "fact_validation": "fact_validation_v1",
        }
    )
```

- [ ] **Step 4: Run schema test**

Run:

```bash
cd apps/api
uv run pytest tests/test_scoring.py::test_report_dto_serializes_core_fields -v
```

Expected: PASS.

- [ ] **Step 5: Commit schemas**

```bash
git add apps/api/app/schemas apps/api/tests/test_scoring.py
git commit -m "feat: define report dto schemas"
```

---

### Task 3: Implement Asset Versioning

**Files:**
- Create: `apps/api/app/config.py`
- Create: `apps/api/app/services/__init__.py`
- Create: `apps/api/app/services/assets.py`
- Test: `apps/api/tests/test_assets.py`

- [ ] **Step 1: Write failing asset tests**

Write `apps/api/tests/test_assets.py`:

```python
import json
from pathlib import Path

from app.services.assets import AssetPaths, create_report_asset_dir, write_json


def test_create_report_asset_dir_uses_next_version(tmp_path: Path) -> None:
    first = create_report_asset_dir(tmp_path, "2026-05-26", "close")
    second = create_report_asset_dir(tmp_path, "2026-05-26", "close")

    assert first.version == "v001"
    assert second.version == "v002"
    assert first.root == tmp_path / "2026-05-26" / "close" / "v001"
    assert second.root == tmp_path / "2026-05-26" / "close" / "v002"
    assert first.root.exists()
    assert second.root.exists()


def test_write_json_outputs_pretty_utf8(tmp_path: Path) -> None:
    paths = AssetPaths(root=tmp_path, version="v001")
    write_json(paths.snapshot, {"name": "机器人", "score": 86.5})

    loaded = json.loads(paths.snapshot.read_text(encoding="utf-8"))

    assert loaded == {"name": "机器人", "score": 86.5}
    assert "机器人" in paths.snapshot.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_assets.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.assets'`.

- [ ] **Step 3: Implement asset service**

Write `apps/api/app/config.py`:

```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/stock_review.db"
    reports_root: Path = Path("../../reports")
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    anspire_api_key: str = ""
    news_provider: str = "anspire"
    news_top_k: int = 10
    news_lookback_hours: int = 36
    report_brand_name: str = ""
    report_brand_footer: str = ""
    report_disclaimer_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Write `apps/api/app/services/__init__.py`:

```python
from app.services.assets import AssetPaths, create_report_asset_dir, write_json

__all__ = ["AssetPaths", "create_report_asset_dir", "write_json"]
```

Write `apps/api/app/services/assets.py`:

```python
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AssetPaths:
    root: Path
    version: str

    @property
    def snapshot(self) -> Path:
        return self.root / "snapshot.json"

    @property
    def facts(self) -> Path:
        return self.root / "facts.json"

    @property
    def news_raw(self) -> Path:
        return self.root / "news_raw.json"

    @property
    def llm_calls(self) -> Path:
        return self.root / "llm_calls.json"

    @property
    def report_dto(self) -> Path:
        return self.root / "report.dto.json"

    @property
    def report_html(self) -> Path:
        return self.root / "report.html"

    @property
    def report_png(self) -> Path:
        return self.root / "report.png"

    @property
    def notes(self) -> Path:
        return self.root / "notes.json"


def create_report_asset_dir(reports_root: Path, trade_date: str, kind: str) -> AssetPaths:
    report_type_dir = reports_root / trade_date / kind
    report_type_dir.mkdir(parents=True, exist_ok=True)

    existing_versions = [
        int(path.name[1:])
        for path in report_type_dir.glob("v[0-9][0-9][0-9]")
        if path.is_dir() and path.name[1:].isdigit()
    ]
    next_number = max(existing_versions, default=0) + 1
    version = f"v{next_number:03d}"
    root = report_type_dir / version
    root.mkdir(parents=True, exist_ok=False)

    return AssetPaths(root=root, version=version)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run asset tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_assets.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit asset versioning**

```bash
git add apps/api/app/config.py apps/api/app/services apps/api/tests/test_assets.py
git commit -m "feat: add report asset versioning"
```

---

### Task 4: Add SQLite Persistence

**Files:**
- Create: `apps/api/app/db/__init__.py`
- Create: `apps/api/app/db/models.py`
- Create: `apps/api/app/db/session.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Write database smoke test**

Write `apps/api/tests/test_report_api.py`:

```python
from pathlib import Path

from app.db.models import Report, ReportKindModel, ReportStatusModel
from app.db.session import create_sqlite_engine, init_db, session_scope


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
    assert loaded.algorithm_versions["sector_score"] == "sector_score_v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_report_model_persists_asset_path -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 3: Implement database models and session helpers**

Write `apps/api/app/db/__init__.py`:

```python
from app.db.models import Base, Report, ReportKindModel, ReportStatusModel
from app.db.session import create_sqlite_engine, get_engine, init_db, session_scope

__all__ = [
    "Base",
    "Report",
    "ReportKindModel",
    "ReportStatusModel",
    "create_sqlite_engine",
    "get_engine",
    "init_db",
    "session_scope",
]
```

Write `apps/api/app/db/models.py`:

```python
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ReportKindModel(StrEnum):
    CLOSE = "close"


class ReportStatusModel(StrEnum):
    DRAFT = "draft"
    VALIDATION_FAILED = "validation_failed"
    READY_FOR_REVIEW = "ready_for_review"
    EXPORTED = "exported"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    kind: Mapped[ReportKindModel] = mapped_column(Enum(ReportKindModel), index=True)
    version: Mapped[str] = mapped_column(String(16))
    status: Mapped[ReportStatusModel] = mapped_column(Enum(ReportStatusModel), index=True)
    asset_dir: Mapped[str] = mapped_column(String(1024))
    algorithm_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
```

Write `apps/api/app/db/session.py`:

```python
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base


def create_sqlite_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.replace("sqlite:///", "", 1))
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, connect_args={"check_same_thread": False})


def get_engine() -> Engine:
    return create_sqlite_engine(get_settings().database_url)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 4: Initialize DB on app startup**

Modify `apps/api/app/main.py`:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.db.session import get_engine, init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    init_db(engine)
    app.state.engine = engine
    yield


app = FastAPI(title="A 股每日复盘 API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run database tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_report_model_persists_asset_path -v
```

Expected: PASS.

- [ ] **Step 6: Run health check again**

Run:

```bash
cd apps/api
uv run python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
print("health ok")
PY
```

Expected: prints `health ok`.

- [ ] **Step 7: Commit persistence**

```bash
git add apps/api/app/db apps/api/app/main.py apps/api/tests/test_report_api.py
git commit -m "feat: add sqlite report persistence"
```

---

### Task 5: Implement Scoring Rules

**Files:**
- Create: `apps/api/app/rules/__init__.py`
- Create: `apps/api/app/rules/scoring.py`
- Modify: `apps/api/tests/test_scoring.py`

- [ ] **Step 1: Add scoring tests**

Append to `apps/api/tests/test_scoring.py`:

```python
from app.rules.scoring import RawSectorInput, score_sectors


def test_score_sectors_ranks_by_short_term_strength() -> None:
    sectors = [
        RawSectorInput(
            name="低位防御",
            pct_change=2.0,
            limit_up_count=1,
            stock_up_ratio=0.55,
            turnover_change=0.1,
            news_weight=0.1,
        ),
        RawSectorInput(
            name="机器人",
            pct_change=5.88,
            limit_up_count=8,
            stock_up_ratio=0.82,
            turnover_change=0.35,
            news_weight=0.8,
        ),
    ]

    scored = score_sectors(sectors)

    assert [sector.name for sector in scored] == ["机器人", "低位防御"]
    assert scored[0].rank == 1
    assert scored[0].algorithm_version == "sector_score_v1"
    assert scored[0].factor_scores["limit_up"] > scored[1].factor_scores["limit_up"]


def test_score_sectors_caps_to_top_n() -> None:
    sectors = [
        RawSectorInput(
            name=f"板块{i}",
            pct_change=float(i),
            limit_up_count=i,
            stock_up_ratio=0.5,
            turnover_change=0.1,
            news_weight=0.0,
        )
        for i in range(8)
    ]

    scored = score_sectors(sectors, top_n=5)

    assert len(scored) == 5
    assert scored[0].name == "板块7"
```

- [ ] **Step 2: Run scoring tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_scoring.py::test_score_sectors_ranks_by_short_term_strength tests/test_scoring.py::test_score_sectors_caps_to_top_n -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.rules'`.

- [ ] **Step 3: Implement scoring rules**

Write `apps/api/app/rules/__init__.py`:

```python
from app.rules.scoring import RawSectorInput, ScoredSector, score_sectors

__all__ = ["RawSectorInput", "ScoredSector", "score_sectors"]
```

Write `apps/api/app/rules/scoring.py`:

```python
from dataclasses import dataclass, field


SECTOR_SCORE_VERSION = "sector_score_v1"


@dataclass(frozen=True)
class RawSectorInput:
    name: str
    pct_change: float
    limit_up_count: int
    stock_up_ratio: float
    turnover_change: float
    news_weight: float


@dataclass(frozen=True)
class ScoredSector:
    name: str
    score: float
    rank: int
    pct_change: float
    factor_scores: dict[str, float] = field(default_factory=dict)
    algorithm_version: str = SECTOR_SCORE_VERSION


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _normalize_pct_change(value: float) -> float:
    return _clamp((value + 2.0) / 12.0 * 100.0)


def _normalize_limit_up(value: int) -> float:
    return _clamp(value / 10.0 * 100.0)


def _normalize_ratio(value: float) -> float:
    return _clamp(value * 100.0)


def _normalize_turnover_change(value: float) -> float:
    return _clamp((value + 0.2) / 0.8 * 100.0)


def _normalize_news(value: float) -> float:
    return _clamp(value * 100.0)


def score_sectors(sectors: list[RawSectorInput], top_n: int = 5) -> list[ScoredSector]:
    scored: list[ScoredSector] = []
    for sector in sectors:
        factor_scores = {
            "pct_change": _normalize_pct_change(sector.pct_change),
            "limit_up": _normalize_limit_up(sector.limit_up_count),
            "breadth": _normalize_ratio(sector.stock_up_ratio),
            "turnover": _normalize_turnover_change(sector.turnover_change),
            "news": _normalize_news(sector.news_weight),
        }
        total = (
            factor_scores["limit_up"] * 0.35
            + factor_scores["pct_change"] * 0.20
            + factor_scores["turnover"] * 0.20
            + factor_scores["breadth"] * 0.15
            + factor_scores["news"] * 0.10
        )
        scored.append(
            ScoredSector(
                name=sector.name,
                score=round(total, 2),
                rank=0,
                pct_change=sector.pct_change,
                factor_scores={key: round(value, 2) for key, value in factor_scores.items()},
            )
        )

    ranked = sorted(scored, key=lambda item: item.score, reverse=True)[:top_n]
    return [
        ScoredSector(
            name=item.name,
            score=item.score,
            rank=index + 1,
            pct_change=item.pct_change,
            factor_scores=item.factor_scores,
            algorithm_version=item.algorithm_version,
        )
        for index, item in enumerate(ranked)
    ]
```

- [ ] **Step 4: Run scoring tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_scoring.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit scoring**

```bash
git add apps/api/app/rules apps/api/tests/test_scoring.py
git commit -m "feat: add sector scoring rules"
```

---

### Task 6: Implement Fact Validation

**Files:**
- Create: `apps/api/app/rules/validation.py`
- Modify: `apps/api/app/rules/__init__.py`
- Test: `apps/api/tests/test_validation.py`

- [ ] **Step 1: Write failing validation tests**

Write `apps/api/tests/test_validation.py`:

```python
from app.rules.validation import validate_narrative_facts
from app.schemas.report import (
    IndexSnapshot,
    MarketBreadth,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    SectorCandidate,
)


def make_report(narrative: ReportNarrative) -> ReportDTO:
    return ReportDTO(
        trade_date="2026-05-26",
        kind=ReportKind.CLOSE,
        title="2026.05.26 A股复盘",
        indices=[IndexSnapshot(name="上证指数", code="000001", close=3100.5, pct_change=1.2)],
        breadth=MarketBreadth(up_count=3200, down_count=1800, limit_up_count=86, limit_down_count=8),
        turnover_cny=12345.67,
        market_state_tags=["放量"],
        sectors=[
            SectorCandidate(
                name="机器人",
                score=86.5,
                rank=1,
                pct_change=5.88,
                reason="涨停扩散",
            )
        ],
        narrative=narrative,
    )


def test_validate_narrative_accepts_known_facts() -> None:
    report = make_report(
        ReportNarrative(
            conclusion="上证指数上涨1.2%，机器人板块涨幅5.88%。",
            overview="两市涨停86只，成交额12345.67亿元。",
            sector_commentary=["机器人是今日主线。"],
            watchlist=["关注机器人方向。"],
            tomorrow="观察机器人分歧承接。",
            risks=["涨停86只后高位分歧。"],
        )
    )

    result = validate_narrative_facts(report)

    assert result.is_valid
    assert result.errors == []


def test_validate_narrative_flags_unknown_sector_and_number() -> None:
    report = make_report(
        ReportNarrative(
            conclusion="新能源是今日主线，涨停99只。",
            overview="成交额88888亿元。",
            sector_commentary=[],
            watchlist=[],
            tomorrow="观察。",
            risks=[],
        )
    )

    result = validate_narrative_facts(report)

    assert not result.is_valid
    assert "unknown sector: 新能源" in result.errors
    assert "unknown number: 99" in result.errors
    assert "unknown number: 88888" in result.errors
```

- [ ] **Step 2: Run validation tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_validation.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.rules.validation'`.

- [ ] **Step 3: Implement validation**

Write `apps/api/app/rules/validation.py`:

```python
import re
from dataclasses import dataclass

from app.schemas.report import ReportDTO


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: list[str]


def _narrative_text(report: ReportDTO) -> str:
    narrative = report.narrative
    parts = [
        narrative.conclusion,
        narrative.overview,
        *narrative.sector_commentary,
        *narrative.watchlist,
        narrative.tomorrow,
        *narrative.risks,
    ]
    return "\n".join(parts)


def _allowed_numbers(report: ReportDTO) -> set[str]:
    values = {
        str(report.breadth.up_count),
        str(report.breadth.down_count),
        str(report.breadth.limit_up_count),
        str(report.breadth.limit_down_count),
        f"{report.turnover_cny:g}",
        f"{report.turnover_cny:.2f}",
    }
    for index in report.indices:
        values.add(f"{index.close:g}")
        values.add(f"{index.close:.2f}")
        values.add(f"{index.pct_change:g}")
        values.add(f"{index.pct_change:.2f}")
    for sector in report.sectors:
        values.add(f"{sector.pct_change:g}")
        values.add(f"{sector.pct_change:.2f}")
        values.add(f"{sector.score:g}")
        values.add(f"{sector.score:.2f}")
        values.add(str(sector.rank))
        for stock in sector.top_stocks:
            values.add(f"{stock.pct_change:g}")
            values.add(f"{stock.pct_change:.2f}")
            if stock.turnover_cny is not None:
                values.add(f"{stock.turnover_cny:g}")
                values.add(f"{stock.turnover_cny:.2f}")
    return values


def validate_narrative_facts(report: ReportDTO) -> ValidationResult:
    text = _narrative_text(report)
    errors: list[str] = []
    known_sector_names = {sector.name for sector in report.sectors}

    for sector_name in ["机器人", "PCB", "电力", "新能源", "半导体", "低空经济"]:
        if sector_name in text and sector_name not in known_sector_names:
            errors.append(f"unknown sector: {sector_name}")

    allowed_numbers = _allowed_numbers(report)
    numbers = re.findall(r"(?<![A-Za-z0-9])\\d+(?:\\.\\d+)?(?![A-Za-z0-9])", text)
    for number in numbers:
        normalized = number.rstrip("0").rstrip(".") if "." in number else number
        if number not in allowed_numbers and normalized not in allowed_numbers:
            errors.append(f"unknown number: {number}")

    return ValidationResult(is_valid=not errors, errors=errors)
```

Modify `apps/api/app/rules/__init__.py`:

```python
from app.rules.scoring import RawSectorInput, ScoredSector, score_sectors
from app.rules.validation import ValidationResult, validate_narrative_facts

__all__ = [
    "RawSectorInput",
    "ScoredSector",
    "ValidationResult",
    "score_sectors",
    "validate_narrative_facts",
]
```

- [ ] **Step 4: Run validation tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_validation.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit validation**

```bash
git add apps/api/app/rules apps/api/tests/test_validation.py
git commit -m "feat: validate generated report facts"
```

---

### Task 7: Add Provider Interfaces and Fakes

**Files:**
- Create: `apps/api/app/providers/__init__.py`
- Create: `apps/api/app/providers/market.py`
- Create: `apps/api/app/providers/news.py`
- Create: `apps/api/app/providers/llm.py`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add provider fake test**

Append to `apps/api/tests/test_report_api.py`:

```python
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.providers.llm import FakeLLMProvider


def test_fake_providers_return_deterministic_payloads() -> None:
    market = FakeMarketDataProvider()
    news = FakeNewsProvider()
    llm = FakeLLMProvider()

    market_snapshot = market.get_close_snapshot("2026-05-26")
    news_items = news.search_sector_news("机器人", "2026-05-26")
    narrative = llm.generate_narrative(market_snapshot.to_report_seed(news_items))

    assert market_snapshot.trade_date == "2026-05-26"
    assert market_snapshot.raw_sectors[0].name == "机器人"
    assert news_items[0].matched_sector == "机器人"
    assert narrative.conclusion
```

- [ ] **Step 2: Run provider test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_fake_providers_return_deterministic_payloads -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.providers'`.

- [ ] **Step 3: Implement providers**

Write `apps/api/app/providers/__init__.py`:

```python
from app.providers.llm import FakeLLMProvider, LLMProvider
from app.providers.market import FakeMarketDataProvider, MarketCloseSnapshot, MarketDataProvider
from app.providers.news import FakeNewsProvider, NewsProvider

__all__ = [
    "FakeLLMProvider",
    "FakeMarketDataProvider",
    "FakeNewsProvider",
    "LLMProvider",
    "MarketCloseSnapshot",
    "MarketDataProvider",
    "NewsProvider",
]
```

Write `apps/api/app/providers/market.py`:

```python
from dataclasses import dataclass
from typing import Protocol

from app.rules.scoring import RawSectorInput
from app.schemas.report import IndexSnapshot, MarketBreadth, NewsItem


@dataclass(frozen=True)
class MarketCloseSnapshot:
    trade_date: str
    indices: list[IndexSnapshot]
    breadth: MarketBreadth
    turnover_cny: float
    market_state_tags: list[str]
    raw_sectors: list[RawSectorInput]

    def to_report_seed(self, news: list[NewsItem]) -> dict[str, object]:
        return {
            "trade_date": self.trade_date,
            "indices": [index.model_dump() for index in self.indices],
            "breadth": self.breadth.model_dump(),
            "turnover_cny": self.turnover_cny,
            "market_state_tags": self.market_state_tags,
            "raw_sectors": [sector.__dict__ for sector in self.raw_sectors],
            "news": [item.model_dump() for item in news],
        }


class MarketDataProvider(Protocol):
    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        raise NotImplementedError


class FakeMarketDataProvider:
    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=[
                IndexSnapshot(name="上证指数", code="000001", close=3100.5, pct_change=1.2),
                IndexSnapshot(name="创业板指", code="399006", close=1950.2, pct_change=2.1),
            ],
            breadth=MarketBreadth(
                up_count=3200,
                down_count=1800,
                limit_up_count=86,
                limit_down_count=8,
            ),
            turnover_cny=12345.67,
            market_state_tags=["放量", "分化"],
            raw_sectors=[
                RawSectorInput(
                    name="机器人",
                    pct_change=5.88,
                    limit_up_count=8,
                    stock_up_ratio=0.82,
                    turnover_change=0.35,
                    news_weight=0.8,
                ),
                RawSectorInput(
                    name="PCB",
                    pct_change=3.6,
                    limit_up_count=4,
                    stock_up_ratio=0.7,
                    turnover_change=0.2,
                    news_weight=0.5,
                ),
            ],
        )
```

Write `apps/api/app/providers/news.py`:

```python
from typing import Protocol

from app.schemas.report import NewsItem


class NewsProvider(Protocol):
    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        raise NotImplementedError


class FakeNewsProvider:
    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        return [
            NewsItem(
                title=f"{sector_name}产业链催化增强",
                url=f"https://example.com/news/{trade_date}/{sector_name}",
                source="示例财经",
                summary=f"{sector_name}方向出现政策和产业消息共振。",
                published_at=f"{trade_date}T15:00:00+08:00",
                matched_sector=sector_name,
                weight=0.8,
            )
        ]
```

Write `apps/api/app/providers/llm.py`:

```python
from typing import Protocol

from app.schemas.report import ReportNarrative


class LLMProvider(Protocol):
    def generate_narrative(self, seed: dict[str, object]) -> ReportNarrative:
        raise NotImplementedError


class FakeLLMProvider:
    def generate_narrative(self, seed: dict[str, object]) -> ReportNarrative:
        return ReportNarrative(
            conclusion="上证指数上涨1.2%，市场放量分化，机器人是今日主线。",
            overview="两市涨停86只，成交额12345.67亿元。",
            sector_commentary=["机器人板块涨幅5.88%，短线强度居前。"],
            watchlist=["关注机器人核心股承接。"],
            tomorrow="明日观察机器人方向分歧后的承接。",
            risks=["涨停86只后高位分歧可能加大。"],
        )
```

- [ ] **Step 4: Run provider test**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_fake_providers_return_deterministic_payloads -v
```

Expected: PASS.

- [ ] **Step 5: Commit provider fakes**

```bash
git add apps/api/app/providers apps/api/tests/test_report_api.py
git commit -m "feat: add mockable provider interfaces"
```

---

### Task 8: Build Report Generator Service

**Files:**
- Create: `apps/api/app/services/report_generator.py`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add report generator test**

Append to `apps/api/tests/test_report_api.py`:

```python
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.providers.llm import FakeLLMProvider
from app.services.report_generator import ReportGenerator


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
```

- [ ] **Step 2: Run generator test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_report_generator_writes_snapshot_files -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.report_generator'`.

- [ ] **Step 3: Implement report generator**

Write `apps/api/app/services/report_generator.py`:

```python
from dataclasses import dataclass
from pathlib import Path

from app.providers.llm import LLMProvider
from app.providers.market import MarketDataProvider
from app.providers.news import NewsProvider
from app.rules.scoring import score_sectors
from app.rules.validation import ValidationResult, validate_narrative_facts
from app.schemas.report import ReportDTO, ReportKind, SectorCandidate
from app.services.assets import AssetPaths, create_report_asset_dir, write_json


@dataclass(frozen=True)
class GeneratedReport:
    report: ReportDTO
    validation: ValidationResult
    assets: AssetPaths


class ReportGenerator:
    def __init__(
        self,
        reports_root: Path,
        market_provider: MarketDataProvider,
        news_provider: NewsProvider,
        llm_provider: LLMProvider,
    ) -> None:
        self.reports_root = reports_root
        self.market_provider = market_provider
        self.news_provider = news_provider
        self.llm_provider = llm_provider

    def generate_close_report(self, trade_date: str) -> GeneratedReport:
        assets = create_report_asset_dir(self.reports_root, trade_date, ReportKind.CLOSE.value)
        market_snapshot = self.market_provider.get_close_snapshot(trade_date)
        scored_sectors = score_sectors(market_snapshot.raw_sectors, top_n=5)

        news_items = []
        for sector in scored_sectors:
            news_items.extend(self.news_provider.search_sector_news(sector.name, trade_date))

        seed = market_snapshot.to_report_seed(news_items)
        narrative = self.llm_provider.generate_narrative(seed)

        sector_candidates = [
            SectorCandidate(
                name=scored.name,
                score=scored.score,
                rank=scored.rank,
                pct_change=scored.pct_change,
                reason="综合评分靠前",
                top_stocks=[],
                news_summaries=[
                    item.summary for item in news_items if item.matched_sector == scored.name
                ],
                factor_scores=scored.factor_scores,
            )
            for scored in scored_sectors
        ]

        report = ReportDTO(
            trade_date=trade_date,
            kind=ReportKind.CLOSE,
            title=f"{trade_date} A股复盘",
            indices=market_snapshot.indices,
            breadth=market_snapshot.breadth,
            turnover_cny=market_snapshot.turnover_cny,
            market_state_tags=market_snapshot.market_state_tags,
            sectors=sector_candidates,
            narrative=narrative,
            news=news_items,
        )
        validation = validate_narrative_facts(report)

        write_json(assets.facts, market_snapshot.to_report_seed(news=[]))
        write_json(assets.news_raw, [item.model_dump() for item in news_items])
        write_json(
            assets.llm_calls,
            [
                {
                    "provider": "fake",
                    "model": "fake-llm",
                    "prompt": "seed-json",
                    "parameters": {},
                    "output": narrative.model_dump(),
                    "validation_errors": validation.errors,
                }
            ],
        )
        write_json(assets.report_dto, report.model_dump(mode="json"))
        write_json(
            assets.snapshot,
            {
                "report": report.model_dump(mode="json"),
                "validation": {"is_valid": validation.is_valid, "errors": validation.errors},
            },
        )
        write_json(assets.notes, {"overrides": []})

        return GeneratedReport(report=report, validation=validation, assets=assets)
```

- [ ] **Step 4: Run generator test**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_report_generator_writes_snapshot_files -v
```

Expected: PASS.

- [ ] **Step 5: Commit generator**

```bash
git add apps/api/app/services/report_generator.py apps/api/tests/test_report_api.py
git commit -m "feat: generate report snapshots"
```

---

### Task 9: Render HTML and Export PNG

**Files:**
- Create: `apps/api/app/renderers/__init__.py`
- Create: `apps/api/app/renderers/html_renderer.py`
- Create: `apps/api/app/renderers/png_exporter.py`
- Create: `apps/api/app/renderers/templates/mobile_report.html.j2`
- Modify: `apps/api/app/services/report_generator.py`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add renderer test**

Append to `apps/api/tests/test_report_api.py`:

```python
from app.renderers.html_renderer import render_mobile_report_html


def test_mobile_report_renderer_contains_core_sections(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )
    result = generator.generate_close_report("2026-05-26")

    html = render_mobile_report_html(result.report, brand_name="复盘测试", disclaimer_enabled=True)

    assert "2026-05-26 A股复盘" in html
    assert "先给结论" in html
    assert "盘面总览" in html
    assert "强势板块" in html
    assert "机器人" in html
    assert "非投资建议" in html
```

- [ ] **Step 2: Run renderer test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_mobile_report_renderer_contains_core_sections -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.renderers'`.

- [ ] **Step 3: Implement HTML renderer**

Write `apps/api/app/renderers/__init__.py`:

```python
from app.renderers.html_renderer import render_mobile_report_html
from app.renderers.png_exporter import export_png

__all__ = ["export_png", "render_mobile_report_html"]
```

Write `apps/api/app/renderers/html_renderer.py`:

```python
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.schemas.report import ReportDTO


TEMPLATE_DIR = Path(__file__).parent / "templates"


def render_mobile_report_html(
    report: ReportDTO,
    brand_name: str = "",
    brand_footer: str = "",
    disclaimer_enabled: bool = True,
) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
    )
    template = env.get_template("mobile_report.html.j2")
    return template.render(
        report=report,
        brand_name=brand_name,
        brand_footer=brand_footer,
        disclaimer_enabled=disclaimer_enabled,
    )
```

Write `apps/api/app/renderers/templates/mobile_report.html.j2`:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ report.title }}</title>
  <style>
    body { margin: 0; background: #eef2f7; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #0f172a; }
    .page { width: 720px; margin: 0 auto; background: #f8fafc; }
    .hero { background: #101d2d; color: #fff; padding: 44px 36px 36px; text-align: center; }
    .kicker { color: #94a3b8; font-size: 12px; letter-spacing: 4px; text-transform: uppercase; }
    h1 { margin: 14px 0 24px; font-size: 34px; }
    .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
    .metric strong { color: #ef4444; font-size: 24px; display: block; }
    .metric span { color: #94a3b8; font-size: 12px; }
    section { margin: 22px 22px 0; background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 22px; }
    h2 { margin: 0 0 14px; font-size: 22px; border-left: 5px solid #d97706; padding-left: 10px; }
    .sector { margin-top: 14px; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }
    .sector-header { background: #12233a; color: #fff; padding: 14px 16px; display: flex; justify-content: space-between; }
    .sector-body { padding: 16px; }
    .tag { display: inline-block; background: #fee2e2; color: #b91c1c; border-radius: 999px; padding: 4px 10px; font-size: 12px; margin-right: 6px; }
    ul { margin: 8px 0 0 20px; padding: 0; line-height: 1.8; }
    .footer { padding: 26px; text-align: center; color: #94a3b8; font-size: 12px; }
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <div class="kicker">A-SHARE MARKET REVIEW</div>
      <h1>{{ report.title }}</h1>
      <div class="metrics">
        <div class="metric"><strong>{{ "%.2f"|format(report.indices[0].pct_change) }}%</strong><span>{{ report.indices[0].name }}</span></div>
        <div class="metric"><strong>{{ report.breadth.limit_up_count }}只</strong><span>涨停家数</span></div>
        <div class="metric"><strong>{{ report.sectors|length }}</strong><span>强势板块</span></div>
        <div class="metric"><strong>{{ "%.2f"|format(report.turnover_cny) }}亿</strong><span>成交额</span></div>
      </div>
    </header>

    <section>
      <h2>一、先给结论</h2>
      <p>{{ report.narrative.conclusion }}</p>
      {% for tag in report.market_state_tags %}<span class="tag">{{ tag }}</span>{% endfor %}
    </section>

    <section>
      <h2>二、盘面总览</h2>
      <p>{{ report.narrative.overview }}</p>
      <ul>
        <li>上涨 {{ report.breadth.up_count }} 家，下跌 {{ report.breadth.down_count }} 家。</li>
        <li>涨停 {{ report.breadth.limit_up_count }} 家，跌停 {{ report.breadth.limit_down_count }} 家。</li>
      </ul>
    </section>

    <section>
      <h2>三、强势板块</h2>
      {% for sector in report.sectors %}
      <article class="sector">
        <div class="sector-header"><strong>{{ sector.rank }}. {{ sector.name }}</strong><span>{{ "%.2f"|format(sector.pct_change) }}%</span></div>
        <div class="sector-body">
          <p>{{ sector.reason }}，综合评分 {{ "%.2f"|format(sector.score) }}。</p>
          {% if sector.news_summaries %}
          <ul>{% for summary in sector.news_summaries %}<li>{{ summary }}</li>{% endfor %}</ul>
          {% endif %}
        </div>
      </article>
      {% endfor %}
    </section>

    <section>
      <h2>四、个股关注</h2>
      <ul>{% for item in report.narrative.watchlist %}<li>{{ item }}</li>{% endfor %}</ul>
    </section>

    <section>
      <h2>五、明日观察</h2>
      <p>{{ report.narrative.tomorrow }}</p>
      <ul>{% for risk in report.narrative.risks %}<li>{{ risk }}</li>{% endfor %}</ul>
    </section>

    <footer class="footer">
      {% if brand_name %}<div>{{ brand_name }}</div>{% endif %}
      {% if brand_footer %}<div>{{ brand_footer }}</div>{% endif %}
      {% if disclaimer_enabled %}<div>仅为市场复盘记录，非投资建议。</div>{% endif %}
    </footer>
  </main>
</body>
</html>
```

Write `apps/api/app/renderers/png_exporter.py`:

```python
from pathlib import Path

from playwright.sync_api import sync_playwright


def export_png(html_path: Path, output_path: Path, width: int = 720) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1200}, device_scale_factor=2)
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        page.screenshot(path=str(output_path), full_page=True)
        browser.close()
```

- [ ] **Step 4: Update generator to write HTML**

Modify `apps/api/app/services/report_generator.py` to import and use the renderer:

```python
from app.renderers.html_renderer import render_mobile_report_html
```

After `write_json(assets.notes, {"overrides": []})`, add:

```python
        assets.report_html.write_text(
            render_mobile_report_html(report),
            encoding="utf-8",
        )
```

- [ ] **Step 5: Run renderer test**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_mobile_report_renderer_contains_core_sections -v
```

Expected: PASS.

- [ ] **Step 6: Install Playwright browser and smoke test PNG export**

Run:

```bash
cd apps/api
uv run playwright install chromium
uv run python - <<'PY'
from pathlib import Path
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.providers.llm import FakeLLMProvider
from app.renderers.png_exporter import export_png
from app.services.report_generator import ReportGenerator

root = Path("/tmp/stock-review-export-test")
result = ReportGenerator(root, FakeMarketDataProvider(), FakeNewsProvider(), FakeLLMProvider()).generate_close_report("2026-05-26")
export_png(result.assets.report_html, result.assets.report_png)
assert result.assets.report_png.exists()
assert result.assets.report_png.stat().st_size > 0
print(result.assets.report_png)
PY
```

Expected: prints a PNG path and the file exists.

- [ ] **Step 7: Commit renderer**

```bash
git add apps/api/app/renderers apps/api/app/services/report_generator.py apps/api/tests/test_report_api.py
git commit -m "feat: render mobile report html and png"
```

---

### Task 10: Expose Backend Report API

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add API endpoint test**

Append to `apps/api/tests/test_report_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_create_close_report_api_returns_generated_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path))
    with TestClient(app) as api_client:
        response = api_client.post("/api/reports/close", json={"trade_date": "2026-05-26"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["report"]["trade_date"] == "2026-05-26"
    assert payload["report"]["sectors"][0]["name"] == "机器人"
    assert payload["validation"]["is_valid"] is True
    assert payload["assets"]["version"] == "v001"
```

- [ ] **Step 2: Run API test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_create_close_report_api_returns_generated_report -v
```

Expected: FAIL with `404 Not Found`.

- [ ] **Step 3: Implement report endpoint**

Modify `apps/api/app/main.py`:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import get_settings
from app.db.session import get_engine, init_db
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
```

- [ ] **Step 4: Run API test**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_create_close_report_api_returns_generated_report -v
```

Expected: PASS.

- [ ] **Step 5: Commit API endpoint**

```bash
git add apps/api/app/main.py apps/api/tests/test_report_api.py
git commit -m "feat: expose close report generation api"
```

---

### Task 11: Scaffold Next.js Frontend

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/next.config.ts`
- Create: `apps/web/postcss.config.mjs`
- Create: `apps/web/tailwind.config.ts`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/app/globals.css`
- Create: `apps/web/app/layout.tsx`
- Create: `apps/web/lib/types.ts`
- Create: `apps/web/lib/api.ts`
- Create: `apps/web/components/Stepper.tsx`
- Create: `apps/web/components/TaskProgress.tsx`
- Create: `apps/web/components/ReportPreview.tsx`
- Create: `apps/web/app/page.tsx`

- [ ] **Step 1: Create frontend package and config**

Write `apps/web/package.json`:

```json
{
  "name": "@stock-review/web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "lint": "next lint",
    "test": "tsc --noEmit"
  },
  "dependencies": {
    "next": "15.1.0",
    "react": "19.0.0",
    "react-dom": "19.0.0"
  },
  "devDependencies": {
    "@types/node": "22.10.0",
    "@types/react": "19.0.0",
    "@types/react-dom": "19.0.0",
    "autoprefixer": "10.4.20",
    "postcss": "8.4.49",
    "tailwindcss": "3.4.17",
    "typescript": "5.7.2"
  }
}
```

Write `apps/web/next.config.ts`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
```

Write `apps/web/postcss.config.mjs`:

```js
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

export default config;
```

Write `apps/web/tailwind.config.ts`:

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        panel: "#f8fafc",
      },
    },
  },
  plugins: [],
};

export default config;
```

Write `apps/web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "es2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }]
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 2: Create frontend types and API client**

Write `apps/web/lib/types.ts`:

```ts
export type ReportNarrative = {
  conclusion: string;
  overview: string;
  sector_commentary: string[];
  watchlist: string[];
  tomorrow: string;
  risks: string[];
};

export type SectorCandidate = {
  name: string;
  score: number;
  rank: number;
  pct_change: number;
  reason: string;
  news_summaries: string[];
};

export type ReportDTO = {
  trade_date: string;
  kind: "close";
  title: string;
  turnover_cny: number;
  market_state_tags: string[];
  sectors: SectorCandidate[];
  narrative: ReportNarrative;
  breadth: {
    up_count: number;
    down_count: number;
    limit_up_count: number;
    limit_down_count: number;
  };
};

export type CreateReportResponse = {
  report: ReportDTO;
  validation: {
    is_valid: boolean;
    errors: string[];
  };
  assets: {
    root: string;
    version: string;
    html: string;
    png: string;
  };
};
```

Write `apps/web/lib/api.ts`:

```ts
import type { CreateReportResponse } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function createCloseReport(tradeDate: string): Promise<CreateReportResponse> {
  const response = await fetch(`${API_BASE_URL}/api/reports/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trade_date: tradeDate }),
  });

  if (!response.ok) {
    throw new Error(`生成失败：${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<CreateReportResponse>;
}
```

- [ ] **Step 3: Create UI components**

Write `apps/web/app/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  background: #edf2f7;
  color: #0f172a;
}
```

Write `apps/web/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "A 股每日复盘",
  description: "本地 A 股复盘生成工作台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
```

Write `apps/web/components/Stepper.tsx`:

```tsx
const steps = ["生成报告", "系统校验", "人工修正", "预览长图", "导出归档"];

export function Stepper({ activeIndex }: { activeIndex: number }) {
  return (
    <div className="grid grid-cols-5 gap-2">
      {steps.map((step, index) => (
        <div
          key={step}
          className={`rounded-xl px-3 py-3 text-center text-sm font-semibold ${
            index <= activeIndex ? "bg-slate-900 text-white" : "bg-white text-slate-500"
          }`}
        >
          {index + 1}. {step}
        </div>
      ))}
    </div>
  );
}
```

Write `apps/web/components/TaskProgress.tsx`:

```tsx
const stages = ["采集行情", "计算评分", "搜索新闻", "生成文案", "事实校验", "渲染导出"];

export function TaskProgress({ running }: { running: boolean }) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold">生成进度</h2>
      <div className="mt-4 grid gap-2">
        {stages.map((stage, index) => (
          <div key={stage} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
            <span>{stage}</span>
            <span className="text-sm text-slate-500">{running && index === 0 ? "运行中" : "待执行"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

Write `apps/web/components/ReportPreview.tsx`:

```tsx
import type { CreateReportResponse } from "../lib/types";

export function ReportPreview({ result }: { result: CreateReportResponse }) {
  const { report, validation, assets } = result;
  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.3em] text-slate-400">A-SHARE MARKET REVIEW</p>
          <h2 className="mt-2 text-2xl font-black">{report.title}</h2>
        </div>
        <span className="rounded-full bg-emerald-100 px-3 py-1 text-sm font-semibold text-emerald-700">
          {assets.version}
        </span>
      </div>

      <div className="mt-5 grid grid-cols-4 gap-3">
        <Metric label="涨停" value={`${report.breadth.limit_up_count}只`} />
        <Metric label="跌停" value={`${report.breadth.limit_down_count}只`} />
        <Metric label="成交额" value={`${report.turnover_cny.toFixed(2)}亿`} />
        <Metric label="强势板块" value={`${report.sectors.length}`} />
      </div>

      <section className="mt-6">
        <h3 className="border-l-4 border-amber-600 pl-3 text-lg font-bold">先给结论</h3>
        <p className="mt-3 leading-7 text-slate-700">{report.narrative.conclusion}</p>
      </section>

      <section className="mt-6">
        <h3 className="border-l-4 border-amber-600 pl-3 text-lg font-bold">强势板块</h3>
        <div className="mt-3 grid gap-3">
          {report.sectors.map((sector) => (
            <div key={sector.name} className="rounded-xl border border-slate-200 p-4">
              <div className="flex justify-between font-bold">
                <span>{sector.rank}. {sector.name}</span>
                <span className="text-red-600">{sector.pct_change.toFixed(2)}%</span>
              </div>
              <p className="mt-2 text-sm text-slate-600">{sector.news_summaries[0] ?? sector.reason}</p>
            </div>
          ))}
        </div>
      </section>

      {!validation.is_valid && (
        <section className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-red-700">
          <h3 className="font-bold">事实校验失败</h3>
          <ul className="mt-2 list-disc pl-5">
            {validation.errors.map((error) => <li key={error}>{error}</li>)}
          </ul>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <div className="text-xl font-black text-red-600">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}
```

- [ ] **Step 4: Create page**

Write `apps/web/app/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ReportPreview } from "../components/ReportPreview";
import { Stepper } from "../components/Stepper";
import { TaskProgress } from "../components/TaskProgress";
import { createCloseReport } from "../lib/api";
import type { CreateReportResponse } from "../lib/types";

export default function HomePage() {
  const [tradeDate, setTradeDate] = useState("2026-05-26");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateReportResponse | null>(null);

  async function handleGenerate() {
    setRunning(true);
    setError(null);
    try {
      const response = await createCloseReport(tradeDate);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-8">
        <p className="text-sm font-semibold uppercase tracking-[0.35em] text-slate-500">Stock Review</p>
        <h1 className="mt-2 text-4xl font-black">A 股每日复盘工作台</h1>
        <p className="mt-3 text-slate-600">v0.1：手动生成收盘复盘，审核后导出长图。</p>
      </div>

      <Stepper activeIndex={result ? 3 : running ? 0 : 0} />

      <div className="mt-6 grid grid-cols-[360px_1fr] gap-6">
        <aside className="space-y-4">
          <div className="rounded-2xl bg-white p-5 shadow-sm">
            <label className="text-sm font-semibold text-slate-600" htmlFor="trade-date">交易日</label>
            <input
              id="trade-date"
              className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-2"
              value={tradeDate}
              onChange={(event) => setTradeDate(event.target.value)}
            />
            <button
              className="mt-4 w-full rounded-xl bg-slate-900 px-4 py-3 font-bold text-white disabled:opacity-50"
              disabled={running}
              onClick={handleGenerate}
            >
              {running ? "生成中..." : "生成收盘复盘"}
            </button>
            {error && <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          </div>
          <TaskProgress running={running} />
        </aside>

        <section>
          {result ? (
            <ReportPreview result={result} />
          ) : (
            <div className="flex min-h-[520px] items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white text-slate-500">
              选择交易日后生成报告预览
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
```

- [ ] **Step 5: Install frontend dependencies**

Run:

```bash
pnpm install
```

Expected: dependencies install successfully and `pnpm-lock.yaml` is created.

- [ ] **Step 6: Type-check frontend**

Run:

```bash
pnpm --filter @stock-review/web test
```

Expected: TypeScript passes with no errors.

- [ ] **Step 7: Commit frontend scaffold**

```bash
git add package.json pnpm-lock.yaml pnpm-workspace.yaml apps/web
git commit -m "feat: scaffold report review frontend"
```

---

### Task 12: Wire Local End-to-End Smoke

**Files:**
- Modify: `apps/api/app/main.py`
- Create: `apps/api/Dockerfile`
- Create: `README.md`

- [ ] **Step 1: Add CORS middleware**

Modify `apps/api/app/main.py` to include CORS:

```python
from fastapi.middleware.cors import CORSMiddleware
```

After creating `app`, add:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 2: Add API Dockerfile**

Write `apps/api/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /workspace/apps/api

RUN pip install uv

COPY pyproject.toml ./pyproject.toml
RUN uv sync --no-dev

COPY app ./app

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Add README**

Write `README.md`:

```markdown
# A 股每日复盘

本地 A 股收盘复盘生成工作台。v0.1 支持手动生成收盘报告、事实校验、网页预览和 HTML/PNG 资产留档。

## 开发启动

后端：

```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

前端：

```bash
pnpm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 pnpm dev:web
```

打开 `http://localhost:3000`。

## v0.1 范围

- 手动生成收盘复盘
- AkShare/Anspire/OpenAI provider adapter 预留
- 当前实现先使用 deterministic fake providers，便于开发和测试
- 规则评分、事实校验、HTML 报告、PNG 导出
- SQLite + `reports/YYYY-MM-DD/close/vNNN/` 资产目录

## 后续阶段

- v0.2：午盘、定时任务、自选股和同花顺导入
- v0.3：历史补档、Markdown、OCR、系统体检和任务日志增强
```

- [ ] **Step 4: Run backend full tests**

Run:

```bash
cd apps/api
uv run pytest -v
```

Expected: all backend tests pass.

- [ ] **Step 5: Run frontend type-check**

Run:

```bash
pnpm --filter @stock-review/web test
```

Expected: TypeScript passes.

- [ ] **Step 6: Manual smoke test**

Run backend:

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 8000
```

In another terminal, run frontend:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 pnpm dev:web
```

Open `http://localhost:3000`, click `生成收盘复盘`, and verify:

- Report preview appears.
- Validation status is valid.
- A new directory appears under `reports/2026-05-26/close/v001/`.
- `report.dto.json`, `snapshot.json`, and `report.html` exist.

- [ ] **Step 7: Commit smoke wiring**

```bash
git add apps/api/app/main.py apps/api/Dockerfile README.md docker-compose.yml
git commit -m "chore: document local stock review workflow"
```

---

## Self-Review

Spec coverage:

- v0.1 monorepo, FastAPI, Next.js, pnpm + uv: Tasks 1, 11, 12.
- SQLite + local report asset directories: Tasks 3, 4, 8.
- ReportDTO, shared report source, HTML rendering: Tasks 2, 9.
- Sector scoring and market state-ready structure: Task 5.
- News and LLM provider adapter boundaries: Tasks 7, 8.
- LLM fact validation and retry-ready validation output: Tasks 6, 8.
- Basic editing/review UI shell: Task 11.
- PNG export with Playwright: Task 9.
- Backend API and local smoke: Tasks 10, 12.

Known intentional deferrals:

- Live AkShare, Anspire, and OpenAI calls are provider adapter follow-ups after this scaffold proves the local v0.1 loop with deterministic providers.
- True background task queue, override persistence endpoints, and full task logs can be added after the synchronous `/api/reports/close` endpoint is stable.
- Scheduler,午盘、自选股、OCR、Markdown/PDF, auth, and system health page remain outside v0.1 implementation.

Placeholder scan:

- The plan contains no placeholder instructions or cross-task shorthand.
- Each code-changing step includes concrete file content or concrete patch instructions.

Type consistency:

- Backend uses `ReportDTO`, `ReportKind.CLOSE`, `ReportNarrative`, `SectorCandidate`, and `NewsItem` consistently.
- Frontend mirrors the backend JSON shape with `ReportDTO` and `CreateReportResponse`.
- Asset names match the approved spec: `snapshot.json`, `facts.json`, `news_raw.json`, `llm_calls.json`, `report.dto.json`, `report.html`, `report.png`, `notes.json`.
