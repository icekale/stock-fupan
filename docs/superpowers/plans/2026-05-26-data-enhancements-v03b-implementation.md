# v0.3b Data Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TongHuaShun-compatible watchlist import, local watchlist persistence, TickFlow quote enrichment, and a watchlist observation section in the generated HTML report.

**Architecture:** Add a focused `app.watchlist` package for parsing/storage/service boundaries, a `tickflow` provider with fake/fallback behavior, and optional watchlist dependencies in `ReportGenerator`. Keep AkShare as the broad market source; TickFlow only enriches imported watchlist stocks.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic v2, httpx, pytest, ruff, Next.js/TypeScript, pnpm.

---

## File Structure

Create or modify these files:

```text
apps/api/app/config.py                         # TickFlow/watchlist settings
apps/api/app/db/models.py                      # watchlist import/item tables
apps/api/app/main.py                           # watchlist API endpoints and report generator wiring
apps/api/app/providers/factory.py              # add TickFlow provider bundle
apps/api/app/providers/tickflow.py             # TickFlow/fake/fallback provider
apps/api/app/schemas/report.py                 # WatchlistObservation models
apps/api/app/services/report_generator.py      # load/enrich watchlist and persist status
apps/api/app/services/watchlist_observation.py # build report observation from watchlist + quotes
apps/api/app/watchlist/__init__.py             # package exports
apps/api/app/watchlist/parser.py               # .blk/.csv/.txt/raw parser
apps/api/app/watchlist/storage.py              # SQLite + snapshot persistence
apps/api/app/watchlist/service.py              # import/latest service
apps/api/app/renderers/templates/mobile_report.html.j2 # 自选股观察 section
apps/api/tests/test_watchlist_parser.py        # parser tests
apps/api/tests/test_watchlist_api.py           # storage/API tests
apps/api/tests/test_tickflow_provider.py       # TickFlow provider tests
apps/api/tests/test_report_api.py              # report/status/html assertions
apps/web/lib/types.ts                          # watchlist and tickflow status types
apps/web/lib/api.ts                            # watchlist import API client
apps/web/components/ProviderStatusPanel.tsx    # show tickflow status
apps/web/components/ReportPreview.tsx          # render watchlist observation
apps/web/components/WatchlistImportPanel.tsx   # import UI
apps/web/app/page.tsx                          # mount import panel
.env.example                                   # TickFlow/watchlist settings
README.md                                      # v0.3b usage docs
```

---

### Task 1: Watchlist Parser

**Files:**
- Create: `apps/api/app/watchlist/__init__.py`
- Create: `apps/api/app/watchlist/parser.py`
- Create: `apps/api/tests/test_watchlist_parser.py`

- [ ] **Step 1: Write failing parser tests**

Create `apps/api/tests/test_watchlist_parser.py`:

```python
from app.watchlist.parser import parse_watchlist_text


def test_parse_watchlist_text_normalizes_common_a_share_codes() -> None:
    result = parse_watchlist_text(
        "600000\n000001\n300750\n688001\n430001\n",
        source_name="manual.txt",
    )

    assert [item.symbol for item in result.items] == [
        "600000.SH",
        "000001.SZ",
        "300750.SZ",
        "688001.SH",
        "430001.BJ",
    ]
    assert result.warnings == []


def test_parse_watchlist_text_accepts_suffixes_and_removes_duplicates() -> None:
    result = parse_watchlist_text(
        "SH600000, 600000.SH, sz000001, 000001.SZ, BJ430001",
        source_name="paste.txt",
    )

    assert [item.symbol for item in result.items] == ["600000.SH", "000001.SZ", "430001.BJ"]


def test_parse_watchlist_text_reads_csv_names() -> None:
    result = parse_watchlist_text(
        "代码,名称\n600000,浦发银行\n000001,平安银行\n",
        source_name="ths.csv",
    )

    assert [(item.symbol, item.name) for item in result.items] == [
        ("600000.SH", "浦发银行"),
        ("000001.SZ", "平安银行"),
    ]


def test_parse_watchlist_text_returns_warnings_for_invalid_tokens() -> None:
    result = parse_watchlist_text("600000\nabc123\n12345\n", source_name="manual.txt")

    assert [item.symbol for item in result.items] == ["600000.SH"]
    assert "abc123" in result.warnings[0]
    assert "12345" in result.warnings[1]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_watchlist_parser.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.watchlist'`.

- [ ] **Step 3: Implement parser models and normalization**

Create `apps/api/app/watchlist/__init__.py`:

```python
from app.watchlist.parser import WatchlistItem, WatchlistParseResult, parse_watchlist_text

__all__ = ["WatchlistItem", "WatchlistParseResult", "parse_watchlist_text"]
```

Create `apps/api/app/watchlist/parser.py`:

```python
import csv
import io
import re
from typing import Literal

from pydantic import BaseModel


Exchange = Literal["SH", "SZ", "BJ"]


class WatchlistItem(BaseModel):
    symbol: str
    code: str
    exchange: Exchange
    name: str | None = None
    source: str = "import"


class WatchlistParseResult(BaseModel):
    items: list[WatchlistItem]
    warnings: list[str] = []


_CODE_RE = re.compile(r"(?i)(?:\b(?P<prefix>SH|SZ|BJ)[.:-]?)?(?P<code>\d{6})(?:[.:-]?(?P<suffix>SH|SZ|BJ)\b)?")
_INVALID_TOKEN_RE = re.compile(r"(?i)\b(?=[a-z0-9]*\d)(?=[a-z0-9]*[a-z])[a-z0-9]{5,12}\b|\b\d{1,5}\b|\b\d{7,12}\b")


def parse_watchlist_text(content: str, source_name: str = "manual.txt") -> WatchlistParseResult:
    rows = _parse_csv_rows(content) if source_name.lower().endswith(".csv") else []
    if rows:
        return _parse_rows(rows)
    return _parse_free_text(content)


def _parse_rows(rows: list[dict[str, str]]) -> WatchlistParseResult:
    seen: set[str] = set()
    items: list[WatchlistItem] = []
    warnings: list[str] = []
    for row in rows:
        code_text = _first_value(row, "code", "代码", "symbol", "证券代码")
        name = _first_value(row, "name", "名称", "证券名称") or None
        item = _item_from_token(code_text, name=name)
        if item is None:
            if code_text:
                warnings.append(f"无法识别股票代码: {code_text}")
            continue
        if item.symbol not in seen:
            seen.add(item.symbol)
            items.append(item)
    return WatchlistParseResult(items=items, warnings=warnings)


def _parse_free_text(content: str) -> WatchlistParseResult:
    seen: set[str] = set()
    items: list[WatchlistItem] = []
    warnings: list[str] = []
    consumed_spans: list[tuple[int, int]] = []
    for match in _CODE_RE.finditer(content):
        item = _item_from_match(match)
        if item is None:
            continue
        consumed_spans.append(match.span())
        if item.symbol not in seen:
            seen.add(item.symbol)
            items.append(item)

    for match in _INVALID_TOKEN_RE.finditer(content):
        if any(start <= match.start() and match.end() <= end for start, end in consumed_spans):
            continue
        warnings.append(f"无法识别股票代码: {match.group(0)}")
    return WatchlistParseResult(items=items, warnings=warnings)


def _parse_csv_rows(content: str) -> list[dict[str, str]]:
    sample = content.encode("utf-8", errors="ignore").decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(sample))
    if not reader.fieldnames:
        return []
    return [{str(key).strip(): str(value or "").strip() for key, value in row.items()} for row in reader]


def _first_value(row: dict[str, str], *keys: str) -> str:
    normalized = {key.strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(key.lower())
        if value:
            return value.strip()
    return ""


def _item_from_token(token: str, name: str | None = None) -> WatchlistItem | None:
    match = _CODE_RE.search(token)
    if match is None:
        return None
    return _item_from_match(match, name=name)


def _item_from_match(match: re.Match[str], name: str | None = None) -> WatchlistItem | None:
    code = match.group("code")
    prefix = match.group("prefix")
    suffix = match.group("suffix")
    exchange = _infer_exchange(code, explicit=(suffix or prefix))
    if exchange is None:
        return None
    return WatchlistItem(
        symbol=f"{code}.{exchange}",
        code=code,
        exchange=exchange,
        name=name,
    )


def _infer_exchange(code: str, explicit: str | None = None) -> Exchange | None:
    if explicit:
        normalized = explicit.upper()
        if normalized in {"SH", "SZ", "BJ"}:
            return normalized  # type: ignore[return-value]
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "3")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    return None
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_watchlist_parser.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit parser**

```bash
git add apps/api/app/watchlist apps/api/tests/test_watchlist_parser.py
git commit -m "feat: parse local watchlist imports"
```

---

### Task 2: Watchlist Persistence and API

**Files:**
- Modify: `apps/api/app/config.py`
- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/app/watchlist/storage.py`
- Create: `apps/api/app/watchlist/service.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_watchlist_api.py`

- [ ] **Step 1: Write failing storage/API tests**

Create `apps/api/tests/test_watchlist_api.py`:

```python
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.models import WatchlistImport, WatchlistItemModel
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.main import app
from app.watchlist.service import WatchlistImportService


def test_watchlist_service_imports_text_to_db_and_snapshots(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistImportService(engine=engine, snapshot_root=tmp_path / "watchlists")

    result = service.import_text("600000\n000001\n", source_name="manual.txt")

    assert result.import_id == 1
    assert [item.symbol for item in result.items] == ["600000.SH", "000001.SZ"]
    assert result.item_count == 2
    with session_scope(engine) as session:
        imported = session.query(WatchlistImport).one()
        rows = session.query(WatchlistItemModel).order_by(WatchlistItemModel.display_order).all()
        assert imported.item_count == 2
        assert Path(imported.snapshot_path).exists()
        assert [row.symbol for row in rows] == ["600000.SH", "000001.SZ"]
    parsed = json.loads((tmp_path / "watchlists" / "imports" / "000001-parsed.json").read_text(encoding="utf-8"))
    assert parsed["items"][0]["symbol"] == "600000.SH"


def test_watchlist_latest_returns_empty_without_import(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistImportService(engine=engine, snapshot_root=tmp_path / "watchlists")

    latest = service.get_latest()

    assert latest.import_id is None
    assert latest.items == []


def test_watchlist_import_text_api_returns_items(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.post(
            "/api/watchlists/import-text",
            json={"content": "600000\n000001", "source_name": "manual.txt"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_count"] == 2
    assert [item["symbol"] for item in payload["items"]] == ["600000.SH", "000001.SZ"]
    get_settings.cache_clear()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_watchlist_api.py -v
```

Expected: FAIL because models/service/endpoints do not exist.

- [ ] **Step 3: Add settings**

Modify `apps/api/app/config.py` after provider settings:

```python
    tickflow_api_key: str = ""
    tickflow_base_url: str = "https://api.tickflow.org"
    tickflow_provider: str = "tickflow"
    watchlist_provider: str = "local"
    watchlist_snapshot_root: Path = Path("./data/watchlists")
```

- [ ] **Step 4: Add DB models**

Modify `apps/api/app/db/models.py` imports:

```python
from sqlalchemy import ForeignKey, JSON, DateTime, Enum, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
```

Append models:

```python
class WatchlistImport(Base):
    __tablename__ = "watchlist_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_name: Mapped[str] = mapped_column(String(255))
    snapshot_path: Mapped[str] = mapped_column(String(1024))
    parsed_snapshot_path: Mapped[str] = mapped_column(String(1024))
    item_count: Mapped[int] = mapped_column(Integer)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    items: Mapped[list["WatchlistItemModel"]] = relationship(
        back_populates="import_record",
        cascade="all, delete-orphan",
    )


class WatchlistItemModel(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("watchlist_imports.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    code: Mapped[str] = mapped_column(String(8), index=True)
    exchange: Mapped[str] = mapped_column(String(4))
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer)
    import_record: Mapped[WatchlistImport] = relationship(back_populates="items")
```

- [ ] **Step 5: Add storage/service**

Create `apps/api/app/watchlist/service.py`:

```python
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine, select

from app.db.models import WatchlistImport, WatchlistItemModel
from app.db.session import session_scope
from app.services.assets import write_json
from app.watchlist.parser import WatchlistItem, parse_watchlist_text


class WatchlistImportResult(BaseModel):
    import_id: int | None
    item_count: int
    items: list[WatchlistItem]
    warnings: list[str] = []


class WatchlistImportService:
    def __init__(self, engine: Engine, snapshot_root: Path) -> None:
        self.engine = engine
        self.snapshot_root = snapshot_root

    def import_text(self, content: str, source_name: str = "manual.txt") -> WatchlistImportResult:
        parsed = parse_watchlist_text(content, source_name=source_name)
        imports_dir = self.snapshot_root / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)
        next_id = self._next_import_id()
        safe_name = _safe_filename(source_name)
        raw_path = imports_dir / f"{next_id:06d}-{safe_name}"
        parsed_path = imports_dir / f"{next_id:06d}-parsed.json"
        raw_path.write_text(content, encoding="utf-8")
        write_json(parsed_path, parsed.model_dump(mode="json"))

        with session_scope(self.engine) as session:
            record = WatchlistImport(
                source_type="text",
                source_name=source_name,
                snapshot_path=str(raw_path),
                parsed_snapshot_path=str(parsed_path),
                item_count=len(parsed.items),
                warnings=parsed.warnings,
            )
            session.add(record)
            session.flush()
            for index, item in enumerate(parsed.items):
                session.add(
                    WatchlistItemModel(
                        import_id=record.id,
                        symbol=item.symbol,
                        code=item.code,
                        exchange=item.exchange,
                        name=item.name,
                        display_order=index,
                    )
                )
            import_id = record.id

        return WatchlistImportResult(
            import_id=import_id,
            item_count=len(parsed.items),
            items=parsed.items,
            warnings=parsed.warnings,
        )

    def get_latest(self) -> WatchlistImportResult:
        with session_scope(self.engine) as session:
            record = session.execute(
                select(WatchlistImport).order_by(WatchlistImport.id.desc()).limit(1)
            ).scalar_one_or_none()
            if record is None:
                return WatchlistImportResult(import_id=None, item_count=0, items=[], warnings=[])
            rows = session.execute(
                select(WatchlistItemModel)
                .where(WatchlistItemModel.import_id == record.id)
                .order_by(WatchlistItemModel.display_order)
            ).scalars().all()
            items = [
                WatchlistItem(
                    symbol=row.symbol,
                    code=row.code,
                    exchange=row.exchange,  # type: ignore[arg-type]
                    name=row.name,
                )
                for row in rows
            ]
            return WatchlistImportResult(
                import_id=record.id,
                item_count=len(items),
                items=items,
                warnings=record.warnings or [],
            )

    def _next_import_id(self) -> int:
        with session_scope(self.engine) as session:
            latest = session.execute(select(WatchlistImport.id).order_by(WatchlistImport.id.desc()).limit(1)).scalar_one_or_none()
            return int(latest or 0) + 1


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {".", "-", "_"} else "_" for ch in name)
    return cleaned or "watchlist.txt"
```

Create `apps/api/app/watchlist/storage.py`:

```python
from app.watchlist.service import WatchlistImportResult, WatchlistImportService

__all__ = ["WatchlistImportResult", "WatchlistImportService"]
```

- [ ] **Step 6: Add API endpoints**

Modify `apps/api/app/main.py` imports:

```python
from fastapi import FastAPI, UploadFile
from app.watchlist.service import WatchlistImportService, WatchlistImportResult
```

Add request model:

```python
class ImportWatchlistTextRequest(BaseModel):
    content: str
    source_name: str = "manual.txt"
```

Add helper and endpoints before report endpoint:

```python
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
```

- [ ] **Step 7: Run watchlist API tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_watchlist_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit persistence/API**

```bash
git add apps/api/app/config.py apps/api/app/db/models.py apps/api/app/main.py apps/api/app/watchlist/storage.py apps/api/app/watchlist/service.py apps/api/tests/test_watchlist_api.py
git commit -m "feat: persist and import watchlists"
```

---

### Task 3: TickFlow Provider and Factory Wiring

**Files:**
- Create: `apps/api/app/providers/tickflow.py`
- Modify: `apps/api/app/providers/factory.py`
- Modify: `apps/api/tests/test_tickflow_provider.py`
- Modify: `apps/api/tests/test_real_providers.py`

- [ ] **Step 1: Write failing TickFlow tests**

Create `apps/api/tests/test_tickflow_provider.py`:

```python
import httpx
import pytest

from app.providers.market import ProviderFallbackError
from app.providers.tickflow import FallbackTickFlowProvider, FakeTickFlowProvider, TickFlowProvider


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=httpx.Request("POST", "https://api.test"), response=httpx.Response(self.status_code))

    def json(self) -> object:
        return self.payload


class FakeClient:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.last_request: dict[str, object] = {}
        self.closed = False

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.last_request = {"url": url, **kwargs}
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response

    def close(self) -> None:
        self.closed = True


def test_tickflow_provider_maps_batch_quotes() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "data": [
                    {
                        "symbol": "600000.SH",
                        "name": "浦发银行",
                        "last_price": 10.5,
                        "pct_change": 2.3,
                        "turnover": 123000000,
                        "volume": 45600,
                        "time": "2026-05-26T15:00:00+08:00",
                    }
                ]
            }
        )
    )
    provider = TickFlowProvider(
        api_key="tk-test-local",
        base_url="https://api.tickflow.org",
        http_client=client,
    )

    quotes = provider.get_quotes(["600000.SH"])

    assert quotes[0].symbol == "600000.SH"
    assert quotes[0].name == "浦发银行"
    assert quotes[0].pct_change == 2.3
    assert client.last_request["url"] == "https://api.tickflow.org/v1/quotes"
    assert client.last_request["headers"] == {"x-api-key": "tk-test-local"}


def test_tickflow_provider_rejects_missing_key() -> None:
    provider = TickFlowProvider(api_key="", base_url="https://api.tickflow.org")

    with pytest.raises(ProviderFallbackError, match="TICKFLOW_API_KEY"):
        provider.get_quotes(["600000.SH"])


def test_tickflow_provider_sanitizes_request_errors() -> None:
    leaked_key = "tk_secret_leak"
    provider = TickFlowProvider(
        api_key=leaked_key,
        base_url="https://api.tickflow.org",
        http_client=FakeClient(error=RuntimeError(f"boom {leaked_key}")),
    )

    with pytest.raises(ProviderFallbackError) as exc_info:
        provider.get_quotes(["600000.SH"])

    message = str(exc_info.value)
    assert "TickFlow 请求失败" in message
    assert leaked_key not in message


def test_tickflow_fallback_returns_fake_quotes_and_status() -> None:
    provider = FallbackTickFlowProvider(
        primary=TickFlowProvider(api_key="", base_url="https://api.tickflow.org"),
        fallback=FakeTickFlowProvider(),
        fallback_enabled=True,
    )

    quotes, status = provider.get_quotes_with_status(["600000.SH"])

    assert quotes[0].symbol == "600000.SH"
    assert status.provider == "tickflow"
    assert status.status == "fallback"
    assert status.fallback_used is True
    assert status.reason == "TICKFLOW_API_KEY 未配置"
```

Append to `apps/api/tests/test_real_providers.py`:

```python
from app.providers.tickflow import FallbackTickFlowProvider


def test_provider_factory_includes_tickflow_provider() -> None:
    settings = Settings(
        tickflow_provider="tickflow",
        tickflow_api_key="tk-test-local",
        tickflow_base_url="https://api.tickflow.org",
    )

    bundle = create_provider_bundle(settings)

    assert isinstance(bundle.tickflow_provider, FallbackTickFlowProvider)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_tickflow_provider.py tests/test_real_providers.py::test_provider_factory_includes_tickflow_provider -v
```

Expected: FAIL because provider and bundle field do not exist.

- [ ] **Step 3: Implement TickFlow provider**

Create `apps/api/app/providers/tickflow.py`:

```python
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from app.providers.market import ProviderFallbackError, ProviderStatus


class WatchlistQuote(BaseModel):
    symbol: str
    name: str | None = None
    last_price: float | None = None
    pct_change: float | None = None
    turnover_cny: float | None = None
    volume: float | None = None
    quote_time: str | None = None


class TickFlowQuoteProvider(Protocol):
    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        raise NotImplementedError


class FakeTickFlowProvider:
    provider_name = "fake_tickflow"

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        fake_names = {"600000.SH": "浦发银行", "000001.SZ": "平安银行", "300750.SZ": "宁德时代"}
        return [
            WatchlistQuote(
                symbol=symbol,
                name=fake_names.get(symbol),
                last_price=10.0 + index,
                pct_change=2.5 - index,
                turnover_cny=100000000 + index * 1000000,
                volume=10000 + index,
                quote_time="2026-05-26T15:00:00+08:00",
            )
            for index, symbol in enumerate(symbols)
        ]


class TickFlowProvider:
    provider_name = "tickflow"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 12,
        http_client: object | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        if not symbols:
            return []
        if not self.api_key:
            raise ProviderFallbackError("TICKFLOW_API_KEY 未配置")
        try:
            response = self.http_client.post(
                f"{self.base_url}/v1/quotes",
                headers={"x-api-key": self.api_key},
                json={"symbols": symbols},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderFallbackError("TickFlow 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            raise ProviderFallbackError(_safe_status_error(status_code)) from exc
        except Exception as exc:
            raise ProviderFallbackError(f"TickFlow 请求失败: {exc.__class__.__name__}") from exc
        return [_quote_from_item(item) for item in _extract_items(payload)]


class FallbackTickFlowProvider:
    def __init__(
        self,
        primary: TickFlowQuoteProvider,
        fallback: TickFlowQuoteProvider,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        quotes, _status = self.get_quotes_with_status(symbols)
        return quotes

    def get_quotes_with_status(self, symbols: list[str]) -> tuple[list[WatchlistQuote], ProviderStatus]:
        try:
            quotes = self.primary.get_quotes(symbols)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            if not self.fallback_enabled:
                raise
            return self.fallback.get_quotes(symbols), ProviderStatus(
                provider="tickflow",
                status="fallback",
                fallback_used=True,
                reason=reason,
            )
        return quotes, ProviderStatus(
            provider="tickflow",
            status="success",
            fallback_used=False,
            reason=None,
        )


def _extract_items(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data") or payload.get("items") or payload.get("results")
    else:
        data = payload
    if not isinstance(data, list):
        raise ProviderFallbackError("TickFlow 响应结构异常")
    return [item for item in data if isinstance(item, dict)]


def _quote_from_item(item: dict[str, Any]) -> WatchlistQuote:
    symbol = str(item.get("symbol") or item.get("ticker") or item.get("code") or "")
    if not symbol:
        raise ProviderFallbackError("TickFlow 响应缺少 symbol")
    return WatchlistQuote(
        symbol=symbol,
        name=_optional_str(item.get("name")),
        last_price=_optional_float(item.get("last_price") or item.get("price") or item.get("last")),
        pct_change=_optional_float(item.get("pct_change") or item.get("change_percent") or item.get("percent")),
        turnover_cny=_optional_float(item.get("turnover_cny") or item.get("turnover")),
        volume=_optional_float(item.get("volume")),
        quote_time=_optional_str(item.get("quote_time") or item.get("time") or item.get("timestamp")),
    )


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None and str(value) else None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_status_error(status_code: object) -> str:
    return "TickFlow HTTP 请求失败" if status_code is None else f"TickFlow HTTP {status_code}"
```

- [ ] **Step 4: Wire provider factory**

Modify `apps/api/app/providers/factory.py` imports:

```python
from app.providers.tickflow import (
    FakeTickFlowProvider,
    FallbackTickFlowProvider,
    TickFlowProvider,
    TickFlowQuoteProvider,
)
```

Update bundle:

```python
@dataclass(frozen=True)
class ProviderBundle:
    market_provider: MarketDataProvider
    news_provider: NewsProvider
    llm_provider: LLMProvider
    tickflow_provider: TickFlowQuoteProvider
```

Update `create_provider_bundle`:

```python
        tickflow_provider=_create_tickflow_provider(settings),
```

Add helper:

```python
def _create_tickflow_provider(settings: Settings) -> TickFlowQuoteProvider:
    if settings.tickflow_provider == "fake":
        return FakeTickFlowProvider()
    if settings.tickflow_provider == "tickflow":
        return FallbackTickFlowProvider(
            primary=TickFlowProvider(
                api_key=settings.tickflow_api_key,
                base_url=settings.tickflow_base_url,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            fallback=FakeTickFlowProvider(),
            fallback_enabled=settings.provider_fallback_enabled,
        )
    raise ValueError(f"Unsupported TICKFLOW_PROVIDER: {settings.tickflow_provider}")
```

- [ ] **Step 5: Run TickFlow tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_tickflow_provider.py tests/test_real_providers.py::test_provider_factory_includes_tickflow_provider -v
```

Expected: PASS.

- [ ] **Step 6: Commit provider**

```bash
git add apps/api/app/providers/tickflow.py apps/api/app/providers/factory.py apps/api/tests/test_tickflow_provider.py apps/api/tests/test_real_providers.py
git commit -m "feat: add tickflow quote provider"
```

---

### Task 4: Watchlist Observation Schema and Builder

**Files:**
- Modify: `apps/api/app/schemas/report.py`
- Create: `apps/api/app/services/watchlist_observation.py`
- Create: `apps/api/tests/test_watchlist_observation.py`

- [ ] **Step 1: Write failing observation tests**

Create `apps/api/tests/test_watchlist_observation.py`:

```python
from app.providers.tickflow import WatchlistQuote
from app.services.watchlist_observation import build_watchlist_observation
from app.watchlist.parser import WatchlistItem


def test_build_watchlist_observation_sorts_strongest_and_weakest() -> None:
    items = [
        WatchlistItem(symbol="600000.SH", code="600000", exchange="SH", name="浦发银行"),
        WatchlistItem(symbol="000001.SZ", code="000001", exchange="SZ", name="平安银行"),
        WatchlistItem(symbol="300750.SZ", code="300750", exchange="SZ", name="宁德时代"),
    ]
    quotes = [
        WatchlistQuote(symbol="600000.SH", name="浦发银行", pct_change=1.2),
        WatchlistQuote(symbol="000001.SZ", name="平安银行", pct_change=-2.5),
        WatchlistQuote(symbol="300750.SZ", name="宁德时代", pct_change=4.8),
    ]

    observation = build_watchlist_observation(import_id=7, items=items, quotes=quotes, sectors=[])

    assert observation.import_id == 7
    assert observation.total_count == 3
    assert observation.quote_count == 3
    assert observation.strongest[0].symbol == "300750.SZ"
    assert observation.weakest[0].symbol == "000001.SZ"


def test_build_watchlist_observation_handles_empty_watchlist() -> None:
    observation = build_watchlist_observation(import_id=None, items=[], quotes=[], sectors=[])

    assert observation.total_count == 0
    assert observation.quote_count == 0
    assert observation.notes == ["未导入自选股"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_watchlist_observation.py -v
```

Expected: FAIL because schema/builder do not exist.

- [ ] **Step 3: Add ReportDTO models**

Modify `apps/api/app/schemas/report.py` before `ReportDTO`:

```python
class WatchlistMatch(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    pct_change: float | None = None
    reason: str


class WatchlistObservation(BaseModel):
    import_id: int | None = None
    total_count: int = 0
    quote_count: int = 0
    strongest: list[WatchlistMatch] = Field(default_factory=list)
    weakest: list[WatchlistMatch] = Field(default_factory=list)
    sector_matches: list[WatchlistMatch] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
```

Add field to `ReportDTO` after `structured_review`:

```python
    watchlist_observation: WatchlistObservation | None = None
```

- [ ] **Step 4: Implement observation builder**

Create `apps/api/app/services/watchlist_observation.py`:

```python
from app.providers.tickflow import WatchlistQuote
from app.schemas.report import SectorCandidate, WatchlistMatch, WatchlistObservation
from app.watchlist.parser import WatchlistItem


def build_watchlist_observation(
    import_id: int | None,
    items: list[WatchlistItem],
    quotes: list[WatchlistQuote],
    sectors: list[SectorCandidate],
) -> WatchlistObservation:
    if not items:
        return WatchlistObservation(import_id=import_id, total_count=0, quote_count=0, notes=["未导入自选股"])

    quote_by_symbol = {quote.symbol: quote for quote in quotes}
    matches = [_match_from_item(item, quote_by_symbol.get(item.symbol)) for item in items]
    quoted_matches = [match for match in matches if match.pct_change is not None]
    strongest = sorted(quoted_matches, key=lambda match: match.pct_change or 0, reverse=True)[:5]
    weakest = sorted(quoted_matches, key=lambda match: match.pct_change or 0)[:5]
    sector_matches = _sector_matches(matches, sectors)
    notes = [] if quotes else ["TickFlow 未返回自选股行情，已保留导入列表"]
    if not sector_matches:
        notes.append("暂未匹配到板块内自选股")
    return WatchlistObservation(
        import_id=import_id,
        total_count=len(items),
        quote_count=len(quotes),
        strongest=strongest,
        weakest=weakest,
        sector_matches=sector_matches,
        notes=notes,
    )


def _match_from_item(item: WatchlistItem, quote: WatchlistQuote | None) -> WatchlistMatch:
    name = quote.name if quote and quote.name else item.name
    pct_change = quote.pct_change if quote else None
    reason = "自选股涨跌幅居前" if pct_change is not None and pct_change >= 0 else "自选股风险观察"
    if pct_change is None:
        reason = "已导入自选股，等待行情确认"
    return WatchlistMatch(symbol=item.symbol, name=name, pct_change=pct_change, reason=reason)


def _sector_matches(matches: list[WatchlistMatch], sectors: list[SectorCandidate]) -> list[WatchlistMatch]:
    results: list[WatchlistMatch] = []
    for match in matches:
        for sector in sectors:
            if match.name and match.name in sector.name:
                results.append(match.model_copy(update={"sector": sector.name, "reason": f"名称命中{sector.name}方向"}))
                break
    return results[:10]
```

- [ ] **Step 5: Run observation tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_watchlist_observation.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit observation builder**

```bash
git add apps/api/app/schemas/report.py apps/api/app/services/watchlist_observation.py apps/api/tests/test_watchlist_observation.py
git commit -m "feat: build watchlist observations"
```

---

### Task 5: Report Generator and HTML Integration

**Files:**
- Modify: `apps/api/app/services/report_generator.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/renderers/templates/mobile_report.html.j2`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Write failing report integration tests**

Append to `apps/api/tests/test_report_api.py`:

```python
from app.watchlist.parser import WatchlistItem
from app.watchlist.service import WatchlistImportResult
from app.providers.tickflow import FakeTickFlowProvider


class StaticWatchlistService:
    def get_latest(self):
        return WatchlistImportResult(
            import_id=1,
            item_count=2,
            items=[
                WatchlistItem(symbol="600000.SH", code="600000", exchange="SH", name="浦发银行"),
                WatchlistItem(symbol="000001.SZ", code="000001", exchange="SZ", name="平安银行"),
            ],
            warnings=[],
        )


def test_report_generator_writes_watchlist_observation_and_tickflow_status(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        watchlist_service=StaticWatchlistService(),
        tickflow_provider=FakeTickFlowProvider(),
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
    )

    result = generator.generate_close_report("2026-05-26")
    html = render_mobile_report_html(result.report)

    assert "自选股观察" in html
    assert "600000.SH" in html
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_report_generator_writes_watchlist_observation_and_tickflow_status tests/test_report_api.py::test_mobile_report_renderer_contains_watchlist_section -v
```

Expected: FAIL because `ReportGenerator` does not accept watchlist dependencies.

- [ ] **Step 3: Update ReportGenerator**

Modify `apps/api/app/services/report_generator.py` imports:

```python
from app.providers.tickflow import TickFlowQuoteProvider
from app.services.watchlist_observation import build_watchlist_observation
from app.watchlist.service import WatchlistImportService
```

Update constructor:

```python
        watchlist_service: object | None = None,
        tickflow_provider: TickFlowQuoteProvider | None = None,
```

Set fields:

```python
        self.watchlist_service = watchlist_service
        self.tickflow_provider = tickflow_provider
```

Before validation, after structured review assignment:

```python
        tickflow_status = ProviderStatus(
            provider="tickflow",
            status="disabled",
            fallback_used=False,
            reason="未配置自选股服务",
        )
        if self.watchlist_service is not None:
            latest_watchlist = self.watchlist_service.get_latest()
            symbols = [item.symbol for item in latest_watchlist.items]
            quotes = []
            if self.tickflow_provider is not None and symbols:
                if hasattr(self.tickflow_provider, "get_quotes_with_status"):
                    quotes, tickflow_status = self.tickflow_provider.get_quotes_with_status(symbols)
                else:
                    quotes = self.tickflow_provider.get_quotes(symbols)
                    tickflow_status = ProviderStatus(
                        provider=getattr(self.tickflow_provider, "provider_name", "tickflow"),
                        status="success",
                        fallback_used=False,
                        reason=None,
                    )
            report.watchlist_observation = build_watchlist_observation(
                import_id=latest_watchlist.import_id,
                items=latest_watchlist.items,
                quotes=quotes,
                sectors=report.sectors,
            )
```

Add `tickflow` to `provider_status`:

```python
            "tickflow": tickflow_status.model_dump(mode="json"),
```

- [ ] **Step 4: Wire main generator dependencies**

Modify `apps/api/app/main.py` generator creation:

```python
            watchlist_service=_watchlist_service(),
            tickflow_provider=providers.tickflow_provider,
```

- [ ] **Step 5: Add HTML section**

Modify `apps/api/app/renderers/templates/mobile_report.html.j2` after the “盘面总览” section:

```jinja2
          <section>
            <div class="section-title"><span class="section-num">04</span><h2>自选股观察</h2></div>
            {% set watch = report.watchlist_observation %}
            {% if watch %}
              <p class="muted">导入 {{ watch.total_count }} 只，行情匹配 {{ watch.quote_count }} 只。</p>
              {% if watch.strongest %}
                <h3>强势自选</h3>
                <ul>{% for item in watch.strongest %}<li>{{ item.symbol }} {{ item.name or '' }} {{ "%+.2f"|format(item.pct_change or 0) }}% · {{ item.reason }}</li>{% endfor %}</ul>
              {% endif %}
              {% if watch.weakest %}
                <h3>风险观察</h3>
                <ul>{% for item in watch.weakest %}<li>{{ item.symbol }} {{ item.name or '' }} {{ "%+.2f"|format(item.pct_change or 0) }}% · {{ item.reason }}</li>{% endfor %}</ul>
              {% endif %}
              {% if watch.notes %}<p class="muted">{{ "；".join(watch.notes) }}</p>{% endif %}
            {% else %}
              <p class="muted">未导入自选股。</p>
            {% endif %}
          </section>
```

Renumber later structured sections: 板块详细分析 `05`, 板块持续性排序 `06`, 去弱留强 `07`.

- [ ] **Step 6: Run report integration tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_report_generator_writes_watchlist_observation_and_tickflow_status tests/test_report_api.py::test_mobile_report_renderer_contains_watchlist_section -v
```

Expected: PASS.

- [ ] **Step 7: Commit report integration**

```bash
git add apps/api/app/services/report_generator.py apps/api/app/main.py apps/api/app/renderers/templates/mobile_report.html.j2 apps/api/tests/test_report_api.py
git commit -m "feat: render watchlist observations in reports"
```

---

### Task 6: Frontend Watchlist Import and Preview

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Create: `apps/web/components/WatchlistImportPanel.tsx`
- Modify: `apps/web/components/ProviderStatusPanel.tsx`
- Modify: `apps/web/components/ReportPreview.tsx`
- Modify: `apps/web/app/page.tsx`

- [ ] **Step 1: Update frontend types**

Modify `apps/web/lib/types.ts` by adding:

```ts
export type WatchlistItem = {
  symbol: string;
  code: string;
  exchange: "SH" | "SZ" | "BJ";
  name: string | null;
  source: string;
};

export type WatchlistImportResult = {
  import_id: number | null;
  item_count: number;
  items: WatchlistItem[];
  warnings: string[];
};

export type WatchlistMatch = {
  symbol: string;
  name: string | null;
  sector: string | null;
  pct_change: number | null;
  reason: string;
};

export type WatchlistObservation = {
  import_id: number | null;
  total_count: number;
  quote_count: number;
  strongest: WatchlistMatch[];
  weakest: WatchlistMatch[];
  sector_matches: WatchlistMatch[];
  notes: string[];
};
```

Add to `ReportDTO`:

```ts
  watchlist_observation?: WatchlistObservation | null;
```

Add to `ProviderStatusSummary`:

```ts
  tickflow?: ProviderStatus;
```

- [ ] **Step 2: Add API functions**

Modify `apps/web/lib/api.ts` imports:

```ts
import type { CreateReportResponse, WatchlistImportResult } from "./types";
```

Add:

```ts
export async function importWatchlistText(content: string, sourceName = "manual.txt"): Promise<WatchlistImportResult> {
  const response = await fetch(`${API_BASE_URL}/api/watchlists/import-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, source_name: sourceName }),
  });
  if (!response.ok) {
    throw new Error(`导入失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistImportResult>;
}

export async function importWatchlistFile(file: File): Promise<WatchlistImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/watchlists/import-file`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`导入失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistImportResult>;
}
```

- [ ] **Step 3: Add WatchlistImportPanel component**

Create `apps/web/components/WatchlistImportPanel.tsx`:

```tsx
"use client";

import { useState } from "react";
import { importWatchlistFile, importWatchlistText } from "../lib/api";
import type { WatchlistImportResult } from "../lib/types";

export function WatchlistImportPanel({ onImported }: { onImported: (result: WatchlistImportResult) => void }) {
  const [content, setContent] = useState("600000\n000001\n300750");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<WatchlistImportResult | null>(null);

  async function handleTextImport() {
    setRunning(true);
    setError(null);
    try {
      const result = await importWatchlistText(content, "manual.txt");
      setLatest(result);
      onImported(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setRunning(true);
    setError(null);
    try {
      const result = await importWatchlistFile(file);
      setLatest(result);
      onImported(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setRunning(false);
      event.target.value = "";
    }
  }

  return (
    <section className="rounded-3xl border border-slate-200 bg-white/90 p-5 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-black text-slate-950">自选股导入</h2>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-500">同花顺 / CSV / 文本</span>
      </div>
      <textarea
        className="mt-3 min-h-28 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm"
        value={content}
        onChange={(event) => setContent(event.target.value)}
      />
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          className="rounded-2xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white disabled:bg-slate-300"
          disabled={running || content.trim().length === 0}
          onClick={handleTextImport}
          type="button"
        >
          {running ? "导入中..." : "导入文本"}
        </button>
        <label className="cursor-pointer rounded-2xl border border-slate-200 px-4 py-2.5 text-center text-sm font-bold text-slate-700 hover:border-slate-300">
          上传文件
          <input className="hidden" type="file" accept=".blk,.csv,.txt" onChange={handleFileChange} />
        </label>
      </div>
      {error && <p className="mt-3 rounded-2xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {latest && (
        <div className="mt-3 rounded-2xl bg-slate-50 p-3 text-xs leading-6 text-slate-600">
          <div className="font-bold text-slate-800">已导入 {latest.item_count} 只</div>
          <div className="mt-1 line-clamp-3">{latest.items.map((item) => item.symbol).join("、")}</div>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Render tickflow status and watchlist observation**

Modify `apps/web/components/ProviderStatusPanel.tsx` to include TickFlow fallback in warning list:

```tsx
{status.tickflow?.fallback_used && (
  <li>TickFlow 已回退 fake：{status.tickflow.reason ?? "未知原因"}</li>
)}
```

Modify success summary to mention TickFlow when present:

```tsx
{status.tickflow ? ` · TickFlow ${status.tickflow.provider}` : ""}
```

Modify `apps/web/components/ReportPreview.tsx` after market metrics:

```tsx
{report.watchlist_observation && (
  <section className="mt-5 rounded-2xl border border-amber-100 bg-amber-50/60 p-4">
    <h3 className="text-sm font-black text-slate-950">自选股观察</h3>
    <p className="mt-1 text-xs text-slate-500">
      导入 {report.watchlist_observation.total_count} 只，行情匹配 {report.watchlist_observation.quote_count} 只
    </p>
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {report.watchlist_observation.strongest.slice(0, 3).map((item) => (
        <div key={`strong-${item.symbol}`} className="rounded-xl bg-white px-3 py-2 text-sm">
          <div className="font-bold text-slate-900">{item.name ?? item.symbol}</div>
          <div className="mt-1 text-red-600">{item.pct_change?.toFixed(2) ?? "--"}% · {item.symbol}</div>
        </div>
      ))}
    </div>
  </section>
)}
```

- [ ] **Step 5: Mount panel in page**

Modify `apps/web/app/page.tsx` imports:

```tsx
import { WatchlistImportPanel } from "../components/WatchlistImportPanel";
```

Add state:

```tsx
const [watchlistImported, setWatchlistImported] = useState(false);
```

Add panel in aside before `TaskProgress`:

```tsx
<WatchlistImportPanel onImported={() => setWatchlistImported(true)} />
{watchlistImported && <p className="rounded-2xl bg-emerald-50 p-3 text-sm text-emerald-700">自选股已导入，下一次生成报告会带入观察模块。</p>}
```

- [ ] **Step 6: Run frontend checks**

Run:

```bash
corepack pnpm --filter @stock-review/web test
corepack pnpm --filter @stock-review/web lint
```

Expected: PASS.

- [ ] **Step 7: Commit frontend**

```bash
git add apps/web/lib/types.ts apps/web/lib/api.ts apps/web/components/WatchlistImportPanel.tsx apps/web/components/ProviderStatusPanel.tsx apps/web/components/ReportPreview.tsx apps/web/app/page.tsx
git commit -m "feat: add watchlist import UI"
```

---

### Task 7: Docs, Env, and Full Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update env example**

Add to `.env.example` after provider settings:

```dotenv
TICKFLOW_API_KEY=
TICKFLOW_BASE_URL=https://api.tickflow.org
TICKFLOW_PROVIDER=tickflow
WATCHLIST_PROVIDER=local
WATCHLIST_SNAPSHOT_ROOT=./data/watchlists
```

- [ ] **Step 2: Update README**

Add section after LLM Structured Review:

```markdown
## Watchlist and TickFlow Enrichment

v0.3b imports local watchlists and adds a `自选股观察` block to generated HTML reports.

Supported import inputs:

- TongHuaShun-style `.blk` files containing six-digit A-share codes.
- `.csv` files with `代码`/`名称` or `code`/`name` columns.
- Plain text pasted codes.

TickFlow settings:

```dotenv
TICKFLOW_API_KEY=
TICKFLOW_BASE_URL=https://api.tickflow.org
TICKFLOW_PROVIDER=tickflow
WATCHLIST_PROVIDER=local
WATCHLIST_SNAPSHOT_ROOT=./data/watchlists
```

No key mode still works: TickFlow falls back to deterministic fake quotes and writes `provider_status.tickflow` to `snapshot.json`.
```

- [ ] **Step 3: Run backend verification**

Run:

```bash
cd apps/api
uv run pytest -v
uv run ruff check .
```

Expected: PASS.

- [ ] **Step 4: Run frontend verification**

Run:

```bash
corepack pnpm --filter @stock-review/web test
corepack pnpm --filter @stock-review/web lint
```

Expected: PASS.

- [ ] **Step 5: Run no-key smoke with imported watchlist**

Run:

```bash
rm -rf /tmp/stock-review-v03b-smoke
cd apps/api
DATABASE_URL=sqlite:////tmp/stock-review-v03b-smoke/api.db REPORTS_ROOT=/tmp/stock-review-v03b-smoke/reports WATCHLIST_SNAPSHOT_ROOT=/tmp/stock-review-v03b-smoke/watchlists MARKET_PROVIDER=fake NEWS_PROVIDER=fake TICKFLOW_PROVIDER=tickflow TICKFLOW_API_KEY= uv run python - <<'PY'
from fastapi.testclient import TestClient
from app.config import get_settings
from app.main import app

get_settings.cache_clear()
with TestClient(app) as client:
    imported = client.post('/api/watchlists/import-text', json={'content': '600000\n000001\n300750', 'source_name': 'manual.txt'})
    imported.raise_for_status()
    response = client.post('/api/reports/close', json={'trade_date': '2026-05-26'})
response.raise_for_status()
payload = response.json()
print(payload['assets']['html'])
print(payload['report']['watchlist_observation']['total_count'])
print(payload['provider_status']['tickflow'])
assert payload['report']['watchlist_observation']['total_count'] == 3
assert payload['provider_status']['tickflow']['status'] == 'fallback'
PY
```

Expected: prints generated HTML path, total count `3`, and TickFlow fallback status.

- [ ] **Step 6: Secret scan**

Run:

```bash
if rg -n "tk_[a-f0-9]{32}|sk-WAkD|c3faee0d" .env.example README.md docs apps; then exit 1; else echo "secret scan ok"; fi
```

Expected: `secret scan ok`.

- [ ] **Step 7: Commit docs**

```bash
git add .env.example README.md
git commit -m "docs: document watchlist tickflow enrichment"
```

---

## Self-Review

Spec coverage:

- Parser, persistence, API, TickFlow provider, report DTO, HTML, frontend import panel, docs, no-key smoke, and secret handling are covered.
- OCR remains explicitly out of scope.
- AkShare remains the broad market/sector provider; TickFlow only enriches watchlists.

Placeholder scan:

- No `TBD`, `TODO`, or “implement later” placeholders are required for execution.
- Every task contains concrete files, test code, implementation code, commands, expected outcomes, and commit commands.

Type consistency:

- Python uses `WatchlistItem`, `WatchlistImportResult`, `WatchlistQuote`, `WatchlistObservation` consistently.
- TypeScript mirrors backend JSON field names exactly: `import_id`, `item_count`, `watchlist_observation`, `provider_status.tickflow`.
- Provider status shape reuses existing `ProviderStatus` fields: `provider`, `status`, `fallback_used`, `reason`.
