# AI Watchlist Alert Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first version of the AI watchlist alert engine: a durable watchlist observation pool, explainable alert events, rule-based risk/opportunity scans, throttled notifications, settings, and an alert-center UI.

**Architecture:** The current repository still has the legacy watchlist import snapshot model, so the first task creates a durable watchlist pool that later alert tasks can depend on. The alert engine is deterministic: rules create events, persistence deduplicates them, AI only comments on already-triggered events, and notifications are sent only after throttling. Realtime continuous monitoring and complex task workflow stay out of this version.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, SQLite, existing provider bundle, TickFlow provider, OpenAI-compatible LLM provider, Next.js, TypeScript, Tailwind, pytest, Node test runner.

---

## Scope Check

This is one coherent first-version feature with one dependency chain:

1. Durable watchlist pool and observation plan.
2. Alert event persistence.
3. Health/settings primitives.
4. Rule engine, dedupe, and write-back.
5. Notifications and schedule/API endpoints.
6. Alert center, settings, and watchlist UI.

Do not implement:

- continuous realtime monitoring,
- auto-trading,
- position management,
- complex task workflow,
- buy/sell directive wording.

## File Structure

Backend files:

- Modify: `apps/api/app/db/models.py` for durable watchlist pool, observation plan, alert events, alert settings, and delivery records.
- Modify: `apps/api/app/db/session.py` for additive SQLite bootstrap of new columns/tables when existing local databases are opened.
- Modify: `apps/api/app/config.py` for alert schedule, throttle, AI, and notification settings.
- Create: `apps/api/app/watchlist/pool_service.py` for long-lived watchlist groups/stocks/tags/observation plans.
- Modify: `apps/api/app/watchlist/service.py` so text/file/OCR imports also upsert the durable pool.
- Create: `apps/api/app/services/watchlist_alerts.py` for alert event rules, dedupe, persistence, and write-back.
- Create: `apps/api/app/services/watchlist_alert_schedule.py` for 10:00, 14:30, and 19:30 scan scheduling.
- Create: `apps/api/app/services/tickflow_health.py` for manual TickFlow capability/status payloads.
- Create: `apps/api/app/services/notification.py` for WeCom, Feishu, Telegram, email, and testable message sending.
- Create: `apps/api/app/services/watchlist_ai_review.py` for rule fallback commentary and OpenAI/DeepSeek-compatible AI commentary.
- Modify: `apps/api/app/main.py` for watchlist pool, alert, settings, health, and schedule APIs.
- Test: `apps/api/tests/test_watchlist_pool.py`
- Test: `apps/api/tests/test_watchlist_alerts.py`
- Test: `apps/api/tests/test_watchlist_alert_schedule.py`
- Test: `apps/api/tests/test_tickflow_health.py`
- Test: `apps/api/tests/test_notifications.py`
- Test: `apps/api/tests/test_watchlist_api.py`

Frontend files:

- Modify: `apps/web/components/AdminShell.tsx` to show route-aware navigation for 首页, 自选股, 提醒中心, 设置.
- Create: `apps/web/app/watchlist/page.tsx` for durable watchlist group/plan management.
- Create: `apps/web/app/watchlist-alerts/page.tsx` for alert center event handling.
- Create: `apps/web/app/settings/page.tsx` for alert schedule, channels, and TickFlow health.
- Modify: `apps/web/app/page.tsx` to expose entry cards and latest alert summary.
- Modify: `apps/web/lib/api.ts` for watchlist pool, alert, health, and settings endpoints.
- Modify: `apps/web/lib/types.ts` for DTOs.
- Test: `apps/web/lib/watchlistPoolPage.test.ts`
- Test: `apps/web/lib/watchlistAlertCenter.test.ts`
- Test: `apps/web/lib/watchlistSettingsPanel.test.ts`

---

### Task 1: Durable Watchlist Pool and Observation Plan

**Files:**

- Modify: `apps/api/app/db/models.py`
- Modify: `apps/api/app/db/session.py`
- Create: `apps/api/app/watchlist/pool_service.py`
- Modify: `apps/api/app/watchlist/service.py`
- Test: `apps/api/tests/test_watchlist_pool.py`

- [ ] **Step 1: Write failing durable-pool tests**

Create `apps/api/tests/test_watchlist_pool.py`:

```python
from app.db.models import WatchlistGroup, WatchlistStock
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.watchlist.pool_service import WatchlistPoolService


def _service(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    return engine, WatchlistPoolService(engine)


def test_add_stock_creates_default_group_and_observation_plan(tmp_path):
    engine, service = _service(tmp_path)

    stock = service.add_stock(
        symbol="000001.SZ",
        name="平安银行",
        observation_plan={
            "entry_reason": "银行方向观察",
            "planned_buy_price": "回踩MA10",
            "invalid_condition": "跌破MA20",
            "themes": "银行",
        },
    )

    assert stock.symbol == "000001.SZ"
    assert stock.observation_plan.entry_reason == "银行方向观察"
    assert stock.observation_plan.invalid_condition == "跌破MA20"
    with session_scope(engine) as session:
        groups = session.query(WatchlistGroup).all()
        stored = session.query(WatchlistStock).filter_by(symbol="000001.SZ").one()
        assert [group.name for group in groups] == ["自选"]
        assert [group.name for group in stored.groups] == ["自选"]
        assert stored.observation_plan["planned_buy_price"] == "回踩MA10"


def test_stock_can_belong_to_multiple_groups_and_tags(tmp_path):
    _, service = _service(tmp_path)
    stock = service.add_stock(symbol="000001.SZ", name="平安银行")
    bank = service.create_group("银行")
    dividend = service.create_group("红利")

    service.set_stock_groups(stock.id, [bank.id, dividend.id])
    service.set_stock_tags(stock.id, ["低估值", "观察"])

    pool = service.get_pool()
    item = next(item for item in pool.stocks if item.symbol == "000001.SZ")
    assert [group.name for group in item.groups] == ["银行", "红利"]
    assert item.tags == ["低估值", "观察"]


def test_delete_custom_group_keeps_stock(tmp_path):
    _, service = _service(tmp_path)
    stock = service.add_stock(symbol="600563.SH", name="法拉电子")
    group = service.create_group("MLCC")
    service.set_stock_groups(stock.id, [group.id])

    service.delete_group(group.id)

    pool = service.get_pool()
    assert [item.symbol for item in pool.stocks] == ["600563.SH"]
    assert [group.name for group in pool.groups] == ["自选"]


def test_import_text_upserts_durable_pool(tmp_path):
    from app.watchlist.service import WatchlistImportService

    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistImportService(engine=engine, snapshot_root=tmp_path / "watchlists")

    service.import_text("600000 浦发银行\n000001 平安银行\n", source_name="manual.txt")

    pool = WatchlistPoolService(engine).get_pool()
    assert [item.symbol for item in pool.stocks] == ["600000.SH", "000001.SZ"]
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_pool.py -q
```

Expected: FAIL because `WatchlistPoolService`, `WatchlistStock`, and `WatchlistGroup` are missing.

- [ ] **Step 3: Add durable watchlist models**

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
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    observation_plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    groups: Mapped[list["WatchlistGroup"]] = relationship(
        secondary="watchlist_stock_groups",
        back_populates="stocks",
    )


class WatchlistGroup(Base):
    __tablename__ = "watchlist_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    stocks: Mapped[list[WatchlistStock]] = relationship(
        secondary="watchlist_stock_groups",
        back_populates="groups",
    )


class WatchlistStockGroup(Base):
    __tablename__ = "watchlist_stock_groups"

    stock_id: Mapped[int] = mapped_column(ForeignKey("watchlist_stocks.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("watchlist_groups.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
```

- [ ] **Step 4: Implement the pool service**

Create `apps/api/app/watchlist/pool_service.py`:

```python
from pydantic import BaseModel
from sqlalchemy import Engine, select

from app.db.models import WatchlistGroup, WatchlistStock
from app.db.session import session_scope
from app.watchlist.parser import _infer_exchange

DEFAULT_GROUP_NAME = "自选"
VALID_STOCK_STATUSES = {"观察中", "持有中"}
OBSERVATION_PLAN_FIELDS = (
    "entry_reason",
    "planned_buy_price",
    "invalid_condition",
    "themes",
    "last_review_conclusion",
    "today_risk_hint",
)


class WatchlistPoolGroupDTO(BaseModel):
    id: int
    name: str
    is_default: bool
    sort_order: int


class WatchlistObservationPlanDTO(BaseModel):
    entry_reason: str = ""
    planned_buy_price: str = ""
    invalid_condition: str = ""
    themes: str = ""
    last_review_conclusion: str = ""
    today_risk_hint: str = ""


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
    observation_plan: WatchlistObservationPlanDTO = WatchlistObservationPlanDTO()


class WatchlistPoolState(BaseModel):
    groups: list[WatchlistPoolGroupDTO]
    stocks: list[WatchlistPoolStockDTO]


class WatchlistPoolService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def ensure_default_group(self) -> WatchlistPoolGroupDTO:
        with session_scope(self.engine) as session:
            return _group_dto(_ensure_default_group(session))

    def create_group(self, name: str) -> WatchlistPoolGroupDTO:
        group_name = _clean_group_name(name)
        with session_scope(self.engine) as session:
            if _group_by_name(session, group_name):
                raise ValueError("分组名已存在")
            orders = session.execute(select(WatchlistGroup.sort_order)).scalars().all()
            group = WatchlistGroup(
                name=group_name,
                is_default=False,
                sort_order=(max(orders) + 1) if orders else 1,
            )
            session.add(group)
            session.flush()
            return _group_dto(group)

    def delete_group(self, group_id: int) -> None:
        with session_scope(self.engine) as session:
            group = session.get(WatchlistGroup, group_id)
            if group is None:
                raise ValueError("分组不存在")
            if group.is_default:
                raise ValueError("默认分组不可删除")
            session.delete(group)

    def add_stock(
        self,
        symbol: str,
        name: str | None = None,
        note: str | None = None,
        status: str = "观察中",
        group_ids: list[int] | None = None,
        tags: list[str] | None = None,
        observation_plan: dict[str, object] | None = None,
    ) -> WatchlistPoolStockDTO:
        normalized = _normalize_symbol(symbol)
        cleaned_status = _clean_status(status)
        cleaned_plan = _clean_observation_plan(observation_plan)
        with session_scope(self.engine) as session:
            default_group = _ensure_default_group(session)
            groups = _groups_by_ids(session, group_ids) if group_ids is not None else [default_group]
            stock = session.execute(
                select(WatchlistStock).where(WatchlistStock.symbol == normalized["symbol"])
            ).scalar_one_or_none()
            if stock is None:
                stock = WatchlistStock(
                    symbol=normalized["symbol"],
                    code=normalized["code"],
                    exchange=normalized["exchange"],
                    name=name,
                    note=note,
                    status=cleaned_status,
                    groups=groups,
                    tags=_clean_tags(tags or []),
                    observation_plan=cleaned_plan,
                )
                session.add(stock)
            else:
                if name:
                    stock.name = name
                if note is not None:
                    stock.note = note
                stock.status = cleaned_status
                stock.groups = groups
                stock.tags = _clean_tags(tags or stock.tags or [])
                if observation_plan is not None:
                    stock.observation_plan = cleaned_plan
            session.flush()
            return _stock_dto(stock)

    def set_stock_groups(self, stock_id: int, group_ids: list[int]) -> WatchlistPoolStockDTO:
        with session_scope(self.engine) as session:
            stock = session.get(WatchlistStock, stock_id)
            if stock is None:
                raise ValueError("股票不存在")
            stock.groups = _groups_by_ids(session, group_ids)
            session.flush()
            return _stock_dto(stock)

    def set_stock_tags(self, stock_id: int, tags: list[str]) -> WatchlistPoolStockDTO:
        with session_scope(self.engine) as session:
            stock = session.get(WatchlistStock, stock_id)
            if stock is None:
                raise ValueError("股票不存在")
            stock.tags = _clean_tags(tags)
            session.flush()
            return _stock_dto(stock)

    def update_review_result(
        self,
        stock_id: int,
        last_review_conclusion: str | None = None,
        today_risk_hint: str | None = None,
    ) -> WatchlistPoolStockDTO:
        with session_scope(self.engine) as session:
            stock = session.get(WatchlistStock, stock_id)
            if stock is None:
                raise ValueError("股票不存在")
            plan = _clean_observation_plan(stock.observation_plan)
            if last_review_conclusion is not None:
                plan["last_review_conclusion"] = last_review_conclusion.strip()
            if today_risk_hint is not None:
                plan["today_risk_hint"] = today_risk_hint.strip()
            stock.observation_plan = plan
            session.flush()
            return _stock_dto(stock)

    def get_pool(self) -> WatchlistPoolState:
        with session_scope(self.engine) as session:
            _ensure_default_group(session)
            groups = session.execute(
                select(WatchlistGroup).order_by(WatchlistGroup.sort_order, WatchlistGroup.id)
            ).scalars().all()
            stocks = session.execute(select(WatchlistStock).order_by(WatchlistStock.id)).scalars().all()
            return WatchlistPoolState(
                groups=[_group_dto(group) for group in groups],
                stocks=[_stock_dto(stock) for stock in stocks],
            )


def _ensure_default_group(session) -> WatchlistGroup:
    group = _group_by_name(session, DEFAULT_GROUP_NAME)
    if group is not None:
        group.is_default = True
        return group
    group = WatchlistGroup(name=DEFAULT_GROUP_NAME, is_default=True, sort_order=0)
    session.add(group)
    session.flush()
    return group


def _group_by_name(session, name: str) -> WatchlistGroup | None:
    return session.execute(select(WatchlistGroup).where(WatchlistGroup.name == name)).scalar_one_or_none()


def _groups_by_ids(session, group_ids: list[int]) -> list[WatchlistGroup]:
    groups = session.execute(
        select(WatchlistGroup)
        .where(WatchlistGroup.id.in_(group_ids))
        .order_by(WatchlistGroup.sort_order, WatchlistGroup.id)
    ).scalars().all()
    if len(groups) != len(set(group_ids)):
        raise ValueError("分组不存在")
    return list(groups)


def _group_dto(group: WatchlistGroup) -> WatchlistPoolGroupDTO:
    return WatchlistPoolGroupDTO(
        id=group.id,
        name=group.name,
        is_default=group.is_default,
        sort_order=group.sort_order,
    )


def _stock_dto(stock: WatchlistStock) -> WatchlistPoolStockDTO:
    return WatchlistPoolStockDTO(
        id=stock.id,
        symbol=stock.symbol,
        code=stock.code,
        exchange=stock.exchange,
        name=stock.name,
        note=stock.note,
        status=stock.status,
        groups=[_group_dto(group) for group in sorted(stock.groups, key=lambda item: (item.sort_order, item.id))],
        tags=list(stock.tags or []),
        observation_plan=WatchlistObservationPlanDTO.model_validate(_clean_observation_plan(stock.observation_plan)),
    )


def _normalize_symbol(symbol: str) -> dict[str, str]:
    raw = symbol.strip().upper()
    if "." in raw:
        code, exchange = raw.split(".", 1)
    elif raw.startswith(("SH", "SZ", "BJ")):
        exchange = raw[:2]
        code = raw[2:]
    else:
        code = raw
        exchange = _infer_exchange(code)
    if exchange not in {"SH", "SZ", "BJ"} or len(code) != 6 or not code.isdigit():
        raise ValueError("无法识别股票代码")
    return {"symbol": f"{code}.{exchange}", "code": code, "exchange": exchange}


def _clean_group_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("分组名不能为空")
    return cleaned


def _clean_status(status: str) -> str:
    cleaned = status.strip()
    if cleaned not in VALID_STOCK_STATUSES:
        raise ValueError("状态只能是观察中或持有中")
    return cleaned


def _clean_tags(tags: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        cleaned = str(tag).strip()
        if cleaned and cleaned not in seen:
            output.append(cleaned)
            seen.add(cleaned)
    return output


def _clean_observation_plan(plan: dict[str, object] | None) -> dict[str, str]:
    source = plan if isinstance(plan, dict) else {}
    return {field: str(source.get(field) or "").strip() for field in OBSERVATION_PLAN_FIELDS}
```

- [ ] **Step 5: Upsert durable pool during imports**

In `apps/api/app/watchlist/service.py`, import `WatchlistPoolService` and call it after saving the import snapshot:

```python
from app.watchlist.pool_service import WatchlistPoolService
```

Inside `import_text`, after the `with session_scope(...)` block that saves `WatchlistImport`, add:

```python
pool_service = WatchlistPoolService(self.engine)
for item in parsed.items:
    pool_service.add_stock(symbol=item.symbol, name=item.name)
```

- [ ] **Step 6: Run durable-pool tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_pool.py tests/test_watchlist_api.py -q
```

Expected: PASS.

---

### Task 2: Alert Event Model and Persistence

**Files:**

- Modify: `apps/api/app/db/models.py`
- Test: `apps/api/tests/test_watchlist_alerts.py`

- [ ] **Step 1: Write failing alert-event persistence tests**

Create `apps/api/tests/test_watchlist_alerts.py`:

```python
from datetime import UTC, datetime

from app.db.models import WatchlistAlertEvent
from app.db.session import create_sqlite_engine, init_db, session_scope


def test_watchlist_alert_event_model_persists_payload(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    init_db(engine)
    seen_at = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)

    with session_scope(engine) as session:
        session.add(
            WatchlistAlertEvent(
                stock_id=1,
                symbol="600519.SH",
                name="贵州茅台",
                event_type="risk",
                severity="high",
                status="active",
                trigger_key="600519.SH:risk:ma_break",
                payload_hash="hash-1",
                trigger_reason="跌破MA5",
                ai_comment="跌破MA5，先处理风险",
                rule_snapshot={"rule_id": "ma_break"},
                market_snapshot={"pct_change": -5.1},
                source_status={"tickflow": "ready"},
                notification_status={"sent": False},
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
        )

    with session_scope(engine) as session:
        row = session.query(WatchlistAlertEvent).one()
        assert row.symbol == "600519.SH"
        assert row.event_type == "risk"
        assert row.severity == "high"
        assert row.trigger_key == "600519.SH:risk:ma_break"
        assert row.rule_snapshot["rule_id"] == "ma_break"
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_alerts.py -q
```

Expected: FAIL because `WatchlistAlertEvent` is missing.

- [ ] **Step 3: Add the alert-event model**

In `apps/api/app/db/models.py`, add:

```python
class WatchlistAlertEvent(Base):
    __tablename__ = "watchlist_alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="active")
    trigger_key: Mapped[str] = mapped_column(String(128), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    trigger_reason: Mapped[str] = mapped_column(String(512))
    ai_comment: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    rule_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    market_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_status: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notification_status: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    muted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
```

- [ ] **Step 4: Run persistence tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_alerts.py -q
```

Expected: PASS.

---

### Task 3: TickFlow Health, Alert Settings, and Notification Settings

**Files:**

- Modify: `apps/api/app/config.py`
- Create: `apps/api/app/services/tickflow_health.py`
- Create: `apps/api/app/services/notification.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_tickflow_health.py`
- Test: `apps/api/tests/test_notifications.py`

- [ ] **Step 1: Write health and notification tests**

Create `apps/api/tests/test_tickflow_health.py`:

```python
from app.services.tickflow_health import check_tickflow_health


def test_tickflow_health_reports_missing_key():
    result = check_tickflow_health(api_key="", base_url="https://api.tickflow.org", timeout_seconds=1)
    assert result["configured"] is False
    assert result["status"] == "disabled"
    assert result["minute_kline"] == "missing_key"
    assert result["last_error"] == "TICKFLOW_API_KEY 未配置"
```

Create `apps/api/tests/test_notifications.py`:

```python
from app.services.notification import NotificationMessage, NotificationService, WeComNotifier


class FakeResponse:
    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self) -> None:
        self.payloads = []

    def post(self, url, json, timeout):
        self.payloads.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()


def test_wecom_notifier_sends_markdown_payload():
    http_client = FakeHttpClient()
    notifier = WeComNotifier("https://example.com/webhook", http_client=http_client)
    service = NotificationService([notifier])

    result = service.send_all(NotificationMessage(title="高危风险", body="贵州茅台触发跌破MA5"))

    assert result[0].status == "sent"
    assert http_client.payloads[0]["json"]["msgtype"] == "markdown"
    assert "贵州茅台触发跌破MA5" in http_client.payloads[0]["json"]["markdown"]["content"]
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_tickflow_health.py tests/test_notifications.py -q
```

Expected: FAIL because the modules are missing.

- [ ] **Step 3: Add alert settings**

Add these fields to `apps/api/app/config.py`:

```python
watchlist_alert_schedule_enabled: bool = False
watchlist_alert_morning_time: str = "10:00"
watchlist_alert_afternoon_time: str = "14:30"
watchlist_alert_review_time: str = "19:30"
watchlist_alert_timezone: str = "Asia/Shanghai"
watchlist_alert_daily_limit: int = 5
watchlist_alert_review_limit: int = 10
watchlist_alert_stale_days: int = 4
watchlist_alert_muted_days: int = 3
watchlist_alert_opportunity_min_score: int = 70
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

- [ ] **Step 4: Add TickFlow health service**

Create `apps/api/app/services/tickflow_health.py`:

```python
from pydantic import BaseModel


class TickFlowHealth(BaseModel):
    configured: bool
    status: str
    realtime_quotes: str
    daily_kline: str
    minute_kline: str
    latency_ms: int | None
    last_error: str | None
    fallback_source: str | None


def check_tickflow_health(api_key: str, base_url: str, timeout_seconds: float) -> dict[str, object]:
    if not api_key:
        return TickFlowHealth(
            configured=False,
            status="disabled",
            realtime_quotes="missing_key",
            daily_kline="missing_key",
            minute_kline="missing_key",
            latency_ms=None,
            last_error="TICKFLOW_API_KEY 未配置",
            fallback_source=None,
        ).model_dump(mode="json")
    return TickFlowHealth(
        configured=True,
        status="ready",
        realtime_quotes="not_checked",
        daily_kline="not_checked",
        minute_kline="not_checked",
        latency_ms=None,
        last_error=None,
        fallback_source=None,
    ).model_dump(mode="json")
```

- [ ] **Step 5: Add notification service**

Create `apps/api/app/services/notification.py` with the WeCom notifier and `NotificationService` protocol used by the test. Include Feishu, Telegram, and email adapters after WeCom using the same `NotificationMessage` / `NotificationResult` shapes.

- [ ] **Step 6: Add config and health endpoints**

In `apps/api/app/main.py`, add:

```python
@app.get("/api/tickflow/health")
def get_tickflow_health() -> dict[str, object]:
    settings = get_settings()
    return check_tickflow_health(
        api_key=settings.tickflow_api_key,
        base_url=settings.tickflow_base_url,
        timeout_seconds=settings.provider_timeout_seconds,
    )
```

- [ ] **Step 7: Run health and notification tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_tickflow_health.py tests/test_notifications.py -q
```

Expected: PASS.

---

### Task 4: Alert Rule Engine, Dedupe, and Write-Back

**Files:**

- Create: `apps/api/app/services/watchlist_alerts.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_watchlist_alerts.py`

- [ ] **Step 1: Extend alert tests with deterministic rule cases**

Append to `apps/api/tests/test_watchlist_alerts.py`:

```python
from datetime import UTC, datetime

from app.services.watchlist_alerts import WatchlistAlertInput, build_watchlist_alert_events


def _input(symbol="600519.SH", status="持有中", pct_change=-5.2):
    return WatchlistAlertInput(
        stock_id=1,
        symbol=symbol,
        name="贵州茅台",
        status=status,
        groups=["自选"],
        tags=[],
        observation_plan={
            "entry_reason": "趋势观察",
            "planned_buy_price": "回踩MA10",
            "invalid_condition": "跌破MA5",
            "themes": "白酒",
            "last_review_conclusion": "",
            "today_risk_hint": "",
        },
        quote={
            "last_price": 100.0,
            "pct_change": pct_change,
            "turnover_rate": 8.0,
            "capital_strength": "",
        },
        metrics={
            "close": 100.0,
            "ma5": 105.0,
            "ma10": 98.0,
            "ma20": 95.0,
            "volume_ratio_5d": 1.2,
            "is_200d_high": False,
            "sector_strength_score": 0,
            "sector_limit_up_count": 0,
        },
        risk_signals=[],
    )


def test_alert_engine_creates_high_risk_for_holding_ma_break():
    events = build_watchlist_alert_events(
        items=[_input()],
        trade_date="2026-06-15",
        mode="intraday_morning",
        source_status={"tickflow": "ready"},
        now=datetime(2026, 6, 15, 10, 0, tzinfo=UTC),
    )
    assert [(event.event_type, event.severity) for event in events] == [("risk", "high")]
    assert events[0].trigger_key == "600519.SH:risk:plan_invalid_or_ma_break"
    assert "跌破MA5" in events[0].trigger_reason


def test_alert_engine_requires_momentum_plus_volume_for_opportunity():
    item = _input(status="观察中", pct_change=2.0)
    item.quote["pct_change"] = 2.0
    item.metrics["close"] = 106.0
    item.metrics["ma5"] = 105.0
    item.metrics["volume_ratio_5d"] = 1.0
    item.metrics["sector_strength_score"] = 0

    events = build_watchlist_alert_events(
        items=[item],
        trade_date="2026-06-15",
        mode="daily_review",
        source_status={"tickflow": "ready"},
        now=datetime(2026, 6, 15, 19, 30, tzinfo=UTC),
    )

    assert [event.event_type for event in events] == []


def test_alert_engine_creates_opportunity_for_momentum_volume_resonance():
    item = _input(status="观察中", pct_change=4.0)
    item.quote["pct_change"] = 4.0
    item.metrics["close"] = 108.0
    item.metrics["ma5"] = 105.0
    item.metrics["volume_ratio_5d"] = 2.1

    events = build_watchlist_alert_events(
        items=[item],
        trade_date="2026-06-15",
        mode="daily_review",
        source_status={"tickflow": "ready"},
        now=datetime(2026, 6, 15, 19, 30, tzinfo=UTC),
    )

    assert [(event.event_type, event.severity) for event in events] == [("opportunity", "medium")]
    assert events[0].trigger_key == "600519.SH:opportunity:momentum_volume"
```

- [ ] **Step 2: Run failing rule tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_alerts.py -q
```

Expected: FAIL because `WatchlistAlertInput` and `build_watchlist_alert_events` are missing.

- [ ] **Step 3: Implement rule DTOs and pure rule function**

Create `apps/api/app/services/watchlist_alerts.py`:

```python
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json


@dataclass
class WatchlistAlertInput:
    stock_id: int | None
    symbol: str
    name: str | None
    status: str
    groups: list[str]
    tags: list[str]
    observation_plan: dict[str, str]
    quote: dict[str, object]
    metrics: dict[str, object]
    risk_signals: list[dict[str, object]]


@dataclass(frozen=True)
class WatchlistAlertEventDTO:
    stock_id: int | None
    symbol: str
    name: str | None
    event_type: str
    severity: str
    trigger_key: str
    payload_hash: str
    trigger_reason: str
    rule_snapshot: dict[str, object]
    market_snapshot: dict[str, object]
    source_status: dict[str, object]
    first_seen_at: datetime
    last_seen_at: datetime


def build_watchlist_alert_events(
    items: list[WatchlistAlertInput],
    trade_date: str,
    mode: str,
    source_status: dict[str, object],
    now: datetime,
) -> list[WatchlistAlertEventDTO]:
    events: list[WatchlistAlertEventDTO] = []
    for item in items:
        event = _risk_event(item, source_status, now)
        if event is not None:
            events.append(event)
            continue
        event = _opportunity_event(item, source_status, now)
        if event is not None:
            events.append(event)
    return events


def _risk_event(
    item: WatchlistAlertInput,
    source_status: dict[str, object],
    now: datetime,
) -> WatchlistAlertEventDTO | None:
    pct_change = _float(item.quote.get("pct_change"))
    close = _float(item.metrics.get("close"))
    ma5 = _float(item.metrics.get("ma5"))
    invalid_condition = item.observation_plan.get("invalid_condition", "")
    broke_ma5 = close is not None and ma5 is not None and close < ma5
    high_drop = pct_change is not None and pct_change <= -5
    serious = any(signal.get("type") == "serious_abnormal" for signal in item.risk_signals)
    negative = any(signal.get("type") == "negative_news" for signal in item.risk_signals)
    if item.status != "持有中" and not serious and not negative:
        return None
    if not (broke_ma5 or high_drop or serious or negative):
        return None
    reason = invalid_condition or "跌破MA5"
    snapshot = {"pct_change": pct_change, "close": close, "ma5": ma5, "mode": "risk"}
    return _event(
        item=item,
        event_type="risk",
        severity="high",
        rule_id="plan_invalid_or_ma_break",
        reason=reason,
        market_snapshot=snapshot,
        source_status=source_status,
        now=now,
    )


def _opportunity_event(
    item: WatchlistAlertInput,
    source_status: dict[str, object],
    now: datetime,
) -> WatchlistAlertEventDTO | None:
    close = _float(item.metrics.get("close"))
    ma5 = _float(item.metrics.get("ma5"))
    volume_ratio = _float(item.metrics.get("volume_ratio_5d")) or 0
    sector_strength = _float(item.metrics.get("sector_strength_score")) or 0
    above_ma5 = close is not None and ma5 is not None and close > ma5
    volume_ok = volume_ratio >= 1.8
    sector_ok = sector_strength >= 20
    if not above_ma5 or not (volume_ok or sector_ok):
        return None
    snapshot = {
        "close": close,
        "ma5": ma5,
        "volume_ratio_5d": volume_ratio,
        "sector_strength_score": sector_strength,
        "mode": "opportunity",
    }
    return _event(
        item=item,
        event_type="opportunity",
        severity="medium",
        rule_id="momentum_volume" if volume_ok else "momentum_sector",
        reason="动量与量能共振" if volume_ok else "动量与板块共振",
        market_snapshot=snapshot,
        source_status=source_status,
        now=now,
    )


def _event(
    item: WatchlistAlertInput,
    event_type: str,
    severity: str,
    rule_id: str,
    reason: str,
    market_snapshot: dict[str, object],
    source_status: dict[str, object],
    now: datetime,
) -> WatchlistAlertEventDTO:
    trigger_key = f"{item.symbol}:{event_type}:{rule_id}"
    payload = {"trigger_key": trigger_key, "market_snapshot": market_snapshot}
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return WatchlistAlertEventDTO(
        stock_id=item.stock_id,
        symbol=item.symbol,
        name=item.name,
        event_type=event_type,
        severity=severity,
        trigger_key=trigger_key,
        payload_hash=payload_hash,
        trigger_reason=reason,
        rule_snapshot={"rule_id": rule_id},
        market_snapshot=market_snapshot,
        source_status=source_status,
        first_seen_at=now,
        last_seen_at=now,
    )


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Add persistence helpers and API listing**

In the same service file, add repository helpers that convert `WatchlistAlertEventDTO` into `WatchlistAlertEvent` rows, update `last_seen_at` for same `trigger_key + payload_hash`, and set `status` to `active`. Wire `GET /api/watchlist-alerts` in `apps/api/app/main.py` to return stored rows sorted by `last_seen_at DESC`.

- [ ] **Step 5: Run rule-engine tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_alerts.py -q
```

Expected: PASS.

---

### Task 5: Alert Schedule and API Endpoints

**Files:**

- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/app/services/watchlist_alert_schedule.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_watchlist_alert_schedule.py`
- Test: `apps/api/tests/test_watchlist_api.py`

- [ ] **Step 1: Write schedule tests**

Create `apps/api/tests/test_watchlist_alert_schedule.py`:

```python
from datetime import UTC, datetime

from app.db.session import create_sqlite_engine, init_db
from app.services.watchlist_alert_schedule import (
    WatchlistAlertScheduleUpdate,
    get_watchlist_alert_schedule_status,
    run_due_watchlist_alert_schedule,
    update_watchlist_alert_schedule_status,
)


class SettingsStub:
    watchlist_alert_schedule_enabled = True
    watchlist_alert_morning_time = "10:00"
    watchlist_alert_afternoon_time = "14:30"
    watchlist_alert_review_time = "19:30"
    watchlist_alert_timezone = "Asia/Shanghai"


def test_schedule_skips_before_due_time(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'schedule.db'}")
    init_db(engine)
    calls = []

    result = run_due_watchlist_alert_schedule(
        engine=engine,
        settings=SettingsStub(),
        run_scan=lambda mode, trade_date: calls.append((mode, trade_date)) or {"status": "completed"},
        now=datetime(2026, 6, 15, 1, 0, tzinfo=UTC),
    )

    assert calls == []
    assert result["enabled"] is True


def test_schedule_runs_morning_scan_when_due(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'schedule.db'}")
    init_db(engine)
    calls = []

    result = run_due_watchlist_alert_schedule(
        engine=engine,
        settings=SettingsStub(),
        run_scan=lambda mode, trade_date: calls.append((mode, trade_date)) or {"status": "completed"},
        now=datetime(2026, 6, 15, 2, 1, tzinfo=UTC),
    )

    assert calls == [("intraday_morning", "2026-06-15")]
    assert result["last_result"]["mode"] == "intraday_morning"
    assert result["last_result"]["status"] == "completed"
```

- [ ] **Step 2: Run failing schedule tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_alert_schedule.py -q
```

Expected: FAIL because the schedule model and service are missing.

- [ ] **Step 3: Add schedule model**

In `apps/api/app/db/models.py`, add:

```python
class WatchlistAlertScheduleConfig(Base):
    __tablename__ = "watchlist_alert_schedule_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    morning_time: Mapped[str] = mapped_column(String(5), default="10:00")
    afternoon_time: Mapped[str] = mapped_column(String(5), default="14:30")
    review_time: Mapped[str] = mapped_column(String(5), default="19:30")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
```

- [ ] **Step 4: Implement schedule service**

Create `apps/api/app/services/watchlist_alert_schedule.py` with:

```python
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import Engine, select

from app.db.models import WatchlistAlertScheduleConfig
from app.db.session import session_scope


class WatchlistAlertScheduleUpdate(BaseModel):
    enabled: bool
    morning_time: str = "10:00"
    afternoon_time: str = "14:30"
    review_time: str = "19:30"
    timezone: str = "Asia/Shanghai"


def get_watchlist_alert_schedule_status(engine: Engine, settings: object) -> dict[str, object]:
    with session_scope(engine) as session:
        config = _get_or_create(session, settings)
        session.flush()
        return _payload(config)


def update_watchlist_alert_schedule_status(
    engine: Engine,
    settings: object,
    update: WatchlistAlertScheduleUpdate,
) -> dict[str, object]:
    _parse_hhmm(update.morning_time)
    _parse_hhmm(update.afternoon_time)
    _parse_hhmm(update.review_time)
    ZoneInfo(update.timezone)
    with session_scope(engine) as session:
        config = _get_or_create(session, settings)
        config.enabled = update.enabled
        config.morning_time = update.morning_time
        config.afternoon_time = update.afternoon_time
        config.review_time = update.review_time
        config.timezone = update.timezone
        session.flush()
        return _payload(config)


def run_due_watchlist_alert_schedule(engine: Engine, settings: object, run_scan, now: datetime | None = None) -> dict[str, object]:
    current = now or datetime.now(UTC)
    with session_scope(engine) as session:
        config = _get_or_create(session, settings)
        if not config.enabled:
            return _payload(config)
        mode = _due_mode(config, current)
        if mode is None:
            return _payload(config)
        trade_date = current.astimezone(ZoneInfo(config.timezone)).date().isoformat()

    try:
        result = run_scan(mode, trade_date)
        last_result = {"status": str(result.get("status", "completed")), "mode": mode, "trade_date": trade_date}
    except Exception as exc:
        last_result = {"status": "failed", "mode": mode, "trade_date": trade_date, "reason": exc.__class__.__name__}

    with session_scope(engine) as session:
        config = _get_or_create(session, settings)
        config.last_run_at = current
        config.last_result = last_result
        session.flush()
        return _payload(config)


def _get_or_create(session, settings: object) -> WatchlistAlertScheduleConfig:
    config = session.execute(select(WatchlistAlertScheduleConfig).order_by(WatchlistAlertScheduleConfig.id)).scalars().first()
    if config is not None:
        return config
    config = WatchlistAlertScheduleConfig(
        enabled=bool(getattr(settings, "watchlist_alert_schedule_enabled", False)),
        morning_time=str(getattr(settings, "watchlist_alert_morning_time", "10:00")),
        afternoon_time=str(getattr(settings, "watchlist_alert_afternoon_time", "14:30")),
        review_time=str(getattr(settings, "watchlist_alert_review_time", "19:30")),
        timezone=str(getattr(settings, "watchlist_alert_timezone", "Asia/Shanghai")),
    )
    session.add(config)
    return config


def _payload(config: WatchlistAlertScheduleConfig) -> dict[str, object]:
    return {
        "enabled": config.enabled,
        "morning_time": config.morning_time,
        "afternoon_time": config.afternoon_time,
        "review_time": config.review_time,
        "timezone": config.timezone,
        "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
        "last_result": config.last_result,
    }


def _due_mode(config: WatchlistAlertScheduleConfig, now: datetime) -> str | None:
    tz = ZoneInfo(config.timezone)
    local = now.astimezone(tz)
    if config.last_run_at is not None and config.last_run_at.astimezone(tz).date() == local.date():
        last_mode = (config.last_result or {}).get("mode")
    else:
        last_mode = None
    due = [
        ("intraday_morning", config.morning_time),
        ("intraday_afternoon", config.afternoon_time),
        ("daily_review", config.review_time),
    ]
    for mode, value in due:
        if last_mode == mode:
            continue
        hour, minute = _parse_hhmm(value)
        scheduled = datetime.combine(local.date(), time(hour=hour, minute=minute), tzinfo=tz)
        if local >= scheduled:
            return mode
    return None


def _parse_hhmm(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("time must use HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("time must use HH:MM")
    return hour, minute
```

- [ ] **Step 5: Wire API endpoints**

Add request models and endpoints in `apps/api/app/main.py`:

```python
class RunWatchlistAlertRequest(BaseModel):
    trade_date: str
    mode: str = "daily_review"


class WatchlistAlertScheduleRequest(BaseModel):
    enabled: bool
    morning_time: str = "10:00"
    afternoon_time: str = "14:30"
    review_time: str = "19:30"
    timezone: str = "Asia/Shanghai"
```

Endpoints:

```python
@app.post("/api/watchlist-alerts/run")
def run_watchlist_alerts(request: RunWatchlistAlertRequest) -> dict[str, object]:
    return _run_watchlist_alert_scan(request.mode, request.trade_date)


@app.get("/api/watchlist-alert-schedule/status")
def get_watchlist_alert_schedule() -> dict[str, object]:
    return get_watchlist_alert_schedule_status(app.state.engine, get_settings())


@app.put("/api/watchlist-alert-schedule/status")
def update_watchlist_alert_schedule(request: WatchlistAlertScheduleRequest) -> dict[str, object]:
    return update_watchlist_alert_schedule_status(
        app.state.engine,
        get_settings(),
        WatchlistAlertScheduleUpdate.model_validate(request.model_dump()),
    )
```

- [ ] **Step 6: Run schedule and API tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_alert_schedule.py tests/test_watchlist_api.py -q
```

Expected: PASS.

---

### Task 6: AI Commentary and Alert Dispatch

**Files:**

- Create: `apps/api/app/services/watchlist_ai_review.py`
- Modify: `apps/api/app/services/watchlist_alerts.py`
- Modify: `apps/api/app/services/notification.py`
- Test: `apps/api/tests/test_watchlist_alerts.py`
- Test: `apps/api/tests/test_notifications.py`

- [ ] **Step 1: Add AI fallback commentary test**

Append to `apps/api/tests/test_watchlist_alerts.py`:

```python
from app.services.watchlist_ai_review import RuleWatchlistAIReviewProvider


def test_rule_ai_commentary_summarizes_alert_events():
    provider = RuleWatchlistAIReviewProvider()
    result = provider.generate_alert_commentary(
        {
            "events": [
                {
                    "symbol": "600519.SH",
                    "name": "贵州茅台",
                    "event_type": "risk",
                    "trigger_reason": "跌破MA5",
                }
            ]
        }
    )

    assert result["summary"] == "本次触发 1 条自选股提醒。"
    assert result["comments"]["600519.SH"].startswith("贵州茅台触发risk")
```

- [ ] **Step 2: Run failing AI commentary test**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_alerts.py::test_rule_ai_commentary_summarizes_alert_events -q
```

Expected: FAIL because `RuleWatchlistAIReviewProvider` is missing.

- [ ] **Step 3: Implement rule fallback AI provider**

Create `apps/api/app/services/watchlist_ai_review.py`:

```python
from pydantic import BaseModel


class WatchlistAIReview(BaseModel):
    summary: str
    comments: dict[str, str]


class RuleWatchlistAIReviewProvider:
    provider_name = "rule"
    model_name = "watchlist-alert-rule-v1"

    def generate_alert_commentary(self, seed: dict[str, object]) -> dict[str, object]:
        raw_events = seed.get("events")
        events = raw_events if isinstance(raw_events, list) else []
        comments: dict[str, str] = {}
        for event in events:
            if not isinstance(event, dict):
                continue
            symbol = str(event.get("symbol") or "")
            name = str(event.get("name") or symbol)
            event_type = str(event.get("event_type") or "alert")
            reason = str(event.get("trigger_reason") or "规则触发")
            if symbol:
                comments[symbol] = f"{name}触发{event_type}提醒：{reason}。"
        return WatchlistAIReview(
            summary=f"本次触发 {len(comments)} 条自选股提醒。",
            comments=comments,
        ).model_dump(mode="json")
```

- [ ] **Step 4: Add dispatch helper**

In `apps/api/app/services/watchlist_alerts.py`, add a dispatcher that:

- takes stored active events,
- skips `acknowledged` and muted events,
- sends high-risk single messages first,
- merges opportunity events into a summary,
- updates `notification_status` and `sent_at`.

Use `NotificationService.send_all(NotificationMessage(title=title, body=body))` from Task 3, where `title` is either `高危风险提醒` or `自选股机会提醒`, and `body` is the formatted event summary generated by the dispatcher.

- [ ] **Step 5: Run alert and notification tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_watchlist_alerts.py tests/test_notifications.py -q
```

Expected: PASS.

---

### Task 7: Frontend API Types and Client

**Files:**

- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Test: `apps/web/lib/watchlistAlertCenter.test.ts`
- Test: `apps/web/lib/watchlistSettingsPanel.test.ts`

- [ ] **Step 1: Write API type tests**

Create `apps/web/lib/watchlistAlertCenter.test.ts`:

```typescript
import assert from "node:assert/strict";
import test from "node:test";
import type { WatchlistAlertEvent } from "./types";

test("watchlist alert event type supports risk payload", () => {
  const event: WatchlistAlertEvent = {
    id: 1,
    symbol: "600519.SH",
    name: "贵州茅台",
    event_type: "risk",
    severity: "high",
    status: "active",
    trigger_reason: "跌破MA5",
    ai_comment: "跌破MA5，先处理风险",
    source_status: { tickflow: "ready" },
    market_snapshot: { pct_change: -5.1 },
    rule_snapshot: { rule_id: "ma_break" },
    notification_status: { sent: false },
    first_seen_at: "2026-06-15T02:00:00Z",
    last_seen_at: "2026-06-15T02:00:00Z",
  };
  assert.equal(event.severity, "high");
});
```

Create `apps/web/lib/watchlistSettingsPanel.test.ts`:

```typescript
import assert from "node:assert/strict";
import test from "node:test";
import type { WatchlistAlertScheduleStatus } from "./types";

test("watchlist alert schedule status includes intraday and review times", () => {
  const status: WatchlistAlertScheduleStatus = {
    enabled: true,
    morning_time: "10:00",
    afternoon_time: "14:30",
    review_time: "19:30",
    timezone: "Asia/Shanghai",
    last_run_at: null,
    last_result: null,
  };
  assert.equal(status.review_time, "19:30");
});
```

- [ ] **Step 2: Run failing frontend type tests**

Run:

```bash
cd apps/web && npm test
```

Expected: FAIL because DTO types are missing.

- [ ] **Step 3: Add frontend DTOs**

In `apps/web/lib/types.ts`, add:

```typescript
export type WatchlistAlertEvent = {
  id: number;
  symbol: string;
  name: string | null;
  event_type: "risk" | "opportunity" | "plan" | "intraday" | "stale_review";
  severity: "high" | "medium" | "low";
  status: "active" | "sent" | "acknowledged" | "muted" | "resolved";
  trigger_reason: string;
  ai_comment: string | null;
  source_status: Record<string, unknown>;
  market_snapshot: Record<string, unknown>;
  rule_snapshot: Record<string, unknown>;
  notification_status: Record<string, unknown>;
  first_seen_at: string;
  last_seen_at: string;
};

export type WatchlistAlertListResponse = {
  items: WatchlistAlertEvent[];
};

export type WatchlistAlertScheduleStatus = {
  enabled: boolean;
  morning_time: string;
  afternoon_time: string;
  review_time: string;
  timezone: string;
  last_run_at: string | null;
  last_result: Record<string, unknown> | null;
};

export type TickFlowHealthStatus = {
  configured: boolean;
  status: string;
  realtime_quotes: string;
  daily_kline: string;
  minute_kline: string;
  latency_ms: number | null;
  last_error: string | null;
  fallback_source: string | null;
};
```

- [ ] **Step 4: Add frontend API methods**

In `apps/web/lib/api.ts`, add:

```typescript
export async function listWatchlistAlerts(): Promise<WatchlistAlertListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-alerts`);
  if (!response.ok) {
    throw new Error(`读取提醒列表失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistAlertListResponse>;
}

export async function runWatchlistAlerts(mode: string, tradeDate: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-alerts/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, trade_date: tradeDate }),
  });
  if (!response.ok) {
    throw new Error(`运行提醒失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<Record<string, unknown>>;
}

export async function acknowledgeWatchlistAlert(alertId: number): Promise<WatchlistAlertEvent> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-alerts/${alertId}/ack`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`标记提醒失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistAlertEvent>;
}

export async function getWatchlistAlertSchedule(): Promise<WatchlistAlertScheduleStatus> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-alert-schedule/status`);
  if (!response.ok) {
    throw new Error(`读取提醒计划失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistAlertScheduleStatus>;
}

export async function getTickFlowHealth(): Promise<TickFlowHealthStatus> {
  const response = await fetch(`${API_BASE_URL}/api/tickflow/health`);
  if (!response.ok) {
    throw new Error(`读取TickFlow健康状态失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<TickFlowHealthStatus>;
}
```

- [ ] **Step 5: Run frontend type tests**

Run:

```bash
cd apps/web && npm test
```

Expected: PASS for the newly added type tests.

---

### Task 8: Frontend Pages and Navigation

**Files:**

- Modify: `apps/web/components/AdminShell.tsx`
- Modify: `apps/web/app/page.tsx`
- Create: `apps/web/app/watchlist/page.tsx`
- Create: `apps/web/app/watchlist-alerts/page.tsx`
- Create: `apps/web/app/settings/page.tsx`
- Test: `apps/web/lib/watchlistPoolPage.test.ts`
- Test: `apps/web/lib/watchlistAlertCenter.test.ts`
- Test: `apps/web/lib/watchlistSettingsPanel.test.ts`

- [ ] **Step 1: Write route/nav render tests**

Add pure helper tests for visible nav labels and status text. Use exported arrays/helpers instead of browser tests so they fit the existing Node test setup.

Expected nav labels:

```typescript
["首页", "自选股", "提醒中心", "设置"]
```

- [ ] **Step 2: Refactor `AdminShell` navigation**

In `apps/web/components/AdminShell.tsx`, replace the current hash-only nav with route-aware links:

```typescript
const navItems = [
  { label: "首页", hint: "Home", href: "/" },
  { label: "自选股", hint: "Watchlist", href: "/watchlist" },
  { label: "提醒中心", hint: "Alerts", href: "/watchlist-alerts" },
  { label: "设置", hint: "Settings", href: "/settings" },
];
```

Use `usePathname()` to highlight the active item.

- [ ] **Step 3: Build watchlist page**

Create `apps/web/app/watchlist/page.tsx` with:

- stock add form,
- group list,
- table with symbol/name/groups/tags/status,
- observation plan fields,
- recent alert summary populated from `/api/watchlist-alerts`, showing the newest event type, severity, trigger reason, and last seen time for each visible stock.

- [ ] **Step 4: Build alert center**

Create `apps/web/app/watchlist-alerts/page.tsx` with:

- filter buttons: 全部、高危、机会、计划、到期复看、已处理,
- event list,
- right-side detail area,
- buttons for 已处理、暂不提醒、加入复盘结论.

- [ ] **Step 5: Build settings page**

Create `apps/web/app/settings/page.tsx` with:

- TickFlow health card,
- schedule fields for 10:00 / 14:30 / 19:30,
- daily reminder limit,
- stale review cycle,
- notification channel status for WeCom, Feishu, Telegram, and email, showing `已配置` when the corresponding setting exists and `未配置` when it is empty.

- [ ] **Step 6: Run frontend tests**

Run:

```bash
cd apps/web && npm test
```

Expected: PASS.

---

### Task 9: Full Verification and Scope Guard

**Files:**

- Modify: `apps/api/tests/test_watchlist_api.py`
- Modify: `apps/web/lib/homePageHydration.test.ts`
- Update: `docs/superpowers/specs/2026-06-15-ai-watchlist-alert-engine-design.md` only if route or endpoint names changed during implementation.

- [ ] **Step 1: Add an API flow test**

In `apps/api/tests/test_watchlist_api.py`, add a test that:

- imports two stocks,
- confirms durable pool has two stocks,
- manually runs `/api/watchlist-alerts/run`,
- reads `/api/watchlist-alerts`,
- marks one event acknowledged when an event is returned.

- [ ] **Step 2: Run full test suites**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest -q
cd ../web && npm test
```

Expected: both pass.

- [ ] **Step 3: Scope guard review**

Before marking complete, inspect the changed files and confirm:

- no continuous polling loop shorter than 60 seconds,
- no automatic trade or position code,
- no task workflow tables beyond alert events and schedule config,
- notification copy avoids “买入”, “卖出”, “必须买”, “必须卖”.

Run:

```bash
rg -n "买入|卖出|必须买|必须卖|position|trade|order|websocket|while True" apps/api/app apps/web/app apps/web/components
```

Expected: no actionable violation of the first-version scope.
