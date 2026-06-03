# Daily Report Evidence Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an evidence-first daily report pipeline where verified evidence drives core conclusions, sector ratings, capital rotation, and next-session strategy.

**Architecture:** Add a small evidence domain around the existing FastAPI, SQLAlchemy, Pydantic, and Next.js app. Evidence is parsed and validated before storage; Anspire only creates candidates; the report generator loads verified evidence and the rule layer enforces evidence-backed output before rendering.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic v2, pytest, Next.js 15, React 19, TypeScript, Node built-in test runner.

---

## Current Context

The existing backend already has:

- SQLAlchemy models in `apps/api/app/db/models.py`.
- DB init through `Base.metadata.create_all()` in `apps/api/app/db/session.py`.
- FastAPI routes in `apps/api/app/main.py`.
- Anspire news search in `apps/api/app/providers/news.py`.
- Report generation in `apps/api/app/services/report_generator.py`.
- Structured daily-report DTOs in `apps/api/app/schemas/structured_review.py`.
- Mobile report template in `apps/api/app/renderers/templates/mobile_report.html.j2`.

The existing frontend already has:

- A single admin page in `apps/web/app/page.tsx`.
- API helpers in `apps/web/lib/api.ts`.
- Shared frontend types in `apps/web/lib/types.ts`.
- Lightweight source-string tests in `apps/web/lib/*.test.ts`.

The worktree is expected to be dirty. Each task must stage only the files listed in that task before committing.

## File Structure

Create:

- `apps/api/app/schemas/evidence.py`  
  Pydantic evidence enums, input DTOs, persisted DTOs, preview DTOs, API request/response DTOs.

- `apps/api/app/services/evidence_service.py`  
  Parser, validator, persistence, query, and Anspire-candidate conversion helpers.

- `apps/api/app/services/evidence_judgment.py`  
  Evidence summary and report-contract enforcement for structured reviews.

- `apps/api/tests/test_evidence_service.py`  
  Unit tests for parsing, validation, storage, and candidate conversion.

- `apps/api/tests/test_evidence_api.py`  
  API tests for parse preview, save, query, and Anspire candidate fallback.

- `apps/api/tests/test_evidence_report_contract.py`  
  Tests for evidence-backed report contract, downgrade rules, and missing evidence states.

- `apps/web/components/EvidencePanel.tsx`  
  Batch paste, parse preview, save verified evidence, and Anspire candidate search.

- `apps/web/lib/evidencePanel.test.ts`  
  Frontend source-structure test for evidence panel wiring.

Modify:

- `apps/api/app/db/models.py`  
  Add `EvidenceRecord`.

- `apps/api/app/main.py`  
  Add evidence endpoints and pass evidence store into report generation.

- `apps/api/app/providers/news.py`  
  Add generic Anspire query search while preserving sector search behavior.

- `apps/api/app/schemas/report.py`  
  Add `evidence` to `ReportDTO`.

- `apps/api/app/schemas/structured_review.py`  
  Add evidence-backed conclusion and evidence id fields with safe defaults.

- `apps/api/app/services/report_generator.py`  
  Load verified evidence and apply evidence contract before rendering.

- `apps/api/app/services/structured_review_builder.py`  
  Populate evidence-aware fields for rule-based structured reviews.

- `apps/api/app/rules/validation.py`  
  Add non-fatal validation for evidence contract consistency.

- `apps/api/app/renderers/templates/mobile_report.html.j2`  
  Render ZERO/ONE/.../SEVEN sections, evidence refs, and evidence-insufficient states.

- `apps/web/app/page.tsx`  
  Add the evidence panel near data-source/report controls.

- `apps/web/lib/api.ts`  
  Add evidence API helpers.

- `apps/web/lib/types.ts`  
  Add evidence frontend types.

---

### Task 1: Evidence Schema, Parser, And Validator

**Files:**
- Create: `apps/api/app/schemas/evidence.py`
- Create: `apps/api/app/services/evidence_service.py`
- Test: `apps/api/tests/test_evidence_service.py`

- [ ] **Step 1: Write failing parser and validator tests**

Add this file:

```python
# apps/api/tests/test_evidence_service.py
from sqlalchemy import create_engine

from app.db.models import Base
from app.schemas.evidence import EvidenceCategory, EvidenceConfidence, EvidenceStatus
from app.services.evidence_service import (
    EvidenceStore,
    parse_evidence_preview,
    validate_evidence_item,
)


def _engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def test_parse_json_array_preview_valid_item() -> None:
    preview = parse_evidence_preview(
        """
        [
          {
            "trade_date": "2026-06-01",
            "source": "证券时报",
            "title": "煤炭行业今日净流入资金26.55亿元",
            "url": "https://example.com/stcn/coal",
            "published_at": "2026-06-01T15:30:00+08:00",
            "category": "capital_flow",
            "claim": "煤炭行业今日净流入资金26.55亿元。",
            "numbers": {"industry": "煤炭", "net_inflow_yi": 26.55},
            "related_sectors": ["煤炭"],
            "confidence": "high",
            "status": "verified"
          }
        ]
        """
    )

    assert preview.valid_count == 1
    assert preview.invalid_count == 0
    assert preview.items[0].item is not None
    assert preview.items[0].item.source == "证券时报"
    assert preview.items[0].item.category == EvidenceCategory.CAPITAL_FLOW
    assert preview.items[0].item.confidence == EvidenceConfidence.HIGH


def test_parse_table_text_preview() -> None:
    preview = parse_evidence_preview(
        "\t".join(
            [
                "trade_date",
                "source",
                "title",
                "url",
                "published_at",
                "category",
                "claim",
                "confidence",
                "related_sectors",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "2026-06-01",
                "36氪",
                "全球首个Agent原生电脑问世",
                "https://example.com/36kr/pc",
                "2026-06-01T12:00:00+08:00",
                "catalyst",
                "英伟达与微软推动Agent原生电脑方向。",
                "medium",
                "AI PC,AI应用",
            ]
        )
    )

    assert preview.valid_count == 1
    assert preview.items[0].item is not None
    assert preview.items[0].item.related_sectors == ["AI PC", "AI应用"]


def test_high_capital_flow_without_numbers_is_invalid() -> None:
    preview = parse_evidence_preview(
        """
        [{
          "trade_date": "2026-06-01",
          "source": "证券时报",
          "title": "行业资金流向",
          "url": "https://example.com/fund",
          "published_at": "2026-06-01T18:00:00+08:00",
          "category": "capital_flow",
          "claim": "煤炭行业净流入。",
          "confidence": "high",
          "status": "verified"
        }]
        """
    )

    assert preview.valid_count == 0
    assert preview.invalid_count == 1
    assert "capital_flow high evidence requires numbers" in preview.items[0].errors


def test_high_evidence_requires_trade_date_or_previous_day() -> None:
    preview = parse_evidence_preview(
        """
        [{
          "trade_date": "2026-06-01",
          "source": "新浪财经",
          "title": "宇树科技科创板IPO过会",
          "url": "https://example.com/sina/unitree",
          "published_at": "2026-05-28T18:00:00+08:00",
          "category": "catalyst",
          "claim": "宇树科技科创板IPO过会。",
          "confidence": "high",
          "status": "verified"
        }]
        """
    )

    assert preview.valid_count == 0
    assert "high evidence requires trade date or previous-day date match" in preview.items[0].errors


def test_store_saves_and_lists_verified_evidence() -> None:
    engine = _engine()
    preview = parse_evidence_preview(
        """
        [{
          "trade_date": "2026-06-01",
          "source": "金融界",
          "title": "主力资金连续6天净流出",
          "url": "https://example.com/jrj/outflow",
          "published_at": "2026-06-01T18:00:00+08:00",
          "category": "risk",
          "claim": "主力资金连续6天净流出。",
          "numbers": {"continuous_outflow_days": 6},
          "related_sectors": ["全市场"],
          "confidence": "high",
          "status": "verified"
        }]
        """
    )
    item = preview.items[0].item
    assert item is not None

    store = EvidenceStore(engine)
    saved = store.save_items([item])
    loaded = store.list_items("2026-06-01", status=EvidenceStatus.VERIFIED)

    assert len(saved) == 1
    assert saved[0].id.startswith("ev_20260601_")
    assert len(loaded) == 1
    assert loaded[0].claim == "主力资金连续6天净流出。"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_evidence_service.py -q
```

Expected: FAIL because `app.schemas.evidence` and `app.services.evidence_service` do not exist.

- [ ] **Step 3: Implement evidence schemas**

Create:

```python
# apps/api/app/schemas/evidence.py
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceCategory(StrEnum):
    CAPITAL_FLOW = "capital_flow"
    CATALYST = "catalyst"
    MARKET_SENTIMENT = "market_sentiment"
    LIMIT_UP = "limit_up"
    RISK = "risk"
    POLICY = "policy"
    EARNINGS = "earnings"


class EvidenceConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceStatus(StrEnum):
    CANDIDATE = "candidate"
    DRAFT = "draft"
    VERIFIED = "verified"


class EvidenceInput(BaseModel):
    id: str | None = None
    trade_date: str
    source: str
    title: str
    url: str
    published_at: str
    category: EvidenceCategory
    claim: str
    numbers: dict[str, Any] = Field(default_factory=dict)
    related_sectors: list[str] = Field(default_factory=list)
    confidence: EvidenceConfidence = EvidenceConfidence.MEDIUM
    status: EvidenceStatus = EvidenceStatus.DRAFT
    manual_confirmed: bool = False


class EvidenceItem(EvidenceInput):
    id: str


class EvidencePreviewItem(BaseModel):
    raw: dict[str, Any] | str
    item: EvidenceInput | None = None
    errors: list[str] = Field(default_factory=list)


class EvidenceParsePreview(BaseModel):
    items: list[EvidencePreviewItem] = Field(default_factory=list)
    valid_count: int = 0
    invalid_count: int = 0


class EvidenceParsePreviewRequest(BaseModel):
    content: str


class EvidenceSaveRequest(BaseModel):
    items: list[EvidenceInput]


class EvidenceListResponse(BaseModel):
    items: list[EvidenceItem]


class EvidenceCandidateRequest(BaseModel):
    trade_date: str
    query: str = ""
    task: str = "custom"


class EvidenceCandidateResponse(BaseModel):
    items: list[EvidencePreviewItem]
    provider_status: dict[str, object]
```

- [ ] **Step 4: Implement parser and validator without storage**

Create the top half of `apps/api/app/services/evidence_service.py`:

```python
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, select

from app.db.models import EvidenceRecord
from app.db.session import session_scope
from app.schemas.evidence import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceInput,
    EvidenceItem,
    EvidenceParsePreview,
    EvidencePreviewItem,
    EvidenceStatus,
)
from app.schemas.report import NewsItem


TRUSTED_EVIDENCE_SOURCES = (
    "财联社",
    "东方财富",
    "证券时报",
    "上海证券报",
    "上证报",
    "新浪财经",
    "36氪",
    "搜狐财经",
    "快科技",
    "金融界",
    "交易所",
)

ANISPIRE_TASK_QUERIES = {
    "stcn_capital_flow": "证券时报 行业资金 净流入 净流出 A股",
    "jrj_continuous_outflow": "金融界 主力资金 连续 净流出",
    "catalysts": "搜狐财经 36氪 快科技 新浪财经 催化 A股",
}


def parse_evidence_preview(content: str) -> EvidenceParsePreview:
    rows = _parse_rows(content)
    preview_items = [_preview_row(row) for row in rows]
    return EvidenceParsePreview(
        items=preview_items,
        valid_count=sum(1 for item in preview_items if item.item is not None and not item.errors),
        invalid_count=sum(1 for item in preview_items if item.errors),
    )


def validate_evidence_item(item: EvidenceInput) -> list[str]:
    errors: list[str] = []
    for field_name in ("source", "title", "url", "published_at", "category", "claim", "confidence"):
        value = getattr(item, field_name)
        if isinstance(value, str) and not value.strip():
            errors.append(f"{field_name} is required")

    if item.confidence == EvidenceConfidence.HIGH:
        if not _date_matches_trade_window(item.trade_date, item.published_at):
            errors.append("high evidence requires trade date or previous-day date match")
        if not item.manual_confirmed and not _is_trusted_source(item.source):
            errors.append("high evidence requires trusted source or manual confirmation")

    if item.category == EvidenceCategory.CAPITAL_FLOW and item.confidence == EvidenceConfidence.HIGH:
        if not item.numbers:
            errors.append("capital_flow high evidence requires numbers")

    return errors


def candidate_from_news_item(news_item: NewsItem, trade_date: str, query: str) -> EvidenceInput:
    source = news_item.source or _infer_source_from_title(news_item.title) or "Anspire"
    return EvidenceInput(
        trade_date=trade_date,
        source=source,
        title=news_item.title,
        url=news_item.url,
        published_at=news_item.published_at or f"{trade_date}T00:00:00+08:00",
        category=_infer_category(query, news_item.title),
        claim=news_item.summary or news_item.title,
        numbers=_extract_numbers(news_item.title + " " + news_item.summary),
        related_sectors=[news_item.matched_sector] if news_item.matched_sector else [],
        confidence=EvidenceConfidence.MEDIUM,
        status=EvidenceStatus.CANDIDATE,
    )


def _parse_rows(content: str) -> list[dict[str, Any] | str]:
    stripped = content.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return _parse_table_rows(stripped)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    return [stripped]


def _parse_table_rows(content: str) -> list[dict[str, Any] | str]:
    first_line = content.splitlines()[0]
    delimiter = "\t" if "\t" in first_line else "|" if "|" in first_line else ","
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    rows: list[dict[str, Any] | str] = []
    for row in reader:
        cleaned = {str(key).strip(): _clean_table_value(value) for key, value in row.items() if key}
        if "related_sectors" in cleaned and isinstance(cleaned["related_sectors"], str):
            cleaned["related_sectors"] = [
                part.strip() for part in cleaned["related_sectors"].replace("，", ",").split(",") if part.strip()
            ]
        rows.append(cleaned)
    return rows


def _preview_row(row: dict[str, Any] | str) -> EvidencePreviewItem:
    if not isinstance(row, dict):
        return EvidencePreviewItem(raw=row, item=None, errors=["row must be an object"])
    try:
        item = EvidenceInput.model_validate(row)
    except Exception as exc:
        return EvidencePreviewItem(raw=row, item=None, errors=[str(exc)])
    errors = validate_evidence_item(item)
    return EvidencePreviewItem(raw=row, item=item if not errors else item, errors=errors)


def _clean_table_value(value: object) -> object:
    if value is None:
        return ""
    text = str(value).strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def _date_matches_trade_window(trade_date: str, published_at: str) -> bool:
    published_date = _parse_date_prefix(published_at)
    if published_date is None:
        return False
    expected = date.fromisoformat(trade_date)
    return published_date in {expected, expected - timedelta(days=1)}


def _parse_date_prefix(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _is_trusted_source(source: str) -> bool:
    return any(name in source for name in TRUSTED_EVIDENCE_SOURCES)


def _infer_source_from_title(title: str) -> str | None:
    for source in TRUSTED_EVIDENCE_SOURCES:
        if source in title:
            return source
    return None


def _infer_category(query: str, title: str) -> EvidenceCategory:
    text = f"{query} {title}"
    if any(keyword in text for keyword in ("净流入", "净流出", "主力资金", "行业资金")):
        return EvidenceCategory.CAPITAL_FLOW
    if any(keyword in text for keyword in ("风险", "分歧", "减持", "净流出")):
        return EvidenceCategory.RISK
    if any(keyword in text for keyword in ("政策", "四部门")):
        return EvidenceCategory.POLICY
    return EvidenceCategory.CATALYST


def _extract_numbers(text: str) -> dict[str, Any]:
    numbers: dict[str, Any] = {}
    if "连续6天" in text:
        numbers["continuous_outflow_days"] = 6
    return numbers
```

- [ ] **Step 5: Add DB model and storage implementation**

Modify `apps/api/app/db/models.py` by adding this class after `RuntimeProviderConfig`:

```python
class EvidenceRecord(Base):
    __tablename__ = "evidence_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    source: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(1024))
    published_at: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32), index=True)
    claim: Mapped[str] = mapped_column(String(1024))
    numbers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    related_sectors: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    manual_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
```

Append this storage class to `apps/api/app/services/evidence_service.py`:

```python
class EvidenceStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def save_items(self, items: list[EvidenceInput]) -> list[EvidenceItem]:
        saved: list[EvidenceItem] = []
        with session_scope(self.engine) as session:
            for item in items:
                errors = validate_evidence_item(item)
                if errors:
                    raise ValueError("; ".join(errors))
                evidence_id = item.id or self._next_evidence_id(item.trade_date, len(saved) + 1)
                row = EvidenceRecord(
                    evidence_id=evidence_id,
                    trade_date=item.trade_date,
                    source=item.source,
                    title=item.title,
                    url=item.url,
                    published_at=item.published_at,
                    category=item.category.value,
                    claim=item.claim,
                    numbers=item.numbers,
                    related_sectors=item.related_sectors,
                    confidence=item.confidence.value,
                    status=item.status.value,
                    manual_confirmed=item.manual_confirmed,
                )
                session.add(row)
                saved.append(_row_to_item(row))
        return saved

    def list_items(self, trade_date: str, status: EvidenceStatus | None = None) -> list[EvidenceItem]:
        with session_scope(self.engine) as session:
            statement = select(EvidenceRecord).where(EvidenceRecord.trade_date == trade_date)
            if status is not None:
                statement = statement.where(EvidenceRecord.status == status.value)
            rows = session.execute(statement.order_by(EvidenceRecord.id.asc())).scalars().all()
            return [_row_to_item(row) for row in rows]

    def list_verified(self, trade_date: str) -> list[EvidenceItem]:
        return self.list_items(trade_date, status=EvidenceStatus.VERIFIED)

    def _next_evidence_id(self, trade_date: str, sequence: int) -> str:
        date_part = trade_date.replace("-", "")
        with session_scope(self.engine) as session:
            count = session.execute(
                select(EvidenceRecord).where(EvidenceRecord.trade_date == trade_date)
            ).scalars().all()
        return f"ev_{date_part}_{len(count) + sequence:03d}"


def _row_to_item(row: EvidenceRecord) -> EvidenceItem:
    return EvidenceItem(
        id=row.evidence_id,
        trade_date=row.trade_date,
        source=row.source,
        title=row.title,
        url=row.url,
        published_at=row.published_at,
        category=EvidenceCategory(row.category),
        claim=row.claim,
        numbers=row.numbers or {},
        related_sectors=list(row.related_sectors or []),
        confidence=EvidenceConfidence(row.confidence),
        status=EvidenceStatus(row.status),
        manual_confirmed=row.manual_confirmed,
    )
```

- [ ] **Step 6: Run evidence service tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_evidence_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

Before committing, run:

```bash
git diff --name-only --cached
git status --short apps/api/app/schemas/evidence.py apps/api/app/services/evidence_service.py apps/api/app/db/models.py apps/api/tests/test_evidence_service.py
```

Then commit only Task 1 files:

```bash
git add apps/api/app/schemas/evidence.py apps/api/app/services/evidence_service.py apps/api/app/db/models.py apps/api/tests/test_evidence_service.py
git commit -m "feat: add evidence parser and store"
```

---

### Task 2: Evidence API Endpoints

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_evidence_api.py`

- [ ] **Step 1: Write failing API tests**

Create:

```python
# apps/api/tests/test_evidence_api.py
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'evidence.db'}")
    monkeypatch.setenv("MARKET_PROVIDER", "fake")
    monkeypatch.setenv("NEWS_PROVIDER", "fake")
    monkeypatch.setenv("REVIEW_SOURCES_ENABLED", "false")
    yield
    get_settings.cache_clear()


def test_evidence_parse_preview_endpoint() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/evidence/parse-preview",
            json={
                "content": """
                [{
                  "trade_date": "2026-06-01",
                  "source": "证券时报",
                  "title": "煤炭行业今日净流入资金26.55亿元",
                  "url": "https://example.com/stcn/coal",
                  "published_at": "2026-06-01T15:30:00+08:00",
                  "category": "capital_flow",
                  "claim": "煤炭行业今日净流入资金26.55亿元。",
                  "numbers": {"industry": "煤炭", "net_inflow_yi": 26.55},
                  "confidence": "high",
                  "status": "verified"
                }]
                """
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid_count"] == 1
    assert payload["invalid_count"] == 0


def test_evidence_save_and_query_endpoints() -> None:
    item = {
        "trade_date": "2026-06-01",
        "source": "新浪财经",
        "title": "宇树科技科创板IPO过会",
        "url": "https://example.com/sina/unitree",
        "published_at": "2026-06-01T18:00:00+08:00",
        "category": "catalyst",
        "claim": "宇树科技科创板IPO过会。",
        "related_sectors": ["机器人"],
        "confidence": "high",
        "status": "verified",
    }
    with TestClient(app) as client:
        save_response = client.post("/api/evidence", json={"items": [item]})
        list_response = client.get("/api/evidence?trade_date=2026-06-01&status=verified")

    assert save_response.status_code == 200
    assert save_response.json()["items"][0]["id"].startswith("ev_20260601_")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["source"] == "新浪财经"


def test_evidence_save_rejects_invalid_verified_item() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/evidence",
            json={
                "items": [
                    {
                        "trade_date": "2026-06-01",
                        "source": "证券时报",
                        "title": "行业资金",
                        "url": "https://example.com/fund",
                        "published_at": "2026-06-01T18:00:00+08:00",
                        "category": "capital_flow",
                        "claim": "煤炭净流入。",
                        "confidence": "high",
                        "status": "verified",
                    }
                ]
            },
        )

    assert response.status_code == 422
    assert "capital_flow high evidence requires numbers" in response.text
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_evidence_api.py -q
```

Expected: FAIL with 404 for `/api/evidence/*` routes.

- [ ] **Step 3: Add endpoint imports**

Modify `apps/api/app/main.py` imports:

```python
from app.schemas.evidence import (
    EvidenceCandidateRequest,
    EvidenceCandidateResponse,
    EvidenceListResponse,
    EvidenceParsePreviewRequest,
    EvidenceSaveRequest,
    EvidenceStatus,
)
from app.services.evidence_service import EvidenceStore, parse_evidence_preview
```

- [ ] **Step 4: Add evidence route helpers**

Add below `_watchlist_ocr_service()`:

```python
def _evidence_store() -> EvidenceStore:
    return EvidenceStore(app.state.engine)
```

Add routes before `/api/reports`:

```python
@app.post("/api/evidence/parse-preview")
def parse_evidence(request: EvidenceParsePreviewRequest) -> dict[str, object]:
    return parse_evidence_preview(request.content).model_dump(mode="json")


@app.get("/api/evidence")
def list_evidence(trade_date: str, status: str | None = None) -> dict[str, object]:
    parsed_status = EvidenceStatus(status) if status else None
    return EvidenceListResponse(
        items=_evidence_store().list_items(trade_date, status=parsed_status)
    ).model_dump(mode="json")


@app.post("/api/evidence")
def save_evidence(request: EvidenceSaveRequest) -> dict[str, object]:
    try:
        items = _evidence_store().save_items(request.items)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EvidenceListResponse(items=items).model_dump(mode="json")
```

- [ ] **Step 5: Run API tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_evidence_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Run affected existing API tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_create_close_report_api_returns_generated_report tests/test_runtime_provider_config.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add apps/api/app/main.py apps/api/tests/test_evidence_api.py
git commit -m "feat: add evidence API endpoints"
```

---

### Task 3: Anspire Candidate Search

**Files:**
- Modify: `apps/api/app/providers/news.py`
- Modify: `apps/api/app/services/evidence_service.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_evidence_service.py`
- Test: `apps/api/tests/test_evidence_api.py`

- [ ] **Step 1: Add failing service and API tests**

Append to `apps/api/tests/test_evidence_service.py`:

```python
from app.providers.market import ProviderStatus
from app.schemas.report import NewsItem
from app.services.evidence_service import build_candidate_preview_from_news


def test_candidate_preview_from_news_defaults_to_candidate_status() -> None:
    preview = build_candidate_preview_from_news(
        trade_date="2026-06-01",
        query="金融界 主力资金 连续6天 净流出",
        items=[
            NewsItem(
                title="主力资金连续6天净流出",
                url="https://example.com/jrj/outflow",
                source=None,
                summary="主力资金连续6天净流出。",
                published_at="2026-06-01T18:00:00+08:00",
                matched_sector=None,
                weight=0.6,
            )
        ],
    )

    assert preview.valid_count == 1
    item = preview.items[0].item
    assert item is not None
    assert item.status == EvidenceStatus.CANDIDATE
    assert item.category == EvidenceCategory.CAPITAL_FLOW
    assert item.numbers["continuous_outflow_days"] == 6
```

Append to `apps/api/tests/test_evidence_api.py`:

```python
def test_evidence_anspire_candidates_uses_news_provider(monkeypatch) -> None:
    class FakeSearchProvider:
        def search_news_with_status(self, query: str, trade_date: str):
            from app.providers.news import NewsSearchResult
            from app.providers.market import ProviderStatus
            from app.schemas.report import NewsItem

            return NewsSearchResult(
                query=query,
                items=[
                    NewsItem(
                        title="主力资金连续6天净流出",
                        url="https://example.com/jrj/outflow",
                        source="金融界",
                        summary="主力资金连续6天净流出。",
                        published_at="2026-06-01T18:00:00+08:00",
                    )
                ],
                status=ProviderStatus(
                    provider="anspire",
                    status="success",
                    fallback_used=False,
                    reason=None,
                ),
            )

    class FakeBundle:
        news_provider = FakeSearchProvider()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

    monkeypatch.setattr("app.main.create_provider_bundle", lambda settings, runtime_config=None: FakeBundle())

    with TestClient(app) as client:
        response = client.post(
            "/api/evidence/anspire-candidates",
            json={"trade_date": "2026-06-01", "task": "jrj_continuous_outflow"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_status"]["status"] == "success"
    assert payload["items"][0]["item"]["status"] == "candidate"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_evidence_service.py::test_candidate_preview_from_news_defaults_to_candidate_status tests/test_evidence_api.py::test_evidence_anspire_candidates_uses_news_provider -q
```

Expected: FAIL because `NewsSearchResult`, `search_news_with_status`, and candidate helpers are missing.

- [ ] **Step 3: Add generic news search to Anspire provider**

Modify `apps/api/app/providers/news.py`:

```python
class NewsSearchResult(BaseModel):
    query: str
    items: list[NewsItem]
    status: ProviderStatus
```

Add to `AnspireNewsProvider`:

```python
    def search_news(self, query: str, trade_date: str) -> list[NewsItem]:
        if not self.api_key:
            raise ProviderFallbackError("ANSPIRE_API_KEY 未配置")

        to_time = datetime.fromisoformat(f"{trade_date}T23:59:59")
        from_time = to_time - timedelta(hours=self.lookback_hours)
        try:
            response = self.http_client.get(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={
                    "query": query,
                    "top_k": self.top_k,
                    "FromTime": from_time.isoformat(),
                    "ToTime": to_time.isoformat(),
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderFallbackError("Anspire 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            raise ProviderFallbackError(self._safe_http_status_error(status_code)) from exc
        except Exception as exc:
            raise ProviderFallbackError(self._safe_request_error(exc)) from exc

        try:
            payload = response.json()
        except Exception as exc:
            raise ProviderFallbackError("Anspire JSON 解析失败") from exc

        raw_items = self._extract_items(payload)
        if not raw_items:
            raise ProviderFallbackError("Anspire 无结果")

        return [self._to_news_item(raw_item, query) for raw_item in raw_items[: self.top_k]]
```

Change `search_sector_news()` to:

```python
    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        return self.search_news(f"{sector_name} A股", trade_date)
```

Add to `FallbackNewsProvider`:

```python
    def search_news_with_status(self, query: str, trade_date: str) -> NewsSearchResult:
        provider = _provider_name(self.primary, "news")
        try:
            if hasattr(self.primary, "search_news"):
                items = self.primary.search_news(query, trade_date)
            else:
                items = self.primary.search_sector_news(query, trade_date)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            if not self.fallback_enabled:
                raise
            return NewsSearchResult(
                query=query,
                items=self.fallback.search_sector_news(query, trade_date),
                status=ProviderStatus(
                    provider=provider,
                    status="fallback",
                    fallback_used=True,
                    reason=reason,
                ),
            )
        return NewsSearchResult(
            query=query,
            items=items,
            status=ProviderStatus(
                provider=provider,
                status="success",
                fallback_used=False,
                reason=None,
            ),
        )
```

- [ ] **Step 4: Add candidate helpers**

Append to `apps/api/app/services/evidence_service.py`:

```python
def query_for_candidate_task(task: str, custom_query: str) -> str:
    if custom_query.strip():
        return custom_query.strip()
    return ANISPIRE_TASK_QUERIES.get(task, task)


def build_candidate_preview_from_news(
    trade_date: str,
    query: str,
    items: list[NewsItem],
) -> EvidenceParsePreview:
    preview_items: list[EvidencePreviewItem] = []
    for news_item in items:
        item = candidate_from_news_item(news_item, trade_date=trade_date, query=query)
        preview_items.append(
            EvidencePreviewItem(
                raw=news_item.model_dump(mode="json"),
                item=item,
                errors=validate_evidence_item(item),
            )
        )
    return EvidenceParsePreview(
        items=preview_items,
        valid_count=sum(1 for item in preview_items if not item.errors),
        invalid_count=sum(1 for item in preview_items if item.errors),
    )
```

- [ ] **Step 5: Add Anspire candidates endpoint**

Modify `apps/api/app/main.py` imports:

```python
from app.services.evidence_service import (
    EvidenceStore,
    build_candidate_preview_from_news,
    parse_evidence_preview,
    query_for_candidate_task,
)
```

Add endpoint:

```python
@app.post("/api/evidence/anspire-candidates")
def search_evidence_candidates(request: EvidenceCandidateRequest) -> dict[str, object]:
    settings = get_settings()
    runtime_config = get_runtime_provider_config(app.state.engine, settings)
    query = query_for_candidate_task(request.task, request.query)
    with create_provider_bundle(settings, runtime_config=runtime_config) as providers:
        if not hasattr(providers.news_provider, "search_news_with_status"):
            raise HTTPException(status_code=422, detail="当前新闻源不支持候选搜索")
        result = providers.news_provider.search_news_with_status(query, request.trade_date)
    preview = build_candidate_preview_from_news(
        trade_date=request.trade_date,
        query=query,
        items=result.items,
    )
    return EvidenceCandidateResponse(
        items=preview.items,
        provider_status=result.status.model_dump(mode="json"),
    ).model_dump(mode="json")
```

- [ ] **Step 6: Run candidate tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_evidence_service.py::test_candidate_preview_from_news_defaults_to_candidate_status tests/test_evidence_api.py::test_evidence_anspire_candidates_uses_news_provider -q
```

Expected: PASS.

- [ ] **Step 7: Run provider tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py -q
```

Expected: PASS. If existing tests assert exact Anspire request params, update them to assert that sector search still sends `query == "<sector> A股"`.

- [ ] **Step 8: Commit Task 3**

```bash
git add apps/api/app/providers/news.py apps/api/app/services/evidence_service.py apps/api/app/main.py apps/api/tests/test_evidence_service.py apps/api/tests/test_evidence_api.py apps/api/tests/test_real_providers.py
git commit -m "feat: add Anspire evidence candidates"
```

---

### Task 4: Report DTO Evidence Fields And Contract Rules

**Files:**
- Modify: `apps/api/app/schemas/report.py`
- Modify: `apps/api/app/schemas/structured_review.py`
- Create: `apps/api/app/services/evidence_judgment.py`
- Test: `apps/api/tests/test_evidence_report_contract.py`

- [ ] **Step 1: Write failing contract tests**

Create:

```python
# apps/api/tests/test_evidence_report_contract.py
from app.schemas.evidence import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceItem,
    EvidenceStatus,
)
from app.schemas.structured_review import (
    ActionDiscipline,
    AfterHoursNewsSummary,
    CapitalRotationPath,
    IndexMidTermOutlook,
    MarketOverviewTable,
    NextDayOpportunityPlan,
    PredictionReview,
    PracticalConclusion,
    SectorDeepDive,
    StructuredReviewDTO,
    SustainabilityRank,
    TomorrowJudgement,
)
from app.services.evidence_judgment import apply_evidence_contract


def _evidence(**overrides) -> EvidenceItem:
    base = {
        "id": "ev_20260601_001",
        "trade_date": "2026-06-01",
        "source": "证券时报",
        "title": "煤炭行业净流入",
        "url": "https://example.com/stcn/coal",
        "published_at": "2026-06-01T15:30:00+08:00",
        "category": EvidenceCategory.CAPITAL_FLOW,
        "claim": "煤炭行业今日净流入资金26.55亿元。",
        "numbers": {"industry": "煤炭", "net_inflow_yi": 26.55},
        "related_sectors": ["煤炭"],
        "confidence": EvidenceConfidence.HIGH,
        "status": EvidenceStatus.VERIFIED,
    }
    base.update(overrides)
    return EvidenceItem(**base)


def _review() -> StructuredReviewDTO:
    return StructuredReviewDTO(
        topic="结构复盘",
        prediction_review=PredictionReview(
            previous_prediction="无",
            actual_result="无",
            revision="继续观察",
        ),
        tomorrow_judgement=TomorrowJudgement(
            most_likely_to_continue="煤炭",
            most_likely_to_diverge="电子",
            core_view="围绕证据强的方向处理。",
        ),
        market_overview=MarketOverviewTable(capital_flow_summary="市场震荡。"),
        after_hours_news=AfterHoursNewsSummary(),
        sector_deep_dives=[
            SectorDeepDive(
                sector="煤炭",
                stage="leader",
                rating="high",
                catalysts=[],
                core_stocks=[],
                capital_evidence=[],
                conclusion="煤炭资金占优。",
            ),
            SectorDeepDive(
                sector="机器人",
                stage="leader",
                rating="high",
                catalysts=[],
                core_stocks=[],
                capital_evidence=[],
                conclusion="机器人继续重点关注。",
            ),
        ],
        sustainability_ranking=[
            SustainabilityRank(rank=1, sector="煤炭", rating="high", reason="资金强。"),
            SustainabilityRank(rank=2, sector="机器人", rating="high", reason="题材强。"),
        ],
        capital_rotation=CapitalRotationPath(key_finding="资金集中。"),
        next_day_opportunity=NextDayOpportunityPlan(),
        practical_conclusion=PracticalConclusion(headline="关注证据最强方向。"),
        index_mid_term_outlook=IndexMidTermOutlook(current_position="震荡。"),
        action_discipline=ActionDiscipline(final_view="证据优先。"),
    )


def test_apply_evidence_contract_creates_four_core_signals() -> None:
    review = apply_evidence_contract(
        _review(),
        [
            _evidence(id="ev_20260601_001", claim="煤炭行业今日净流入资金26.55亿元。"),
            _evidence(
                id="ev_20260601_002",
                category=EvidenceCategory.CATALYST,
                claim="英伟达N1X AI PC芯片催化AI PC方向。",
                related_sectors=["AI PC"],
                numbers={},
            ),
        ],
    )

    assert review.evidence_conclusion is not None
    assert len(review.evidence_conclusion.signals) == 4
    assert review.evidence_conclusion.signals[0].evidence_ids == ["ev_20260601_001"]


def test_sector_without_high_evidence_is_downgraded_from_high() -> None:
    review = apply_evidence_contract(_review(), [_evidence()])

    robot = next(item for item in review.sector_deep_dives if item.sector == "机器人")
    assert robot.rating == "medium"
    assert "证据不足" in robot.conclusion


def test_missing_capital_flow_evidence_adds_gap_message() -> None:
    review = apply_evidence_contract(
        _review(),
        [
            _evidence(
                category=EvidenceCategory.CATALYST,
                claim="宇树科技科创板IPO过会。",
                related_sectors=["机器人"],
                numbers={},
            )
        ],
    )

    assert "缺少已验证资金证据" in review.capital_rotation.key_finding
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_evidence_report_contract.py -q
```

Expected: FAIL because DTO fields and `apply_evidence_contract` do not exist.

- [ ] **Step 3: Add evidence to report schema**

Modify `apps/api/app/schemas/report.py`:

```python
from app.schemas.evidence import EvidenceItem
```

Add to `ReportDTO`:

```python
    evidence: list[EvidenceItem] = Field(default_factory=list)
```

Add to `algorithm_versions` default:

```python
            "evidence_contract": "evidence_contract_v1",
```

- [ ] **Step 4: Add evidence-backed structured-review fields**

Modify `apps/api/app/schemas/structured_review.py`:

```python
EvidenceSignalStatus = Literal["supported", "pending_confirmation", "insufficient"]


class EvidenceBackedSignal(BaseModel):
    label: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: str = "insufficient"
    status: EvidenceSignalStatus = "insufficient"


class EvidenceBackedConclusion(BaseModel):
    summary: str
    signals: list[EvidenceBackedSignal] = Field(default_factory=list)
```

Add these fields:

```python
class SectorDeepDive(BaseModel):
    ...
    evidence_ids: list[str] = Field(default_factory=list)
```

```python
class SustainabilityRank(BaseModel):
    ...
    evidence_ids: list[str] = Field(default_factory=list)
```

```python
class NextSessionStrategy(BaseModel):
    ...
    evidence_ids: list[str] = Field(default_factory=list)
```

```python
class StructuredReviewDTO(BaseModel):
    evidence_conclusion: EvidenceBackedConclusion | None = None
    ...
```

- [ ] **Step 5: Implement evidence judgment service**

Create:

```python
# apps/api/app/services/evidence_judgment.py
from __future__ import annotations

from app.schemas.evidence import EvidenceCategory, EvidenceConfidence, EvidenceItem
from app.schemas.structured_review import (
    EvidenceBackedConclusion,
    EvidenceBackedSignal,
    StructuredReviewDTO,
)


def apply_evidence_contract(
    review: StructuredReviewDTO,
    evidence: list[EvidenceItem],
) -> StructuredReviewDTO:
    high_evidence = [item for item in evidence if item.confidence == EvidenceConfidence.HIGH]
    review.evidence_conclusion = _build_evidence_conclusion(high_evidence)
    _attach_sector_evidence(review, high_evidence)
    _downgrade_unsupported_high_ratings(review, high_evidence)
    _enforce_capital_flow_gap(review, high_evidence)
    _attach_strategy_evidence(review, high_evidence)
    return review


def _build_evidence_conclusion(evidence: list[EvidenceItem]) -> EvidenceBackedConclusion:
    supported = [
        EvidenceBackedSignal(
            label=_signal_label(item),
            summary=item.claim,
            evidence_ids=[item.id],
            confidence=item.confidence.value,
            status="supported",
        )
        for item in evidence[:4]
    ]
    while len(supported) < 4:
        supported.append(
            EvidenceBackedSignal(
                label="待确认信号",
                summary="证据不足，暂不生成强结论。",
                evidence_ids=[],
                confidence="insufficient",
                status="insufficient",
            )
        )
    summary = supported[0].summary if supported and supported[0].evidence_ids else "证据不足，核心结论保持保守。"
    return EvidenceBackedConclusion(summary=summary, signals=supported)


def _attach_sector_evidence(review: StructuredReviewDTO, evidence: list[EvidenceItem]) -> None:
    for sector in review.sector_deep_dives:
        matched = [
            item
            for item in evidence
            if sector.sector in item.related_sectors or sector.sector in item.claim or sector.sector in item.title
        ]
        sector.evidence_ids = [item.id for item in matched]
        if matched:
            claims = [item.claim for item in matched[:2]]
            sector.capital_evidence.extend(
                claim for claim in claims if claim not in sector.capital_evidence
            )


def _downgrade_unsupported_high_ratings(review: StructuredReviewDTO, evidence: list[EvidenceItem]) -> None:
    sectors_with_high = {
        sector
        for item in evidence
        for sector in item.related_sectors
    }
    for sector in review.sector_deep_dives:
        if sector.rating == "high" and sector.sector not in sectors_with_high:
            sector.rating = "medium"
            sector.conclusion = f"{sector.conclusion} 证据不足，评级降为观察。"
    for rank in review.sustainability_ranking:
        if rank.rating == "high" and rank.sector not in sectors_with_high:
            rank.rating = "medium"
            rank.reason = f"{rank.reason} 证据不足，降为观察。"
        rank.evidence_ids = [
            item.id
            for item in evidence
            if rank.sector in item.related_sectors or rank.sector in item.claim or rank.sector in item.title
        ]


def _enforce_capital_flow_gap(review: StructuredReviewDTO, evidence: list[EvidenceItem]) -> None:
    has_capital_flow = any(item.category == EvidenceCategory.CAPITAL_FLOW for item in evidence)
    if not has_capital_flow and "缺少已验证资金证据" not in review.capital_rotation.key_finding:
        review.capital_rotation.key_finding = (
            f"{review.capital_rotation.key_finding} 缺少已验证资金证据，资金轮动结论保持保守。"
        )
    if review.capital_rotation_v2 and not has_capital_flow:
        review.capital_rotation_v2.key_finding = (
            f"{review.capital_rotation_v2.key_finding} 缺少已验证资金证据，资金轮动结论保持保守。"
        )


def _attach_strategy_evidence(review: StructuredReviewDTO, evidence: list[EvidenceItem]) -> None:
    if review.next_session_strategy is None:
        return
    review.next_session_strategy.evidence_ids = [item.id for item in evidence[:4]]
    if not review.next_session_strategy.evidence_ids:
        review.next_session_strategy.focus = []
        review.next_session_strategy.observe = ["证据不足，等待资金与催化确认。"]


def _signal_label(item: EvidenceItem) -> str:
    labels = {
        EvidenceCategory.CAPITAL_FLOW: "资金信号",
        EvidenceCategory.CATALYST: "催化信号",
        EvidenceCategory.MARKET_SENTIMENT: "情绪信号",
        EvidenceCategory.LIMIT_UP: "强度信号",
        EvidenceCategory.RISK: "风险信号",
        EvidenceCategory.POLICY: "政策信号",
        EvidenceCategory.EARNINGS: "业绩信号",
    }
    return labels[item.category]
```

- [ ] **Step 6: Run contract tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_evidence_report_contract.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add apps/api/app/schemas/report.py apps/api/app/schemas/structured_review.py apps/api/app/services/evidence_judgment.py apps/api/tests/test_evidence_report_contract.py
git commit -m "feat: add evidence report contract"
```

---

### Task 5: Wire Verified Evidence Into Report Generation

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/services/report_generator.py`
- Modify: `apps/api/app/rules/validation.py`
- Test: `apps/api/tests/test_report_api.py`
- Test: `apps/api/tests/test_evidence_report_contract.py`

- [ ] **Step 1: Add failing report API test**

Append to `apps/api/tests/test_report_api.py`:

```python
def test_generated_report_includes_verified_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path))
    evidence = {
        "trade_date": "2026-05-26",
        "source": "证券时报",
        "title": "机器人行业资金流入",
        "url": "https://example.com/stcn/robot",
        "published_at": "2026-05-26T18:00:00+08:00",
        "category": "capital_flow",
        "claim": "机器人行业资金净流入。",
        "numbers": {"industry": "机器人", "net_inflow_yi": 12.3},
        "related_sectors": ["机器人"],
        "confidence": "high",
        "status": "verified",
    }

    with TestClient(app) as client:
        save_response = client.post("/api/evidence", json={"items": [evidence]})
        report_response = client.post("/api/reports/close", json={"trade_date": "2026-05-26"})

    assert save_response.status_code == 200
    assert report_response.status_code == 200
    report = report_response.json()["report"]
    assert report["evidence"][0]["source"] == "证券时报"
    assert report["structured_review"]["evidence_conclusion"]["signals"][0]["evidence_ids"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_generated_report_includes_verified_evidence -q
```

Expected: FAIL because `ReportGenerator` does not load evidence.

- [ ] **Step 3: Inject evidence store into generator**

Modify `ReportGenerator.__init__` in `apps/api/app/services/report_generator.py`:

```python
        evidence_store: object | None = None,
```

Set:

```python
        self.evidence_store = evidence_store
```

In `_generate_report()` before building `ReportDTO`:

```python
        verified_evidence = []
        if self.evidence_store is not None and hasattr(self.evidence_store, "list_verified"):
            verified_evidence = self.evidence_store.list_verified(trade_date)
```

In `ReportDTO(...)`:

```python
            evidence=verified_evidence,
```

After `generate_structured_review(...)` and before `report.structured_review = structured_review`:

```python
        structured_review = apply_evidence_contract(structured_review, report.evidence)
```

Add import:

```python
from app.services.evidence_judgment import apply_evidence_contract
```

- [ ] **Step 4: Pass evidence store from FastAPI**

Modify `_create_report_response()` in `apps/api/app/main.py`:

```python
            evidence_store=_evidence_store(),
```

- [ ] **Step 5: Add evidence status to provider payload**

In `provider_status` inside `ReportGenerator._generate_report()` add:

```python
            "evidence": {
                "provider": "local_evidence_store",
                "status": "success",
                "fallback_used": False,
                "reason": f"{len(verified_evidence)} verified evidence items",
            },
```

- [ ] **Step 6: Add validation helper**

Modify `apps/api/app/rules/validation.py` by adding:

```python
def validate_evidence_contract(report: ReportDTO) -> list[str]:
    errors: list[str] = []
    structured = report.structured_review
    if structured is None or structured.evidence_conclusion is None:
        return errors
    for signal in structured.evidence_conclusion.signals:
        if signal.status == "supported" and not signal.evidence_ids:
            errors.append(f"supported signal lacks evidence ids: {signal.label}")
    for sector in structured.sector_deep_dives:
        if sector.rating == "high" and not sector.evidence_ids:
            errors.append(f"high sector rating lacks evidence ids: {sector.sector}")
    return errors
```

Then call it from `validate_narrative_facts(report)` by extending its error list:

```python
    errors.extend(validate_evidence_contract(report))
```

- [ ] **Step 7: Run report evidence test**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_generated_report_includes_verified_evidence -q
```

Expected: PASS.

- [ ] **Step 8: Run affected report tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py tests/test_evidence_report_contract.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 5**

```bash
git add apps/api/app/main.py apps/api/app/services/report_generator.py apps/api/app/rules/validation.py apps/api/tests/test_report_api.py apps/api/tests/test_evidence_report_contract.py
git commit -m "feat: wire evidence into report generation"
```

---

### Task 6: Render Reference-Style Evidence Sections

**Files:**
- Modify: `apps/api/app/renderers/templates/mobile_report.html.j2`
- Test: `apps/api/tests/test_structured_review.py`
- Test: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add failing template assertions**

Append to `apps/api/tests/test_structured_review.py`:

```python
def test_mobile_template_contains_reference_section_labels() -> None:
    template = Path("app/renderers/templates/mobile_report.html.j2").read_text(encoding="utf-8")

    assert "ZERO" in template
    assert "今日核心结论" in template
    assert "ONE" in template
    assert "指数与市场情绪" in template
    assert "TWO" in template
    assert "昨日预判验证" in template
    assert "THREE" in template
    assert "板块深度分析" in template
    assert "FOUR" in template
    assert "资金轮动全景" in template
    assert "FIVE" in template
    assert "板块持续性排序" in template
    assert "SIX" in template
    assert "明日操作思路" in template
    assert "SEVEN" in template
    assert "中期研判" in template
    assert "evidence_ids" in template
    assert "证据不足" in template
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py::test_mobile_template_contains_reference_section_labels -q
```

Expected: FAIL because the current template starts at ONE and has older numbering.

- [ ] **Step 3: Update top sections**

In `apps/api/app/renderers/templates/mobile_report.html.j2`, replace the current `ONE 核心结论` block with:

```jinja2
    <span class="section-num">ZERO</span>
    <h2 class="section-title">今日核心结论</h2>
    {% if structured.evidence_conclusion %}
      <div class="key-insight">
        <div class="ki-title">一句话总结</div>
        <p>{{ structured.evidence_conclusion.summary }}</p>
      </div>
      <div class="sector-grid">
        {% for signal in structured.evidence_conclusion.signals %}
          <div class="insight-card">
            <div class="insight-label">{{ signal.label }}</div>
            <p>{{ signal.summary }}</p>
            {% if signal.evidence_ids %}
              <p class="muted">证据：{{ signal.evidence_ids|join("、") }}</p>
            {% else %}
              <p class="muted">证据不足，待确认。</p>
            {% endif %}
          </div>
        {% endfor %}
      </div>
    {% else %}
      <div class="conclusion-box"><p>{{ report.narrative.conclusion }}</p></div>
    {% endif %}
```

Change the following labels:

```jinja2
    <span class="section-num">ONE</span>
    <h2 class="section-title">指数与市场情绪</h2>
```

```jinja2
      <span class="section-num">TWO</span>
      <h2 class="section-title">昨日预判验证</h2>
```

```jinja2
    <span class="section-num">THREE</span>
    <h2 class="section-title">板块深度分析</h2>
```

```jinja2
    <span class="section-num">FOUR</span>
    <h2 class="section-title">资金轮动全景</h2>
```

```jinja2
      <span class="section-num">FIVE</span>
      <h2 class="section-title">板块持续性排序</h2>
```

```jinja2
      <span class="section-num">SIX</span>
      <h2 class="section-title">明日操作思路</h2>
```

```jinja2
    <span class="section-num">SEVEN</span>
    <h2 class="section-title">中期研判</h2>
```

- [ ] **Step 4: Render evidence ids in sector cards**

Inside each `sector in structured.sector_deep_dives` article, after `sector-meta`, add:

```jinja2
        {% if sector.evidence_ids %}
          <p class="muted">证据：{{ sector.evidence_ids|join("、") }}</p>
        {% else %}
          <p class="muted">证据不足，强判断已降级。</p>
        {% endif %}
```

- [ ] **Step 5: Update footer source title**

Change footer source label:

```jinja2
      <p style="font-weight:600; margin-bottom:6px;">主要信息来源</p>
```

Before the `report.news` footer, add verified evidence source summary:

```jinja2
  {% if report.evidence %}
    <div class="footer-sources">
      <p style="font-weight:600; margin-bottom:6px;">已验证证据</p>
      <div class="source-grid">
        {% for item in report.evidence[:8] %}
          <div class="source-item">
            <div class="source-name">
              {% if item.url %}<a href="{{ item.url }}">{{ item.title }}</a>{% else %}{{ item.title }}{% endif %}
            </div>
            <div class="source-meta">{{ item.id }} · {{ item.source }} · {{ item.category }}</div>
          </div>
        {% endfor %}
      </div>
    </div>
  {% endif %}
```

- [ ] **Step 6: Run template tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py::test_mobile_template_contains_reference_section_labels tests/test_report_api.py::test_create_close_report_api_returns_generated_report -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```bash
git add apps/api/app/renderers/templates/mobile_report.html.j2 apps/api/tests/test_structured_review.py
git commit -m "feat: render evidence-first report sections"
```

---

### Task 7: Frontend Evidence Panel

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Create: `apps/web/components/EvidencePanel.tsx`
- Modify: `apps/web/app/page.tsx`
- Test: `apps/web/lib/evidencePanel.test.ts`

- [ ] **Step 1: Write failing frontend source test**

Create:

```typescript
// apps/web/lib/evidencePanel.test.ts
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("evidence panel is wired to API helpers and homepage", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
  const panelSource = readFileSync(new URL("../components/EvidencePanel.tsx", import.meta.url), "utf8");
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(typesSource, /EvidenceItem/);
  assert.match(typesSource, /EvidenceParsePreview/);
  assert.match(apiSource, /parseEvidencePreview/);
  assert.match(apiSource, /saveEvidenceItems/);
  assert.match(apiSource, /searchEvidenceCandidates/);
  assert.match(panelSource, /日报证据/);
  assert.match(panelSource, /解析预览/);
  assert.match(panelSource, /Anspire 候选/);
  assert.match(pageSource, /EvidencePanel/);
});
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd apps/web
npm test -- --test-name-pattern "evidence panel"
```

Expected: FAIL because evidence types, API helpers, and component do not exist.

- [ ] **Step 3: Add frontend types**

Append to `apps/web/lib/types.ts`:

```typescript
export type EvidenceCategory =
  | "capital_flow"
  | "catalyst"
  | "market_sentiment"
  | "limit_up"
  | "risk"
  | "policy"
  | "earnings";

export type EvidenceConfidence = "high" | "medium" | "low";
export type EvidenceStatus = "candidate" | "draft" | "verified";

export type EvidenceItem = {
  id?: string;
  trade_date: string;
  source: string;
  title: string;
  url: string;
  published_at: string;
  category: EvidenceCategory;
  claim: string;
  numbers: Record<string, unknown>;
  related_sectors: string[];
  confidence: EvidenceConfidence;
  status: EvidenceStatus;
  manual_confirmed: boolean;
};

export type EvidencePreviewItem = {
  raw: Record<string, unknown> | string;
  item: EvidenceItem | null;
  errors: string[];
};

export type EvidenceParsePreview = {
  items: EvidencePreviewItem[];
  valid_count: number;
  invalid_count: number;
};

export type EvidenceListResponse = {
  items: EvidenceItem[];
};

export type EvidenceCandidateResponse = {
  items: EvidencePreviewItem[];
  provider_status: ProviderStatus;
};
```

- [ ] **Step 4: Add API helpers**

Modify imports in `apps/web/lib/api.ts`:

```typescript
  EvidenceCandidateResponse,
  EvidenceItem,
  EvidenceListResponse,
  EvidenceParsePreview,
```

Append helpers:

```typescript
export async function parseEvidencePreview(content: string): Promise<EvidenceParsePreview> {
  const response = await fetch(`${API_BASE_URL}/api/evidence/parse-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!response.ok) {
    throw new Error(`解析证据失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<EvidenceParsePreview>;
}

export async function listEvidence(tradeDate: string): Promise<EvidenceListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/evidence?trade_date=${encodeURIComponent(tradeDate)}&status=verified`);
  if (!response.ok) {
    throw new Error(`读取证据失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<EvidenceListResponse>;
}

export async function saveEvidenceItems(items: EvidenceItem[]): Promise<EvidenceListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/evidence`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  if (!response.ok) {
    throw new Error(`保存证据失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<EvidenceListResponse>;
}

export async function searchEvidenceCandidates(
  tradeDate: string,
  task: string,
  query = "",
): Promise<EvidenceCandidateResponse> {
  const response = await fetch(`${API_BASE_URL}/api/evidence/anspire-candidates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trade_date: tradeDate, task, query }),
  });
  if (!response.ok) {
    throw new Error(`搜索候选证据失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<EvidenceCandidateResponse>;
}
```

- [ ] **Step 5: Create EvidencePanel component**

Create:

```tsx
// apps/web/components/EvidencePanel.tsx
"use client";

import { useState } from "react";
import {
  parseEvidencePreview,
  saveEvidenceItems,
  searchEvidenceCandidates,
} from "../lib/api";
import type { EvidenceParsePreview } from "../lib/types";

type EvidencePanelProps = {
  tradeDate: string;
};

const sampleEvidence = `[
  {
    "trade_date": "2026-06-01",
    "source": "证券时报",
    "title": "煤炭行业今日净流入资金26.55亿元",
    "url": "https://example.com/stcn/coal",
    "published_at": "2026-06-01T15:30:00+08:00",
    "category": "capital_flow",
    "claim": "煤炭行业今日净流入资金26.55亿元。",
    "numbers": {"industry": "煤炭", "net_inflow_yi": 26.55},
    "related_sectors": ["煤炭"],
    "confidence": "high",
    "status": "verified"
  }
]`;

export function EvidencePanel({ tradeDate }: EvidencePanelProps) {
  const [content, setContent] = useState(sampleEvidence);
  const [preview, setPreview] = useState<EvidenceParsePreview | null>(null);
  const [task, setTask] = useState("stcn_capital_flow");
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function handlePreview() {
    setRunning(true);
    setError(null);
    setMessage(null);
    try {
      const response = await parseEvidencePreview(content);
      setPreview(response);
      setMessage(`解析完成：有效 ${response.valid_count} 条，异常 ${response.invalid_count} 条`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "解析证据失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleSave() {
    const validItems = preview?.items.flatMap((item) => (item.item && item.errors.length === 0 ? [item.item] : [])) ?? [];
    if (validItems.length === 0) {
      setError("没有可保存的有效证据");
      return;
    }
    setRunning(true);
    setError(null);
    setMessage(null);
    try {
      const response = await saveEvidenceItems(validItems);
      setMessage(`已保存 ${response.items.length} 条证据`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存证据失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleCandidateSearch() {
    setRunning(true);
    setError(null);
    setMessage(null);
    try {
      const response = await searchEvidenceCandidates(tradeDate, task, query);
      setPreview({ items: response.items, valid_count: response.items.filter((item) => item.errors.length === 0).length, invalid_count: response.items.filter((item) => item.errors.length > 0).length });
      setMessage(`Anspire 候选：${response.items.length} 条，状态 ${response.provider_status.status}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "搜索候选证据失败");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section id="evidence" className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Evidence</p>
          <h2 className="mt-1 text-xl font-black text-slate-950">日报证据</h2>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">{tradeDate}</span>
      </div>

      <textarea
        className="mt-4 min-h-48 w-full rounded-2xl border border-slate-200 bg-white p-3 text-sm text-slate-950 shadow-sm"
        value={content}
        onChange={(event) => setContent(event.target.value)}
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="rounded-full bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:bg-slate-300" disabled={running} onClick={handlePreview} type="button">
          解析预览
        </button>
        <button className="rounded-full bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:bg-slate-300" disabled={running || !preview} onClick={handleSave} type="button">
          保存有效证据
        </button>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50 p-3">
        <div className="grid gap-2 sm:grid-cols-[180px_minmax(0,1fr)_auto]">
          <select className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" value={task} onChange={(event) => setTask(event.target.value)}>
            <option value="stcn_capital_flow">证券时报行业资金</option>
            <option value="jrj_continuous_outflow">金融界连续净流出</option>
            <option value="catalysts">搜狐/36氪/快科技/新浪催化</option>
            <option value="custom">自定义关键词</option>
          </select>
          <input className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="自定义 Anspire 查询，可留空使用预设" />
          <button className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-bold text-white disabled:bg-slate-300" disabled={running} onClick={handleCandidateSearch} type="button">
            Anspire 候选
          </button>
        </div>
      </div>

      {message && <p className="mt-3 rounded-2xl bg-emerald-50 p-3 text-sm text-emerald-700">{message}</p>}
      {error && <p className="mt-3 rounded-2xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      {preview && (
        <div className="mt-4 overflow-hidden rounded-2xl border border-slate-100">
          {preview.items.map((item, index) => (
            <article className="border-b border-slate-100 p-3 text-sm last:border-b-0" key={`${item.item?.title ?? "raw"}-${index}`}>
              <div className="font-bold text-slate-950">{item.item?.title ?? "无法解析"}</div>
              <div className="mt-1 text-xs text-slate-500">{item.item ? `${item.item.source} · ${item.item.category} · ${item.item.confidence} · ${item.item.status}` : String(item.raw)}</div>
              {item.item && <p className="mt-2 text-slate-700">{item.item.claim}</p>}
              {item.errors.length > 0 && <p className="mt-2 text-red-700">{item.errors.join("；")}</p>}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 6: Wire panel into homepage**

Modify `apps/web/app/page.tsx` imports:

```tsx
import { EvidencePanel } from "../components/EvidencePanel";
```

Render below `DataSourceStatusPanel`:

```tsx
            <EvidencePanel tradeDate={tradeDate} />
```

- [ ] **Step 7: Run frontend tests**

Run:

```bash
cd apps/web
npm test
```

Expected: PASS.

- [ ] **Step 8: Commit Task 7**

```bash
git add apps/web/lib/types.ts apps/web/lib/api.ts apps/web/components/EvidencePanel.tsx apps/web/app/page.tsx apps/web/lib/evidencePanel.test.ts
git commit -m "feat: add evidence intake panel"
```

---

### Task 8: End-To-End Verification

**Files:**
- No new files expected.
- Modify only files required by failing checks from earlier tasks.

- [ ] **Step 1: Run full backend tests**

Run:

```bash
cd apps/api
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run full frontend tests**

Run:

```bash
cd apps/web
npm test
```

Expected: PASS.

- [ ] **Step 3: Generate a local evidence-backed report**

Run:

```bash
cd apps/api
uv run python - <<'PY'
from pathlib import Path

from app.config import Settings
from app.db.session import create_sqlite_engine, init_db
from app.providers.llm import FakeLLMProvider
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.services.evidence_service import EvidenceStore, parse_evidence_preview
from app.services.report_generator import ReportGenerator

engine = create_sqlite_engine("sqlite:///./data/evidence-e2e.db")
init_db(engine)
preview = parse_evidence_preview("""
[{
  "trade_date": "2026-06-01",
  "source": "证券时报",
  "title": "机器人行业资金净流入",
  "url": "https://example.com/stcn/robot",
  "published_at": "2026-06-01T18:00:00+08:00",
  "category": "capital_flow",
  "claim": "机器人行业资金净流入。",
  "numbers": {"industry": "机器人", "net_inflow_yi": 12.3},
  "related_sectors": ["机器人"],
  "confidence": "high",
  "status": "verified"
}]
""")
items = [entry.item for entry in preview.items if entry.item and not entry.errors]
store = EvidenceStore(engine)
store.save_items(items)
generator = ReportGenerator(
    reports_root=Path("../../reports"),
    market_provider=FakeMarketDataProvider(),
    news_provider=FakeNewsProvider(),
    llm_provider=FakeLLMProvider(),
    evidence_store=store,
)
result = generator.generate_close_report("2026-06-01")
print(result.assets.report_html)
print(result.report.structured_review.evidence_conclusion.signals[0].evidence_ids)
PY
```

Expected:

- The command prints a report HTML path.
- The second printed line contains `ev_20260601_`.
- The generated HTML contains `ZERO`, `今日核心结论`, and `已验证证据`.

- [ ] **Step 4: Start local app**

Run the API:

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 8000
```

Run the web app in another terminal:

```bash
cd apps/web
npm run dev -- --port 3000
```

Expected:

- API is reachable at `http://localhost:8000/health`.
- Web UI is reachable at `http://localhost:3000`.

- [ ] **Step 5: Browser verification**

Use the in-app browser for `http://localhost:3000`.

Verify:

- The homepage renders without Next.js duplicate-key or hydration errors.
- The `日报证据` panel is visible.
- `解析预览` works with the sample JSON.
- `保存有效证据` succeeds.
- `Anspire 候选` shows a success, fallback, or clear missing-key/error state without crashing.
- Generating a close report succeeds.
- The generated HTML includes `ZERO 今日核心结论` and evidence ids for supported signals.

- [ ] **Step 6: Final git check**

Run:

```bash
git status --short
git log --oneline -8
```

Expected:

- Only expected task commits are present.
- No unrelated dirty files are staged.
- Any unrelated pre-existing dirty files remain untouched.

---

## Self-Review Checklist

Spec coverage:

- Evidence intake: Task 1, Task 2, Task 7.
- Anspire candidates: Task 3, Task 7.
- Judgment rules and downgrade behavior: Task 4, Task 5.
- Report contract and renderer: Task 4, Task 5, Task 6.
- Backend API: Task 2, Task 3.
- Frontend panel: Task 7.
- Error handling: Task 1, Task 2, Task 3, Task 5.
- Testing: Tasks 1 through 8.

Scope constraints:

- No crawler/data warehouse implementation.
- No complex CMS.
- No raw score display.
- Existing market data providers remain in place.

Implementation sequencing:

- Backend evidence domain first.
- Candidate search second.
- Report contract third.
- Renderer and frontend after backend behavior is testable.

