# AI Watchlist Daily Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent AI-powered daily watchlist review system with durable watchlist groups, OpenAI/DeepSeek AI summaries, sector/limit-up/risk linkage, scheduled execution, and WeCom/Feishu/Telegram/email notifications.

**Architecture:** Add a durable watchlist pool first, then layer a daily review domain on top of it. Keep review calculation, AI summarization, scheduling, notification delivery, and UI as separate modules that communicate through typed DTOs and stored review records.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, SQLite, existing provider bundle, OpenAI-compatible SDK, Next.js, TypeScript, Tailwind, existing pytest/pnpm test setup.

---

## Scope Check

This is a multi-subsystem feature. Implement it in this order so each stage is testable on its own:

1. Durable watchlist pool and groups.
2. OpenAI/DeepSeek provider abstraction.
3. Daily watchlist review data model and rule engine.
4. AI memory generation.
5. Notification adapters.
6. Schedule loop.
7. Frontend pages.

Do not implement盘中监控 in this plan. Mention any intraday-only rule as future metadata only.

## File Structure

Backend files:

- Modify: `apps/api/app/db/models.py` for watchlist pool, review, and notification tables.
- Modify: `apps/api/app/db/session.py` for SQLite compatibility columns only if existing tables need additive columns.
- Create: `apps/api/app/watchlist/pool_service.py` for durable watchlist groups/stocks/tags.
- Modify: `apps/api/app/watchlist/service.py` to upsert imports into the durable pool.
- Modify: `apps/api/app/main.py` to expose watchlist pool, review, schedule, notification APIs and start the schedule loop.
- Modify: `apps/api/app/config.py` for DeepSeek and notification settings.
- Modify: `apps/api/app/providers/llm.py` and `apps/api/app/providers/factory.py` for DeepSeek/OpenAI-compatible AI.
- Create: `apps/api/app/services/watchlist_review.py` for review calculation.
- Create: `apps/api/app/services/watchlist_ai_review.py` for AI summary/memory generation.
- Create: `apps/api/app/services/watchlist_review_schedule.py` for scheduled daily review.
- Create: `apps/api/app/services/notification.py` for notification channels and deliveries.
- Test: `apps/api/tests/test_watchlist_pool.py`
- Test: `apps/api/tests/test_deepseek_provider.py`
- Test: `apps/api/tests/test_watchlist_daily_review.py`
- Test: `apps/api/tests/test_watchlist_review_schedule.py`
- Test: `apps/api/tests/test_notifications.py`

Frontend files:

- Modify: `apps/web/components/AdminShell.tsx` to expose `自选股` and `自选股复盘` entries.
- Create: `apps/web/app/watchlist/page.tsx` for group management.
- Create: `apps/web/app/watchlist-review/page.tsx` for daily review.
- Modify: `apps/web/lib/api.ts` for new endpoints.
- Modify: `apps/web/lib/types.ts` for new DTOs.
- Test: `apps/web/lib/watchlistGroupPage.test.ts`
- Test: `apps/web/lib/watchlistReviewPage.test.ts`
- Test: `apps/web/lib/notificationChannels.test.ts`

---

### Task 1: Durable Watchlist Pool Models and Service

**Files:**

- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/app/watchlist/pool_service.py`
- Modify: `apps/api/app/watchlist/service.py`
- Test: `apps/api/tests/test_watchlist_pool.py`

- [ ] **Step 1: Write failing watchlist pool tests**

Create `apps/api/tests/test_watchlist_pool.py`:

```python
from app.db.models import WatchlistGroup, WatchlistStock
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.watchlist.pool_service import WatchlistPoolService


def _service(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    return engine, WatchlistPoolService(engine)


def test_pool_creates_default_group_and_adds_stock(tmp_path):
    engine, service = _service(tmp_path)

    stock = service.add_stock(symbol="000001.SZ", name="平安银行")

    assert stock.symbol == "000001.SZ"
    with session_scope(engine) as session:
        groups = session.query(WatchlistGroup).all()
        assert [group.name for group in groups] == ["自选"]
        stored = session.query(WatchlistStock).filter_by(symbol="000001.SZ").one()
        assert stored.name == "平安银行"
        assert [group.name for group in stored.groups] == ["自选"]


def test_stock_can_belong_to_multiple_groups(tmp_path):
    _, service = _service(tmp_path)
    stock = service.add_stock(symbol="000001.SZ", name="平安银行")
    mlcc = service.create_group("MLCC")
    service.set_stock_groups(stock.id, [mlcc.id])
    service.add_stock_to_group(stock.id, "自选")

    pool = service.get_pool()
    item = next(item for item in pool.stocks if item.symbol == "000001.SZ")
    assert sorted(group.name for group in item.groups) == ["MLCC", "自选"]


def test_delete_custom_group_keeps_stock(tmp_path):
    _, service = _service(tmp_path)
    stock = service.add_stock(symbol="600563.SH", name="法拉电子")
    group = service.create_group("电力")
    service.set_stock_groups(stock.id, [group.id])

    service.delete_group(group.id)

    pool = service.get_pool()
    assert [item.symbol for item in pool.stocks] == ["600563.SH"]
    assert [group.name for group in pool.groups] == ["自选"]


def test_default_group_cannot_be_deleted(tmp_path):
    _, service = _service(tmp_path)
    default_group = service.ensure_default_group()

    try:
        service.delete_group(default_group.id)
    except ValueError as exc:
        assert "默认分组不可删除" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_pool.py -q
```

Expected: fail because `WatchlistPoolService`, `WatchlistGroup`, and `WatchlistStock` are not defined.

- [ ] **Step 3: Add SQLAlchemy models**

In `apps/api/app/db/models.py`, add:

```python
class WatchlistStock(Base):
    __tablename__ = "watchlist_stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(8), index=True)
    exchange: Mapped[str] = mapped_column(String(4))
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="观察中")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    groups: Mapped[list["WatchlistGroup"]] = relationship(secondary="watchlist_stock_groups", back_populates="stocks")


class WatchlistGroup(Base):
    __tablename__ = "watchlist_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    stocks: Mapped[list[WatchlistStock]] = relationship(secondary="watchlist_stock_groups", back_populates="groups")


class WatchlistStockGroup(Base):
    __tablename__ = "watchlist_stock_groups"

    stock_id: Mapped[int] = mapped_column(ForeignKey("watchlist_stocks.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("watchlist_groups.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
```

- [ ] **Step 4: Implement pool service**

Create `apps/api/app/watchlist/pool_service.py` with these Pydantic DTOs and service signatures:

```python
from pydantic import BaseModel
from sqlalchemy import Engine

from app.db.models import WatchlistGroup


class WatchlistPoolGroupDTO(BaseModel):
    id: int
    name: str
    is_default: bool
    sort_order: int


class WatchlistPoolStockDTO(BaseModel):
    id: int
    symbol: str
    code: str
    exchange: str
    name: str | None
    note: str | None
    status: str
    groups: list[WatchlistPoolGroupDTO]
    tags: list[str] = []


class WatchlistPoolState(BaseModel):
    groups: list[WatchlistPoolGroupDTO]
    stocks: list[WatchlistPoolStockDTO]


class WatchlistPoolService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def ensure_default_group(self) -> WatchlistGroup:
        raise NotImplementedError

    def create_group(self, name: str) -> WatchlistPoolGroupDTO:
        raise NotImplementedError

    def delete_group(self, group_id: int) -> None:
        raise NotImplementedError

    def add_stock(self, symbol: str, name: str | None = None, note: str | None = None) -> WatchlistPoolStockDTO:
        raise NotImplementedError

    def set_stock_groups(self, stock_id: int, group_ids: list[int]) -> WatchlistPoolStockDTO:
        raise NotImplementedError

    def add_stock_to_group(self, stock_id: int, group_name: str) -> WatchlistPoolStockDTO:
        raise NotImplementedError

    def get_pool(self) -> WatchlistPoolState:
        raise NotImplementedError
```

Implementation rules:

- `全部` remains virtual and is not stored.
- `自选` is stored, `is_default=True`, and cannot be deleted.
- `add_stock()` normalizes `code` and `exchange` from `symbol`.
- Duplicate stock add updates name/note but preserves existing groups.
- A stock with no explicit group is added to `自选`.

- [ ] **Step 5: Upsert imports into durable pool**

In `apps/api/app/watchlist/service.py`, after writing `WatchlistItemModel` rows, call:

```python
pool = WatchlistPoolService(self.engine)
for item in parsed.items:
    pool.add_stock(symbol=item.symbol, name=item.name)
```

Import `WatchlistPoolService` at the top.

- [ ] **Step 6: Run watchlist pool tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_pool.py -q
```

Expected: all tests pass.

---

### Task 2: Watchlist Pool API

**Files:**

- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_watchlist_pool.py`

- [ ] **Step 1: Add API tests**

Append to `apps/api/tests/test_watchlist_pool.py`:

```python
def test_watchlist_pool_api_adds_group_and_stock(client):
    group_response = client.post("/api/watchlists/groups", json={"name": "存储芯片"})
    assert group_response.status_code == 200
    stock_response = client.post("/api/watchlists/stocks", json={"symbol": "000001.SZ", "name": "平安银行"})
    assert stock_response.status_code == 200

    pool = client.get("/api/watchlists/pool").json()
    assert any(group["name"] == "存储芯片" for group in pool["groups"])
    assert any(stock["symbol"] == "000001.SZ" for stock in pool["stocks"])


def test_watchlist_pool_api_rejects_default_group_delete(client):
    pool = client.get("/api/watchlists/pool").json()
    default_group = next(group for group in pool["groups"] if group["name"] == "自选")

    response = client.delete(f"/api/watchlists/groups/{default_group['id']}")

    assert response.status_code == 400
    assert "默认分组不可删除" in response.text
```

- [ ] **Step 2: Run tests to verify API fails**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_pool.py -q
```

Expected: fail with 404 for new endpoints.

- [ ] **Step 3: Add request models and routes**

In `apps/api/app/main.py`, add request models:

```python
class CreateWatchlistGroupRequest(BaseModel):
    name: str


class CreateWatchlistStockRequest(BaseModel):
    symbol: str
    name: str | None = None
    note: str | None = None


class UpdateWatchlistStockGroupsRequest(BaseModel):
    group_ids: list[int]
```

Add helper:

```python
def _watchlist_pool_service() -> WatchlistPoolService:
    return WatchlistPoolService(app.state.engine)
```

Add routes:

```python
@app.get("/api/watchlists/pool")
def get_watchlist_pool() -> dict[str, object]:
    return _watchlist_pool_service().get_pool().model_dump(mode="json")


@app.post("/api/watchlists/groups")
def create_watchlist_group(request: CreateWatchlistGroupRequest) -> dict[str, object]:
    try:
        return _watchlist_pool_service().create_group(request.name).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/watchlists/groups/{group_id}")
def delete_watchlist_group(group_id: int) -> dict[str, object]:
    try:
        _watchlist_pool_service().delete_group(group_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": True, "id": group_id}


@app.post("/api/watchlists/stocks")
def create_watchlist_stock(request: CreateWatchlistStockRequest) -> dict[str, object]:
    return _watchlist_pool_service().add_stock(
        symbol=request.symbol,
        name=request.name,
        note=request.note,
    ).model_dump(mode="json")


@app.put("/api/watchlists/stocks/{stock_id}/groups")
def update_watchlist_stock_groups(stock_id: int, request: UpdateWatchlistStockGroupsRequest) -> dict[str, object]:
    return _watchlist_pool_service().set_stock_groups(stock_id, request.group_ids).model_dump(mode="json")
```

- [ ] **Step 4: Run API tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_pool.py -q
```

Expected: pass.

---

### Task 3: OpenAI/DeepSeek AI Provider Abstraction

**Files:**

- Modify: `apps/api/app/config.py`
- Modify: `apps/api/app/providers/llm.py`
- Modify: `apps/api/app/providers/factory.py`
- Test: `apps/api/tests/test_deepseek_provider.py`
- Test: `apps/api/tests/test_real_providers.py`

- [ ] **Step 1: Write failing DeepSeek tests**

Create `apps/api/tests/test_deepseek_provider.py`:

```python
import json

import pytest

from app.providers.llm import DeepSeekLLMProvider, LLMFallbackError
from tests.test_llm_provider import FakeClient, FakeCompletions, _valid_structured_payload


def test_deepseek_provider_uses_configured_model_and_json_response():
    completions = FakeCompletions(json.dumps(_valid_structured_payload(), ensure_ascii=False))
    provider = DeepSeekLLMProvider(
        api_key="sk-deepseek-local",
        base_url="https://api.deepseek.com",
        model_name="deepseek-v4-flash",
        client=FakeClient(completions),
    )

    review = provider.generate_structured_review({"trade_date": "2026-06-13"})

    assert review.topic
    assert completions.last_kwargs["model"] == "deepseek-v4-flash"
    assert completions.last_kwargs["response_format"] == {"type": "json_object"}


def test_deepseek_provider_rejects_missing_key():
    provider = DeepSeekLLMProvider(api_key="", base_url="https://api.deepseek.com", model_name="deepseek-v4-flash")

    with pytest.raises(LLMFallbackError, match="DEEPSEEK_API_KEY"):
        provider.generate_structured_review({"trade_date": "2026-06-13"})
```

Append to `apps/api/tests/test_real_providers.py`:

```python
def test_provider_factory_can_create_deepseek_llm_provider() -> None:
    from app.providers.llm import DeepSeekLLMProvider

    settings = Settings(
        llm_provider="deepseek",
        deepseek_api_key="sk-deepseek-local",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
    )

    bundle = create_provider_bundle(settings)

    assert isinstance(bundle.llm_provider, DeepSeekLLMProvider)
    assert bundle.llm_provider.model_name == "deepseek-v4-flash"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_deepseek_provider.py tests/test_real_providers.py::test_provider_factory_can_create_deepseek_llm_provider -q
```

Expected: fail because `DeepSeekLLMProvider` and settings fields do not exist.

- [ ] **Step 3: Add settings**

In `apps/api/app/config.py`, add:

```python
deepseek_api_key: str = ""
deepseek_base_url: str = "https://api.deepseek.com"
deepseek_model: str = "deepseek-v4-flash"
watchlist_ai_provider: str = "fake"
watchlist_ai_fallback_enabled: bool = True
```

Keep existing `llm_provider` for current report generation. Use `watchlist_ai_provider` later for watchlist review if the user wants daily review AI separate from report AI.

- [ ] **Step 4: Add reusable OpenAI-compatible provider base**

In `apps/api/app/providers/llm.py`, extract shared logic from `OpenAILLMProvider` into an internal base class:

```python
class OpenAICompatibleLLMProvider:
    provider_name = "openai_compatible"
    missing_key_name = "API_KEY"
    request_error_label = "AI 请求失败"

    def __init__(self, api_key: str, base_url: str, model_name: str, client: object | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.client = client

    def _client(self):
        return self.client or OpenAI(api_key=self.api_key, base_url=self.base_url)
```

Then make `OpenAILLMProvider` and `DeepSeekLLMProvider` subclasses. Preserve current OpenAI behavior and errors.

- [ ] **Step 5: Update factory**

In `apps/api/app/providers/factory.py`, import `DeepSeekLLMProvider` and add:

```python
if settings.llm_provider == "deepseek":
    return DeepSeekLLMProvider(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model_name=settings.deepseek_model,
    )
```

- [ ] **Step 6: Run provider tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_llm_provider.py tests/test_deepseek_provider.py tests/test_real_providers.py -q
```

Expected: pass.

---

### Task 4: Daily Watchlist Review Models and Rule Engine

**Files:**

- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/app/services/watchlist_review.py`
- Test: `apps/api/tests/test_watchlist_daily_review.py`

- [ ] **Step 1: Write failing review engine tests**

Create `apps/api/tests/test_watchlist_daily_review.py`:

```python
from app.db.session import create_sqlite_engine, init_db
from app.providers.quotes import WatchlistQuote
from app.services.watchlist_review import WatchlistDailyReviewService
from app.watchlist.pool_service import WatchlistPoolService


class FakeQuoteProvider:
    def get_quotes(self, symbols):
        return [
            WatchlistQuote(symbol="000001.SZ", name="平安银行", pct_change=4.2, turnover_rate=8.0, capital_strength="资金净流入"),
            WatchlistQuote(symbol="600563.SH", name="法拉电子", pct_change=-5.4, turnover_rate=23.0, capital_strength="资金净流出"),
        ]


def test_watchlist_daily_review_generates_attention_and_risk_items(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'review.db'}")
    init_db(engine)
    pool = WatchlistPoolService(engine)
    pool.add_stock("000001.SZ", "平安银行")
    pool.add_stock("600563.SH", "法拉电子")

    service = WatchlistDailyReviewService(engine=engine, quote_provider=FakeQuoteProvider())
    review = service.run(trade_date="2026-06-13")

    assert review.trade_date == "2026-06-13"
    assert review.status == "completed"
    assert len(review.items) == 2
    assert any(item.attention_level == "high" for item in review.items)
    assert any(item.risk_score > 0 for item in review.items)
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_daily_review.py -q
```

Expected: fail because models and service are missing.

- [ ] **Step 3: Add review models**

In `apps/api/app/db/models.py`, add:

```python
class WatchlistDailyReview(Base):
    __tablename__ = "watchlist_daily_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    scope: Mapped[str] = mapped_column(String(64), default="自选")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    summary: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    top_alerts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    sector_links: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    risk_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ai_status: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    notification_status: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    items: Mapped[list["WatchlistDailyReviewItem"]] = relationship(back_populates="review", cascade="all, delete-orphan")


class WatchlistDailyReviewItem(Base):
    __tablename__ = "watchlist_daily_review_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("watchlist_daily_reviews.id"), index=True)
    stock_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    concepts: Mapped[list[str]] = mapped_column(JSON, default=list)
    pct_change: Mapped[float | None] = mapped_column(JSON, nullable=True)
    turnover_rate: Mapped[float | None] = mapped_column(JSON, nullable=True)
    capital_flow: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ma_status: Mapped[str | None] = mapped_column(String(256), nullable=True)
    trend_status: Mapped[str | None] = mapped_column(String(256), nullable=True)
    near_200d_high: Mapped[bool] = mapped_column(Boolean, default=False)
    limit_up_related: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    sector_strength_score: Mapped[float] = mapped_column(Integer, default=0)
    stock_trend_score: Mapped[float] = mapped_column(Integer, default=0)
    risk_score: Mapped[float] = mapped_column(Integer, default=0)
    attention_level: Mapped[str] = mapped_column(String(32), default="watch_only")
    ai_comment: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    review: Mapped[WatchlistDailyReview] = relationship(back_populates="items")
```

- [ ] **Step 4: Implement rule engine service**

Create `apps/api/app/services/watchlist_review.py` with these DTOs and service shell, then fill the methods in the same step:

```python
from pydantic import BaseModel
from sqlalchemy import Engine

from app.providers.quotes import QuoteProvider


class WatchlistDailyReviewItemDTO(BaseModel):
    symbol: str
    name: str | None
    groups: list[str]
    tags: list[str]
    industry: str | None = None
    concepts: list[str] = []
    pct_change: float | None = None
    turnover_rate: float | None = None
    capital_flow: str | None = None
    ma_status: str | None = None
    trend_status: str | None = None
    near_200d_high: bool = False
    limit_up_related: list[dict[str, object]] = []
    sector_strength_score: float = 0
    stock_trend_score: float = 0
    risk_score: float = 0
    attention_level: str = "watch_only"
    ai_comment: str | None = None


class WatchlistDailyReviewDTO(BaseModel):
    id: int
    trade_date: str
    scope: str
    status: str
    summary: str | None
    top_alerts: list[dict[str, object]]
    sector_links: list[dict[str, object]]
    risk_items: list[dict[str, object]]
    ai_status: dict[str, object] | None
    notification_status: dict[str, object] | None
    items: list[WatchlistDailyReviewItemDTO]


class WatchlistDailyReviewService:
    def __init__(self, engine: Engine, quote_provider: QuoteProvider, ai_provider: object | None = None) -> None:
        self.engine = engine
        self.quote_provider = quote_provider
        self.ai_provider = ai_provider

    def run(self, trade_date: str, scope: str = "自选") -> WatchlistDailyReviewDTO:
        raise NotImplementedError
```

Minimal first implementation:

- Load durable pool from `WatchlistPoolService`.
- Quote symbols through `quote_provider.get_quotes`.
- Score:
  - `pct_change >= 3`: `stock_trend_score += 30`
  - `capital_strength` contains `净流入`: `sector_strength_score += 20`
  - `pct_change <= -5`: `risk_score += 50`
  - `turnover_rate >= 20 and pct_change < 0`: `risk_score += 20`
  - `capital_strength` contains `流出`: `risk_score += 20`
- `attention_level`:
  - `risk_score >= 50`: `medium` with risk item.
  - `stock_trend_score + sector_strength_score >= 40`: `high`.
  - else `watch_only`.
- Persist `WatchlistDailyReview` and `WatchlistDailyReviewItem`.

- [ ] **Step 5: Run review engine tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_daily_review.py -q
```

Expected: pass.

---

### Task 5: AI Memory Generation for Watchlist Reviews

**Files:**

- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/app/services/watchlist_ai_review.py`
- Modify: `apps/api/app/services/watchlist_review.py`
- Test: `apps/api/tests/test_watchlist_daily_review.py`

- [ ] **Step 1: Add AI memory test**

Append:

```python
class FakeAIReviewProvider:
    provider_name = "fake_ai"
    model_name = "fake-watchlist"

    def generate_watchlist_review(self, seed):
        return {
            "summary": "今日自选股中，平安银行强度靠前，法拉电子触发风险检查。",
            "comments": {
                "000001.SZ": "放量上涨，明日观察是否继续站稳短期均线。",
                "600563.SH": "高换手下跌，先进入风险检查。",
            },
        }


def test_watchlist_review_writes_ai_comments_and_memory(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'review-ai.db'}")
    init_db(engine)
    pool = WatchlistPoolService(engine)
    pool.add_stock("000001.SZ", "平安银行")
    pool.add_stock("600563.SH", "法拉电子")

    service = WatchlistDailyReviewService(
        engine=engine,
        quote_provider=FakeQuoteProvider(),
        ai_provider=FakeAIReviewProvider(),
    )
    review = service.run(trade_date="2026-06-13")

    assert review.summary.startswith("今日自选股")
    assert any(item.ai_comment for item in review.items)
    assert review.ai_status["provider"] == "fake_ai"
```

- [ ] **Step 2: Add stock notes model**

In `apps/api/app/db/models.py`, add:

```python
class WatchlistStockNote(Base):
    __tablename__ = "watchlist_stock_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("watchlist_stocks.id"), index=True)
    note_type: Mapped[str] = mapped_column(String(32), default="ai_memory")
    content: Mapped[str] = mapped_column(String(4096))
    trade_date: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
```

- [ ] **Step 3: Implement AI review adapter**

Create `apps/api/app/services/watchlist_ai_review.py`:

```python
class WatchlistAIReview(BaseModel):
    summary: str
    comments: dict[str, str]


class RuleWatchlistAIReviewProvider:
    provider_name = "rule"
    model_name = "watchlist-rule-v1"

    def generate_watchlist_review(self, seed: dict[str, object]) -> WatchlistAIReview:
        items = seed.get("items") if isinstance(seed.get("items"), list) else []
        high_count = sum(1 for item in items if isinstance(item, dict) and item.get("attention_level") == "high")
        risk_count = sum(1 for item in items if isinstance(item, dict) and float(item.get("risk_score") or 0) > 0)
        return WatchlistAIReview(
            summary=f"今日自选股重点提醒 {high_count} 只，风险检查 {risk_count} 只。",
            comments={},
        )
```

- [ ] **Step 4: Wire AI into review service**

In `WatchlistDailyReviewService.__init__`, accept `ai_provider: object | None = None`.

In `run()`, after rule items are built:

```python
ai_status = {"provider": "rule", "model": "watchlist-rule-v1", "fallback_used": False}
summary = rule_summary
try:
    ai_result = self.ai_provider.generate_watchlist_review(seed) if self.ai_provider else RuleWatchlistAIReviewProvider().generate_watchlist_review(seed)
    summary = ai_result.summary if hasattr(ai_result, "summary") else str(ai_result["summary"])
    comments = ai_result.comments if hasattr(ai_result, "comments") else dict(ai_result.get("comments", {}))
except Exception as exc:
    comments = {}
    ai_status = {"provider": "rule", "model": "watchlist-rule-v1", "fallback_used": True, "reason": exc.__class__.__name__}
```

Update item comments and persist `WatchlistStockNote` for non-empty comments.

- [ ] **Step 5: Run tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_daily_review.py -q
```

Expected: pass.

---

### Task 6: Notification Channels and Delivery Log

**Files:**

- Modify: `apps/api/app/config.py`
- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/app/services/notification.py`
- Test: `apps/api/tests/test_notifications.py`

- [ ] **Step 1: Write notification tests**

Create `apps/api/tests/test_notifications.py`:

```python
from app.services.notification import NotificationMessage, NotificationService, TelegramNotifier


class FakeHttpClient:
    def __init__(self):
        self.posts = []

    def post(self, url, json=None, data=None, timeout=None):
        self.posts.append({"url": url, "json": json, "data": data, "timeout": timeout})
        return type("Response", (), {"status_code": 200, "text": "ok", "raise_for_status": lambda self: None})()


def test_telegram_notifier_sends_message_without_leaking_token():
    client = FakeHttpClient()
    notifier = TelegramNotifier(bot_token="secret-token", chat_id="123", http_client=client)

    result = notifier.send(NotificationMessage(title="自选股复盘", body="今日重点提醒 2 只。"))

    assert result.status == "sent"
    assert "secret-token" not in result.model_dump_json()
    assert client.posts[0]["json"]["chat_id"] == "123"


def test_notification_service_continues_when_one_channel_fails():
    service = NotificationService(
        channels=[
            lambda message: type("R", (), {"channel_type": "broken", "status": "failed", "error": "boom"})(),
            lambda message: type("R", (), {"channel_type": "email", "status": "sent", "error": None})(),
        ]
    )

    results = service.send_all(NotificationMessage(title="测试", body="内容"))

    assert [result.status for result in results] == ["failed", "sent"]
```

- [ ] **Step 2: Add notification settings**

In `apps/api/app/config.py`, add:

```python
wecom_webhook_url: str = ""
feishu_webhook_url: str = ""
telegram_bot_token: str = ""
telegram_chat_id: str = ""
smtp_host: str = ""
smtp_port: int = 587
smtp_username: str = ""
smtp_password: str = ""
smtp_from: str = ""
smtp_to: str = ""
```

- [ ] **Step 3: Add delivery model**

In `apps/api/app/db/models.py`, add:

```python
class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    channel_type: Mapped[str] = mapped_column(String(32), index=True)
    channel_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    message_title: Mapped[str] = mapped_column(String(256))
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
```

- [ ] **Step 4: Implement notification service**

Create `apps/api/app/services/notification.py` with:

```python
class NotificationMessage(BaseModel):
    title: str
    body: str
    html: str | None = None


class NotificationResult(BaseModel):
    channel_type: str
    status: Literal["sent", "failed", "skipped"]
    error: str | None = None
```

Implement:

- `WeComNotifier.send()`: POST markdown payload to webhook.
- `FeishuNotifier.send()`: POST markdown/text payload to webhook.
- `TelegramNotifier.send()`: POST to `https://api.telegram.org/bot{token}/sendMessage`.
- `EmailNotifier.send()`: use `smtplib.SMTP`, start TLS, login if username exists.
- `NotificationService.send_all()`: send to every enabled channel and collect results.

All exception messages must be sanitized with class names only, not raw tokens or webhook URLs.

- [ ] **Step 5: Run notification tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_notifications.py -q
```

Expected: pass.

---

### Task 7: Watchlist Review API and Schedule

**Files:**

- Create: `apps/api/app/services/watchlist_review_schedule.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_watchlist_review_schedule.py`

- [ ] **Step 1: Write schedule tests**

Create `apps/api/tests/test_watchlist_review_schedule.py`:

```python
from datetime import UTC, datetime

from app.db.session import create_sqlite_engine, init_db
from app.services.watchlist_review_schedule import WatchlistReviewScheduleUpdate, run_due_watchlist_review_schedule


def test_watchlist_review_schedule_runs_once_after_due_time(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'schedule.db'}")
    init_db(engine)
    calls = []

    status = run_due_watchlist_review_schedule(
        engine=engine,
        update=WatchlistReviewScheduleUpdate(enabled=True, time="19:30", timezone="Asia/Shanghai"),
        run_review=lambda trade_date: calls.append(trade_date) or {"status": "completed"},
        now=datetime(2026, 6, 13, 12, 0, tzinfo=UTC),
    )

    assert calls == ["2026-06-13"]
    assert status["last_result"]["status"] == "completed"
```

- [ ] **Step 2: Implement schedule config model**

Either create a dedicated `WatchlistReviewScheduleConfig` model or reuse the existing schedule pattern with a new table. Prefer a new table to keep it independent from report scheduling.

Fields:

- `enabled`
- `time`
- `timezone`
- `last_run_at`
- `last_result`

- [ ] **Step 3: Implement schedule service**

Create `apps/api/app/services/watchlist_review_schedule.py`, mirroring `report_schedule.py` with these public functions:

```python
class WatchlistReviewScheduleUpdate(BaseModel):
    enabled: bool
    time: str = "19:30"
    timezone: str = "Asia/Shanghai"


def get_watchlist_review_schedule_status(engine: Engine, settings: Settings) -> dict[str, object]:
    config = _get_or_create_config(engine, settings)
    return _status_payload(config)


def update_watchlist_review_schedule_status(
    engine: Engine,
    settings: Settings,
    update: WatchlistReviewScheduleUpdate,
) -> dict[str, object]:
    _validate_schedule_time(update.time)
    ZoneInfo(update.timezone)
    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        config.enabled = update.enabled
        config.time = update.time
        config.timezone = update.timezone
        session.flush()
        return _status_payload(config)


def run_due_watchlist_review_schedule(
    engine: Engine,
    settings: Settings,
    run_review,
    now: datetime | None = None,
) -> dict[str, object]:
    current_utc = now or datetime.now(UTC)
    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        if not config.enabled:
            return _status_payload(config)
        due_trade_date = _due_trade_date(config, current_utc)
        if due_trade_date is None:
            return _status_payload(config)
    result = run_review(due_trade_date)
    with session_scope(engine) as session:
        config = _get_or_create_config_in_session(session, settings)
        config.last_run_at = current_utc
        config.last_result = {"status": result.get("status", "completed"), "trade_date": due_trade_date}
        session.flush()
        return _status_payload(config)
```

- [ ] **Step 4: Add routes and loop**

In `apps/api/app/main.py`:

- Start `app.state.watchlist_review_schedule_task` in lifespan.
- Cancel it in lifespan shutdown.
- Add `_watchlist_review_schedule_loop()`.
- Add `_run_watchlist_review_schedule_once()`.
- Add `GET /api/watchlist-review-schedule/status`.
- Add `PUT /api/watchlist-review-schedule/status`.
- Add `POST /api/watchlist-reviews/run`.
- Add `GET /api/watchlist-reviews/latest`.
- Add `GET /api/watchlist-reviews/{review_id}`.
- Add `POST /api/watchlist-reviews/{review_id}/notify`.

- [ ] **Step 5: Run schedule tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_review_schedule.py -q
```

Expected: pass.

---

### Task 8: Frontend Watchlist and Review Pages

**Files:**

- Modify: `apps/web/components/AdminShell.tsx`
- Create: `apps/web/app/watchlist/page.tsx`
- Create: `apps/web/app/watchlist-review/page.tsx`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/types.ts`
- Test: `apps/web/lib/watchlistGroupPage.test.ts`
- Test: `apps/web/lib/watchlistReviewPage.test.ts`

- [ ] **Step 1: Add TypeScript DTOs**

In `apps/web/lib/types.ts`, add:

```ts
export type WatchlistPoolGroup = {
  id: number;
  name: string;
  is_default: boolean;
  sort_order: number;
};

export type WatchlistPoolStock = {
  id: number;
  symbol: string;
  code: string;
  exchange: "SH" | "SZ" | "BJ";
  name: string | null;
  note: string | null;
  status: string;
  groups: WatchlistPoolGroup[];
  tags: string[];
};

export type WatchlistPoolState = {
  groups: WatchlistPoolGroup[];
  stocks: WatchlistPoolStock[];
};

export type WatchlistDailyReviewItem = {
  symbol: string;
  name: string | null;
  groups: string[];
  industry: string | null;
  concepts: string[];
  pct_change: number | null;
  capital_flow: string | null;
  risk_score: number;
  attention_level: "high" | "medium" | "low" | "watch_only";
  ai_comment: string | null;
};

export type WatchlistDailyReview = {
  id: number;
  trade_date: string;
  scope: string;
  status: string;
  summary: string | null;
  top_alerts: Array<Record<string, unknown>>;
  sector_links: Array<Record<string, unknown>>;
  risk_items: Array<Record<string, unknown>>;
  ai_status: Record<string, unknown> | null;
  notification_status: Record<string, unknown> | null;
  items: WatchlistDailyReviewItem[];
};
```

- [ ] **Step 2: Add API client functions**

In `apps/web/lib/api.ts`, import the new types and add:

```ts
export async function getWatchlistPool(): Promise<WatchlistPoolState> {
  const response = await fetch(`${API_BASE_URL}/api/watchlists/pool`);
  if (!response.ok) {
    throw new Error(`读取自选股池失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistPoolState>;
}

export async function createWatchlistGroup(name: string): Promise<WatchlistPoolGroup> {
  const response = await fetch(`${API_BASE_URL}/api/watchlists/groups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error(`创建分组失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistPoolGroup>;
}

export async function deleteWatchlistGroup(groupId: number): Promise<{ deleted: boolean; id: number }> {
  const response = await fetch(`${API_BASE_URL}/api/watchlists/groups/${groupId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`删除分组失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<{ deleted: boolean; id: number }>;
}

export async function createWatchlistStock(payload: {
  symbol: string;
  name?: string;
  note?: string;
}): Promise<WatchlistPoolStock> {
  const response = await fetch(`${API_BASE_URL}/api/watchlists/stocks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`添加自选股失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistPoolStock>;
}

export async function runWatchlistReview(tradeDate: string): Promise<WatchlistDailyReview> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-reviews/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trade_date: tradeDate }),
  });
  if (!response.ok) {
    throw new Error(`运行自选股复盘失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistDailyReview>;
}

export async function getLatestWatchlistReview(): Promise<WatchlistDailyReview | null> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-reviews/latest`);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`读取自选股复盘失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistDailyReview>;
}
```

- [ ] **Step 3: Update navigation**

In `apps/web/components/AdminShell.tsx`, change the nav items:

```ts
const navItems = [
  { label: "概览", hint: "Dashboard", href: "/" },
  { label: "报告生成", hint: "Generate", href: "/#generate" },
  { label: "历史报告", hint: "Reports", href: "/#reports" },
  { label: "数据源状态", hint: "Sources", href: "/#sources" },
  { label: "自选股", hint: "Watchlist", href: "/watchlist" },
  { label: "自选股复盘", hint: "Review", href: "/watchlist-review" },
];
```

- [ ] **Step 4: Build watchlist page**

Create `apps/web/app/watchlist/page.tsx`:

- Left column: groups, create group button, delete custom group action.
- Main table: stock symbol, name, groups, note, status.
- Top action: add stock.
- Delete group confirmation text must say stocks are retained.

- [ ] **Step 5: Build review page**

Create `apps/web/app/watchlist-review/page.tsx`:

- Header: latest review date, status, manual run button.
- Summary: AI summary.
- Sections: `重点提醒`, `风险检查`, `板块联动`, `单股明细`, `通知发送记录`.
- Empty state: ask user to add watchlist stocks first.

- [ ] **Step 6: Add frontend tests**

Create tests that read source files and assert user-visible requirements:

```ts
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

test("admin navigation exposes watchlist pages", () => {
  const source = fs.readFileSync(path.join(process.cwd(), "components/AdminShell.tsx"), "utf8");
  assert.match(source, /自选股/);
  assert.match(source, /自选股复盘/);
  assert.match(source, /\/watchlist-review/);
});
```

- [ ] **Step 7: Run frontend tests**

Run:

```bash
cd apps/web && corepack pnpm test
```

Expected: pass.

---

### Task 9: End-to-End Verification

**Files:**

- No new files unless tests reveal gaps.

- [ ] **Step 1: Run full backend verification**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest -q
cd apps/api && .venv/bin/python -m ruff check app tests
```

Expected: all tests and lint pass.

- [ ] **Step 2: Run full frontend verification**

Run:

```bash
cd apps/web && corepack pnpm test
```

Expected: all tests pass.

- [ ] **Step 3: Start dev servers**

Run API:

```bash
cd apps/api && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run web:

```bash
cd apps/web && corepack pnpm dev --host 127.0.0.1 --port 3000
```

- [ ] **Step 4: Browser smoke test**

Open:

```text
http://127.0.0.1:3000/watchlist
```

Verify:

- Create group `MLCC`.
- Add a stock.
- Assign stock to multiple groups.
- Delete `MLCC`; stock remains in `自选`.

Open:

```text
http://127.0.0.1:3000/watchlist-review
```

Verify:

- Manual review run returns a result.
- Summary, risk items, and single-stock table render.
- Notification channel status is visible.

- [ ] **Step 5: Commit**

Commit only files touched for this feature:

```bash
git status --short
git add apps/api/app/db/models.py apps/api/app/db/session.py apps/api/app/watchlist/pool_service.py apps/api/app/watchlist/service.py apps/api/app/main.py apps/api/app/config.py apps/api/app/providers/llm.py apps/api/app/providers/factory.py apps/api/app/services/watchlist_review.py apps/api/app/services/watchlist_ai_review.py apps/api/app/services/watchlist_review_schedule.py apps/api/app/services/notification.py apps/api/tests/test_watchlist_pool.py apps/api/tests/test_deepseek_provider.py apps/api/tests/test_watchlist_daily_review.py apps/api/tests/test_watchlist_review_schedule.py apps/api/tests/test_notifications.py apps/web/components/AdminShell.tsx apps/web/app/watchlist/page.tsx apps/web/app/watchlist-review/page.tsx apps/web/lib/api.ts apps/web/lib/types.ts apps/web/lib/watchlistGroupPage.test.ts apps/web/lib/watchlistReviewPage.test.ts
git commit -m "feat: add ai watchlist daily review"
```

Expected: commit succeeds. Do not stage unrelated existing dirty files.
