# Runtime Data Source Options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SQLite-backed runtime data-source selection to the admin UI and wire a-stock-data enhancement providers into the report generation path.

**Architecture:** Add a small runtime provider config service backed by the existing SQLite database, then feed that config into provider factory creation for FastAPI report endpoints. Provider metadata lives in a backend registry used by both API option responses and config status. The frontend replaces the read-only source status panel with a controlled configuration form that persists choices through the new API.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic Settings, httpx, pytest, Next.js 15, React 19, TypeScript, node:test.

---

## File Structure

- Create `apps/api/app/providers/runtime_config.py`: provider option registry, runtime config DTOs, DB read/write service, request validation.
- Modify `apps/api/app/db/models.py`: add `RuntimeProviderConfig` table.
- Modify `apps/api/app/providers/factory.py`: accept runtime config override and create providers from it.
- Create `apps/api/app/providers/a_stock_data.py`: a-stock-data-derived providers for 同花顺热点、东财行业排名、东财全球资讯.
- Modify `apps/api/app/main.py`: add data-source option GET/PUT endpoints, make report endpoints use runtime config, update config status.
- Modify `apps/web/lib/types.ts`: add data-source option API types and extend config status state if needed.
- Modify `apps/web/lib/api.ts`: add `getDataSourceOptions()` and `updateDataSourceOptions()`.
- Modify `apps/web/components/DataSourceStatusPanel.tsx`: convert read-only cards into form + status cards.
- Modify `apps/web/app/page.tsx`: load/save runtime source options, wire panel callbacks.
- Add/update tests in `apps/api/tests/test_runtime_provider_config.py`, `apps/api/tests/test_a_stock_data_provider.py`, `apps/api/tests/test_report_api.py`, `apps/web/lib/dataSourceStatusPanel.test.ts`.

---

### Task 1: Runtime Config Persistence

**Files:**
- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/app/providers/runtime_config.py`
- Test: `apps/api/tests/test_runtime_provider_config.py`

- [ ] **Step 1: Write failing persistence tests**

Create `apps/api/tests/test_runtime_provider_config.py`:

```python
from sqlalchemy import create_engine

from app.config import Settings
from app.db.models import Base
from app.db.session import session_scope
from app.providers.runtime_config import (
    RuntimeProviderConfigInput,
    get_runtime_provider_config,
    save_runtime_provider_config,
)


def _engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def test_runtime_config_defaults_from_settings_when_empty() -> None:
    engine = _engine()
    settings = Settings(
        market_provider="tickflow",
        news_provider="anspire",
        review_sources_enabled=True,
        thsdk_enabled=True,
        provider_fallback_enabled=False,
    )

    config = get_runtime_provider_config(engine, settings)

    assert config.market_provider == "tickflow"
    assert config.news_provider == "anspire"
    assert config.review_sources == ["ths_fupan", "eastmoney_ztfp", "thsdk"]
    assert config.fallback_enabled is False
    assert config.updated_at is None


def test_runtime_config_save_and_read_back() -> None:
    engine = _engine()
    settings = Settings()

    saved = save_runtime_provider_config(
        engine,
        RuntimeProviderConfigInput(
            market_provider="tickflow",
            news_provider="eastmoney_global",
            review_sources=["a_stock_ths_hot", "ths_fupan", "a_stock_ths_hot"],
            fallback_enabled=True,
        ),
    )
    loaded = get_runtime_provider_config(engine, settings)

    assert saved.news_provider == "eastmoney_global"
    assert loaded.market_provider == "tickflow"
    assert loaded.news_provider == "eastmoney_global"
    assert loaded.review_sources == ["a_stock_ths_hot", "ths_fupan"]
    assert loaded.fallback_enabled is True
    assert loaded.updated_at is not None


def test_runtime_config_rejects_unknown_provider() -> None:
    engine = _engine()

    try:
        save_runtime_provider_config(
            engine,
            RuntimeProviderConfigInput(
                market_provider="tickflow",
                news_provider="unknown",
                review_sources=[],
                fallback_enabled=True,
            ),
        )
    except ValueError as exc:
        assert "Unsupported NEWS_PROVIDER" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_runtime_config_replaces_singleton_row() -> None:
    engine = _engine()
    settings = Settings()

    save_runtime_provider_config(
        engine,
        RuntimeProviderConfigInput(
            market_provider="tickflow",
            news_provider="fake",
            review_sources=["ths_fupan"],
            fallback_enabled=True,
        ),
    )
    save_runtime_provider_config(
        engine,
        RuntimeProviderConfigInput(
            market_provider="fake",
            news_provider="eastmoney_global",
            review_sources=["a_stock_industry_rank"],
            fallback_enabled=False,
        ),
    )

    loaded = get_runtime_provider_config(engine, settings)
    with session_scope(engine) as session:
        rows = session.execute("select count(*) from runtime_provider_config").scalar()

    assert rows == 1
    assert loaded.market_provider == "fake"
    assert loaded.news_provider == "eastmoney_global"
    assert loaded.review_sources == ["a_stock_industry_rank"]
    assert loaded.fallback_enabled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_runtime_provider_config.py -q
```

Expected: FAIL because `app.providers.runtime_config` and `RuntimeProviderConfig` do not exist.

- [ ] **Step 3: Add DB model**

In `apps/api/app/db/models.py`, add this class after `Report`:

```python
class RuntimeProviderConfig(Base):
    __tablename__ = "runtime_provider_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_provider: Mapped[str] = mapped_column(String(64))
    news_provider: Mapped[str] = mapped_column(String(64))
    review_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    fallback_enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
```

Also add `Boolean` to the SQLAlchemy import:

```python
from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String
```

- [ ] **Step 4: Implement runtime config service**

Create `apps/api/app/providers/runtime_config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Engine, select

from app.config import Settings
from app.db.models import RuntimeProviderConfig
from app.db.session import session_scope


MarketProviderKey = Literal["tickflow", "fake"]
NewsProviderKey = Literal["anspire", "eastmoney_global", "fake"]
ReviewSourceKey = Literal[
    "ths_fupan",
    "eastmoney_ztfp",
    "thsdk",
    "a_stock_ths_hot",
    "a_stock_industry_rank",
]

MARKET_PROVIDER_KEYS = {"tickflow", "fake"}
NEWS_PROVIDER_KEYS = {"anspire", "eastmoney_global", "fake"}
REVIEW_SOURCE_KEYS = {
    "ths_fupan",
    "eastmoney_ztfp",
    "thsdk",
    "a_stock_ths_hot",
    "a_stock_industry_rank",
}


class RuntimeProviderConfigInput(BaseModel):
    market_provider: str
    news_provider: str
    review_sources: list[str]
    fallback_enabled: bool


@dataclass(frozen=True)
class RuntimeProviderConfigState:
    market_provider: str
    news_provider: str
    review_sources: list[str]
    fallback_enabled: bool
    updated_at: datetime | None = None


def get_runtime_provider_config(engine: Engine, settings: Settings) -> RuntimeProviderConfigState:
    with session_scope(engine) as session:
        row = session.scalars(
            select(RuntimeProviderConfig).order_by(RuntimeProviderConfig.id.asc())
        ).first()
        if row is None:
            return default_runtime_provider_config(settings)
        return RuntimeProviderConfigState(
            market_provider=row.market_provider,
            news_provider=row.news_provider,
            review_sources=list(row.review_sources or []),
            fallback_enabled=bool(row.fallback_enabled),
            updated_at=row.updated_at,
        )


def default_runtime_provider_config(settings: Settings) -> RuntimeProviderConfigState:
    review_sources: list[str] = []
    if settings.review_sources_enabled:
        review_sources.extend(["ths_fupan", "eastmoney_ztfp"])
    if settings.thsdk_enabled:
        review_sources.append("thsdk")
    return RuntimeProviderConfigState(
        market_provider=settings.market_provider,
        news_provider=settings.news_provider,
        review_sources=_dedupe_review_sources(review_sources),
        fallback_enabled=settings.provider_fallback_enabled,
        updated_at=None,
    )


def save_runtime_provider_config(
    engine: Engine,
    payload: RuntimeProviderConfigInput,
) -> RuntimeProviderConfigState:
    _validate_runtime_config(payload)
    review_sources = _dedupe_review_sources(payload.review_sources)
    with session_scope(engine) as session:
        existing = session.scalars(
            select(RuntimeProviderConfig).order_by(RuntimeProviderConfig.id.asc())
        ).first()
        if existing is None:
            existing = RuntimeProviderConfig(
                market_provider=payload.market_provider,
                news_provider=payload.news_provider,
                review_sources=review_sources,
                fallback_enabled=payload.fallback_enabled,
            )
            session.add(existing)
        else:
            existing.market_provider = payload.market_provider
            existing.news_provider = payload.news_provider
            existing.review_sources = review_sources
            existing.fallback_enabled = payload.fallback_enabled
        session.flush()
        return RuntimeProviderConfigState(
            market_provider=existing.market_provider,
            news_provider=existing.news_provider,
            review_sources=list(existing.review_sources or []),
            fallback_enabled=bool(existing.fallback_enabled),
            updated_at=existing.updated_at,
        )


def _validate_runtime_config(payload: RuntimeProviderConfigInput) -> None:
    if payload.market_provider not in MARKET_PROVIDER_KEYS:
        raise ValueError(f"Unsupported MARKET_PROVIDER: {payload.market_provider}")
    if payload.news_provider not in NEWS_PROVIDER_KEYS:
        raise ValueError(f"Unsupported NEWS_PROVIDER: {payload.news_provider}")
    unsupported = [source for source in payload.review_sources if source not in REVIEW_SOURCE_KEYS]
    if unsupported:
        raise ValueError(f"Unsupported REVIEW_SOURCE: {unsupported[0]}")


def _dedupe_review_sources(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
```

- [ ] **Step 5: Fix SQL text use if needed**

If SQLAlchemy rejects the raw SQL in the test, update the test import:

```python
from sqlalchemy import create_engine, text
```

And replace:

```python
rows = session.execute("select count(*) from runtime_provider_config").scalar()
```

With:

```python
rows = session.execute(text("select count(*) from runtime_provider_config")).scalar()
```

- [ ] **Step 6: Run persistence tests**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_runtime_provider_config.py -q
```

Expected: PASS.

---

### Task 2: Runtime Provider Registry and Options API

**Files:**
- Modify: `apps/api/app/providers/runtime_config.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add failing API tests**

Append to `apps/api/tests/test_report_api.py`:

```python
def test_data_source_options_api_returns_current_options(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_PROVIDER", "tickflow")
    monkeypatch.setenv("NEWS_PROVIDER", "anspire")
    monkeypatch.setenv("TICKFLOW_API_KEY", "tk_secret_should_not_leak")
    monkeypatch.setenv("ANSPIRE_API_KEY", "")
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/api/data-sources/options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current"]["market_provider"] == "tickflow"
    assert payload["current"]["news_provider"] == "anspire"
    categories = {category["key"]: category for category in payload["categories"]}
    assert categories["market_provider"]["selection"] == "single"
    assert categories["news_provider"]["selection"] == "single"
    assert categories["review_sources"]["selection"] == "multiple"
    news_options = {item["key"]: item for item in categories["news_provider"]["options"]}
    assert news_options["anspire"]["status"] == "missing_key"
    assert news_options["eastmoney_global"]["status"] == "ready"
    assert "tk_secret_should_not_leak" not in response.text


def test_data_source_options_api_saves_runtime_config(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_PROVIDER", "tickflow")
    monkeypatch.setenv("NEWS_PROVIDER", "anspire")
    get_settings.cache_clear()

    with TestClient(app) as client:
        save_response = client.put(
            "/api/data-sources/options",
            json={
                "market_provider": "tickflow",
                "news_provider": "eastmoney_global",
                "review_sources": ["a_stock_ths_hot", "a_stock_industry_rank"],
                "fallback_enabled": False,
            },
        )
        read_response = client.get("/api/data-sources/options")

    assert save_response.status_code == 200
    assert read_response.status_code == 200
    current = read_response.json()["current"]
    assert current["news_provider"] == "eastmoney_global"
    assert current["review_sources"] == ["a_stock_ths_hot", "a_stock_industry_rank"]
    assert current["fallback_enabled"] is False
    assert current["updated_at"] is not None


def test_data_source_options_api_rejects_unknown_provider() -> None:
    with TestClient(app) as client:
        response = client.put(
            "/api/data-sources/options",
            json={
                "market_provider": "tickflow",
                "news_provider": "unknown",
                "review_sources": [],
                "fallback_enabled": True,
            },
        )

    assert response.status_code == 422
    assert "Unsupported NEWS_PROVIDER" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_report_api.py::test_data_source_options_api_returns_current_options tests/test_report_api.py::test_data_source_options_api_saves_runtime_config tests/test_report_api.py::test_data_source_options_api_rejects_unknown_provider -q
```

Expected: FAIL with 404 for missing endpoint.

- [ ] **Step 3: Add option registry and response builder**

Append to `apps/api/app/providers/runtime_config.py`:

```python
@dataclass(frozen=True)
class ProviderOption:
    key: str
    category: str
    label: str
    role: str
    requires_key: bool = False
    env_key_name: str | None = None
    experimental: bool = False
    local: bool = False


PROVIDER_OPTIONS: tuple[ProviderOption, ...] = (
    ProviderOption("tickflow", "market_provider", "TickFlow", "主源 · 行情", True, "tickflow_api_key"),
    ProviderOption("fake", "market_provider", "Fake", "本地 · 行情占位", False, None, False, True),
    ProviderOption("anspire", "news_provider", "Anspire", "主源 · 新闻", True, "anspire_api_key"),
    ProviderOption("eastmoney_global", "news_provider", "东财全球资讯", "增强源 · 7x24 新闻"),
    ProviderOption("fake", "news_provider", "Fake", "本地 · 新闻占位", False, None, False, True),
    ProviderOption("ths_fupan", "review_sources", "同花顺复盘", "辅助源 · 题材复盘"),
    ProviderOption("eastmoney_ztfp", "review_sources", "东方财富涨停复盘", "辅助源 · 涨停质量"),
    ProviderOption("thsdk", "review_sources", "THSDK", "实验源 · 同花顺问财/概念", False, None, True),
    ProviderOption("a_stock_ths_hot", "review_sources", "a-stock 同花顺热点", "增强源 · 强势股归因"),
    ProviderOption("a_stock_industry_rank", "review_sources", "a-stock 东财行业排名", "增强源 · 行业轮动"),
)


def build_data_source_options_payload(
    config: RuntimeProviderConfigState,
    settings: Settings,
) -> dict[str, object]:
    return {
        "current": {
            "market_provider": config.market_provider,
            "news_provider": config.news_provider,
            "review_sources": config.review_sources,
            "fallback_enabled": config.fallback_enabled,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        },
        "categories": [
            _category_payload("market_provider", "行情源", "single", config, settings),
            _category_payload("news_provider", "新闻源", "single", config, settings),
            _category_payload("review_sources", "复盘辅助源", "multiple", config, settings),
        ],
    }


def config_status_items(config: RuntimeProviderConfigState, settings: Settings) -> list[dict[str, object]]:
    selected_keys = {
        "market_provider": {config.market_provider},
        "news_provider": {config.news_provider},
        "review_sources": set(config.review_sources),
    }
    items: list[dict[str, object]] = []
    for option in PROVIDER_OPTIONS:
        enabled = option.key in selected_keys[option.category]
        items.append(
            {
                "name": option.label,
                "role": option.role,
                "configured": _option_configured(option, settings),
                "enabled": enabled,
                "status": _option_status(option, settings, enabled),
                "detail": _option_detail(option, settings, enabled),
            }
        )
    return items


def _category_payload(
    key: str,
    label: str,
    selection: str,
    config: RuntimeProviderConfigState,
    settings: Settings,
) -> dict[str, object]:
    current_values = set(config.review_sources) if key == "review_sources" else {
        getattr(config, key)
    }
    return {
        "key": key,
        "label": label,
        "selection": selection,
        "options": [
            {
                "key": option.key,
                "label": option.label,
                "role": option.role,
                "configured": _option_configured(option, settings),
                "enabled": option.key in current_values,
                "status": _option_status(option, settings, option.key in current_values),
                "requires_key": option.requires_key,
                "experimental": option.experimental,
                "detail": _option_detail(option, settings, option.key in current_values),
            }
            for option in PROVIDER_OPTIONS
            if option.category == key
        ],
    }


def _option_configured(option: ProviderOption, settings: Settings) -> bool:
    if not option.requires_key:
        return True
    value = getattr(settings, option.env_key_name or "", "")
    return bool(value)


def _option_status(option: ProviderOption, settings: Settings, enabled: bool) -> str:
    if option.experimental and enabled:
        return "experimental"
    if not enabled:
        return "disabled"
    if option.local:
        return "local"
    if not _option_configured(option, settings):
        return "missing_key"
    return "ready"


def _option_detail(option: ProviderOption, settings: Settings, enabled: bool) -> str:
    if option.env_key_name:
        env_name = option.env_key_name.upper()
        return f"{env_name} 已配置" if _option_configured(option, settings) else f"{env_name} 未配置"
    if option.experimental:
        return "已启用实验源" if enabled else "实验源未启用"
    return "已启用" if enabled else "未启用"
```

- [ ] **Step 4: Add FastAPI request model and endpoints**

In `apps/api/app/main.py`, add imports:

```python
from app.providers.runtime_config import (
    RuntimeProviderConfigInput,
    build_data_source_options_payload,
    config_status_items,
    get_runtime_provider_config,
    save_runtime_provider_config,
)
```

Replace the body of `get_config_status()` with:

```python
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
```

Add endpoints after `get_config_status()`:

```python
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
```

- [ ] **Step 5: Run API option tests**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_report_api.py::test_data_source_options_api_returns_current_options tests/test_report_api.py::test_data_source_options_api_saves_runtime_config tests/test_report_api.py::test_data_source_options_api_rejects_unknown_provider -q
```

Expected: PASS.

- [ ] **Step 6: Run existing config status tests and update expected names if needed**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_report_api.py::test_config_status_api_returns_sanitized_provider_state tests/test_report_api.py::test_config_status_api_marks_thsdk_experimental_when_enabled -q
```

Expected: Existing tests may fail because labels changed to registry labels. Update assertions from `"TickFlow"`, `"Anspire"`, `"THSDK"` if necessary only to match the final labels in `PROVIDER_OPTIONS`; keep the no-secret assertions.

---

### Task 3: a-stock-data Providers

**Files:**
- Create: `apps/api/app/providers/a_stock_data.py`
- Test: `apps/api/tests/test_a_stock_data_provider.py`

- [ ] **Step 1: Write failing provider tests**

Create `apps/api/tests/test_a_stock_data_provider.py`:

```python
from app.providers.a_stock_data import (
    AStockIndustryRankProvider,
    AStockThsHotProvider,
    EastmoneyGlobalNewsProvider,
)


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = "callback({})"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self.payload


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []
        self.closed = False

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        return self.response

    def close(self) -> None:
        self.closed = True


def test_a_stock_ths_hot_maps_hot_reason_payload() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "errocode": 0,
                "data": [
                    {
                        "code": "300476",
                        "name": "胜宏科技",
                        "reason": "PCB+AI服务器",
                        "zhangfu": "12.34",
                    },
                    {
                        "code": "688017",
                        "name": "绿的谐波",
                        "reason": "机器人+减速器",
                        "zhangfu": "20.00",
                    },
                ],
            }
        )
    )
    provider = AStockThsHotProvider(http_client=client)

    result = provider("2026-05-26")

    assert result.source == "a-stock-data 同花顺热点"
    assert result.status == "success"
    assert {theme.name for theme in result.themes} >= {"PCB", "AI服务器", "机器人", "减速器"}
    assert result.hot_stocks[0].code == "300476"
    assert result.hot_stocks[0].pct_change == 12.34
    assert "胜宏科技: PCB+AI服务器" in result.market_notes


def test_a_stock_industry_rank_maps_eastmoney_payload() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "data": {
                    "diff": [
                        {
                            "f14": "半导体",
                            "f3": 4.2,
                            "f12": "BK1036",
                            "f104": 75,
                            "f105": 12,
                            "f140": "中芯国际",
                            "f136": 8.8,
                        }
                    ]
                }
            }
        )
    )
    provider = AStockIndustryRankProvider(http_client=client, top_n=5)

    result = provider("2026-05-26")

    assert result.source == "a-stock-data 东财行业排名"
    assert result.status == "success"
    assert result.themes[0].name == "半导体"
    assert result.themes[0].pct_change == 4.2
    assert result.hot_stocks[0].name == "中芯国际"
    assert "涨75跌12" in result.market_notes[0]


def test_eastmoney_global_news_filters_by_sector_keyword() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "data": {
                    "fastNewsList": [
                        {
                            "title": "机器人产业链订单增长",
                            "summary": "减速器和伺服方向活跃",
                            "showTime": "2026-05-26 15:00:00",
                        },
                        {
                            "title": "海外宏观快讯",
                            "summary": "指数波动",
                            "showTime": "2026-05-26 14:00:00",
                        },
                    ]
                }
            }
        )
    )
    provider = EastmoneyGlobalNewsProvider(http_client=client, page_size=20)

    items = provider.search_sector_news("机器人", "2026-05-26")

    assert len(items) == 1
    assert items[0].title == "机器人产业链订单增长"
    assert items[0].matched_sector == "机器人"
    assert items[0].source == "东方财富"
    assert items[0].weight == 0.7
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_a_stock_data_provider.py -q
```

Expected: FAIL because `app.providers.a_stock_data` does not exist.

- [ ] **Step 3: Implement providers**

Create `apps/api/app/providers/a_stock_data.py`:

```python
from __future__ import annotations

import re
import time
import uuid
from typing import Any

import httpx

from app.providers.market import ProviderFallbackError
from app.providers.review_sources import (
    ReviewSourceResult,
    ReviewStockEvidence,
    ReviewThemeEvidence,
)
from app.schemas.report import NewsItem


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"


class AStockThsHotProvider:
    source_name = "a-stock-data 同花顺热点"

    def __init__(self, timeout_seconds: float = 12, http_client: object | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()
        self.source_url = "http://zx.10jqka.com.cn/event/api/getharden/"

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def __call__(self, trade_date: str) -> ReviewSourceResult:
        url = (
            "http://zx.10jqka.com.cn/event/api/getharden/"
            f"date/{trade_date}/orderby/date/orderway/desc/charset/GBK/"
        )
        response = self.http_client.get(url, headers={"User-Agent": UA}, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("errocode", 0) != 0:
            return ReviewSourceResult(
                source=self.source_name,
                source_url=url,
                status="failed",
                reason=str(payload.get("errormsg", "同花顺热点响应异常")) if isinstance(payload, dict) else "同花顺热点响应异常",
                trade_date=trade_date,
            )
        rows = payload.get("data") or []
        if not isinstance(rows, list) or not rows:
            return ReviewSourceResult(
                source=self.source_name,
                source_url=url,
                status="failed",
                reason="同花顺热点无结果",
                trade_date=trade_date,
            )

        themes: list[ReviewThemeEvidence] = []
        hot_stocks: list[ReviewStockEvidence] = []
        notes: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            code = str(row.get("code") or "").strip()
            reason = str(row.get("reason") or "").strip()
            pct_change = _to_float(row.get("zhangfu"))
            if name:
                hot_stocks.append(
                    ReviewStockEvidence(
                        name=name,
                        code=code or None,
                        pct_change=pct_change,
                        note=reason,
                        source=self.source_name,
                    )
                )
            if name and reason:
                notes.append(f"{name}: {reason}")
            for theme_name in _split_reason_tags(reason):
                themes.append(
                    ReviewThemeEvidence(
                        name=theme_name,
                        pct_change=pct_change,
                        reason=reason,
                        stocks=[
                            ReviewStockEvidence(
                                name=name,
                                code=code or None,
                                pct_change=pct_change,
                                note=reason,
                                source=self.source_name,
                            )
                        ]
                        if name
                        else [],
                        source=self.source_name,
                    )
                )

        return ReviewSourceResult(
            source=self.source_name,
            source_url=url,
            status="success" if themes or hot_stocks else "failed",
            reason=None if themes or hot_stocks else "未解析到同花顺热点内容",
            trade_date=trade_date,
            themes=_dedupe_themes(themes),
            hot_stocks=_dedupe_stocks(hot_stocks),
            market_notes=_dedupe_text(notes[:20]),
        )


class AStockIndustryRankProvider:
    source_name = "a-stock-data 东财行业排名"

    def __init__(
        self,
        timeout_seconds: float = 12,
        http_client: object | None = None,
        top_n: int = 20,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()
        self.top_n = top_n
        self.source_url = "https://push2.eastmoney.com/api/qt/clist/get"

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def __call__(self, trade_date: str) -> ReviewSourceResult:
        response = self.http_client.get(
            self.source_url,
            headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"},
            params={
                "pn": "1",
                "pz": "100",
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fs": "m:90+t:2",
                "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", {}).get("diff", []) if isinstance(payload, dict) else []
        if not isinstance(items, list) or not items:
            return ReviewSourceResult(
                source=self.source_name,
                source_url=self.source_url,
                status="failed",
                reason="东财行业排名无结果",
                trade_date=trade_date,
            )
        themes: list[ReviewThemeEvidence] = []
        stocks: list[ReviewStockEvidence] = []
        notes: list[str] = []
        for item in items[: self.top_n]:
            if not isinstance(item, dict):
                continue
            industry = str(item.get("f14") or "").strip()
            pct_change = _to_float(item.get("f3"))
            leader = str(item.get("f140") or "").strip()
            leader_change = _to_float(item.get("f136"))
            up_count = item.get("f104", 0)
            down_count = item.get("f105", 0)
            if industry:
                themes.append(
                    ReviewThemeEvidence(
                        name=industry,
                        pct_change=pct_change,
                        reason=f"行业涨跌幅{pct_change if pct_change is not None else 0}%，涨{up_count}跌{down_count}",
                        source=self.source_name,
                    )
                )
                notes.append(f"{industry}: {pct_change if pct_change is not None else 0}% 涨{up_count}跌{down_count} 领涨{leader}")
            if leader:
                stocks.append(
                    ReviewStockEvidence(
                        name=leader,
                        pct_change=leader_change,
                        source=self.source_name,
                    )
                )
        return ReviewSourceResult(
            source=self.source_name,
            source_url=self.source_url,
            status="success" if themes else "failed",
            reason=None if themes else "未解析到行业排名内容",
            trade_date=trade_date,
            themes=_dedupe_themes(themes),
            hot_stocks=_dedupe_stocks(stocks),
            market_notes=_dedupe_text(notes),
        )


class EastmoneyGlobalNewsProvider:
    provider_name = "eastmoney_global"

    def __init__(
        self,
        timeout_seconds: float = 12,
        http_client: object | None = None,
        page_size: int = 50,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()
        self.page_size = page_size
        self.base_url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        try:
            response = self.http_client.get(
                self.base_url,
                headers={"User-Agent": UA, "Referer": "https://kuaixun.eastmoney.com/"},
                params={
                    "client": "web",
                    "biz": "web_724",
                    "fastColumn": "102",
                    "sortEnd": "",
                    "pageSize": str(self.page_size),
                    "req_trace": str(uuid.uuid4()),
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ProviderFallbackError(f"东财全球资讯请求失败: {exc.__class__.__name__}") from exc

        rows = payload.get("data", {}).get("fastNewsList", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list) or not rows:
            raise ProviderFallbackError("东财全球资讯无结果")
        items = [_global_news_item(row, sector_name) for row in rows if isinstance(row, dict)]
        matched = [
            item
            for item in items
            if sector_name in item.title or sector_name in item.summary
        ]
        if matched:
            return matched[:5]
        fallback_items = items[:3]
        return [
            item.model_copy(update={"matched_sector": sector_name, "weight": 0.4})
            for item in fallback_items
        ]


def _global_news_item(row: dict[str, Any], sector_name: str) -> NewsItem:
    title = str(row.get("title") or "东财全球资讯")
    summary = str(row.get("summary") or title)
    return NewsItem(
        title=title,
        url=str(row.get("url") or "https://kuaixun.eastmoney.com/"),
        source="东方财富",
        summary=summary[:200],
        published_at=row.get("showTime") or row.get("time"),
        matched_sector=sector_name,
        weight=0.7,
    )


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace("%", "").replace("+", "").strip())
    except ValueError:
        return None


def _split_reason_tags(reason: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"[+、,/，]+", reason)
        if item.strip()
    ]


def _dedupe_text(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _dedupe_stocks(values: list[ReviewStockEvidence]) -> list[ReviewStockEvidence]:
    output: list[ReviewStockEvidence] = []
    seen: set[tuple[str, str | None]] = set()
    for value in values:
        key = (value.name, value.code)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _dedupe_themes(values: list[ReviewThemeEvidence]) -> list[ReviewThemeEvidence]:
    output: list[ReviewThemeEvidence] = []
    seen: set[str] = set()
    for value in values:
        if value.name in seen:
            continue
        seen.add(value.name)
        output.append(value)
    return output
```

Remove unused `time` import if ruff flags it.

- [ ] **Step 4: Run provider tests**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_a_stock_data_provider.py -q
```

Expected: PASS.

---

### Task 4: Wire Runtime Config into Provider Factory and Report Generation

**Files:**
- Modify: `apps/api/app/providers/factory.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add failing report integration test**

Append to `apps/api/tests/test_report_api.py`:

```python
def test_create_report_uses_runtime_data_source_options(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path))
    monkeypatch.setenv("MARKET_PROVIDER", "fake")
    monkeypatch.setenv("NEWS_PROVIDER", "fake")
    get_settings.cache_clear()

    class FakeAStockResponse:
        def __init__(self, payload: object) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            pass

        def json(self) -> object:
            return self.payload

    class FakeAStockClient:
        def get(self, url: str, **kwargs: object) -> FakeAStockResponse:
            if "getharden" in url:
                return FakeAStockResponse(
                    {
                        "errocode": 0,
                        "data": [
                            {
                                "code": "688017",
                                "name": "绿的谐波",
                                "reason": "机器人+减速器",
                                "zhangfu": "20.0",
                            }
                        ],
                    }
                )
            return FakeAStockResponse({"data": {"fastNewsList": []}})

        def close(self) -> None:
            pass

    from app.providers import a_stock_data

    monkeypatch.setattr(a_stock_data.httpx, "Client", lambda: FakeAStockClient())

    with TestClient(app) as client:
        client.put(
            "/api/data-sources/options",
            json={
                "market_provider": "fake",
                "news_provider": "fake",
                "review_sources": ["a_stock_ths_hot"],
                "fallback_enabled": True,
            },
        )
        response = client.post("/api/reports/close", json={"trade_date": "2026-05-26"})

    assert response.status_code == 200
    payload = response.json()
    review_sources = payload["provider_status"]["review_sources"]
    assert review_sources[0]["source"] == "a-stock-data 同花顺热点"
    assert review_sources[0]["status"] == "success"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_report_api.py::test_create_report_uses_runtime_data_source_options -q
```

Expected: FAIL because factory does not read runtime config.

- [ ] **Step 3: Update provider factory**

In `apps/api/app/providers/factory.py`, add imports:

```python
from app.providers.a_stock_data import (
    AStockIndustryRankProvider,
    AStockThsHotProvider,
    EastmoneyGlobalNewsProvider,
)
from app.providers.runtime_config import RuntimeProviderConfigState
```

Change function signature:

```python
def create_provider_bundle(
    settings: Settings,
    runtime_config: RuntimeProviderConfigState | None = None,
) -> ProviderBundle:
    _validate_production_providers(settings, runtime_config)
    return ProviderBundle(
        market_provider=_create_market_provider(settings, runtime_config),
        news_provider=_create_news_provider(settings, runtime_config),
        llm_provider=_create_llm_provider(settings),
        ocr_provider=_create_ocr_provider(settings),
        tickflow_provider=_create_tickflow_provider(settings),
        review_source_provider=_create_review_source_provider(settings, runtime_config),
    )
```

Add helper:

```python
def _runtime_value(runtime_config: RuntimeProviderConfigState | None, name: str, fallback: object) -> object:
    if runtime_config is None:
        return fallback
    return getattr(runtime_config, name)
```

Update market provider:

```python
def _create_market_provider(
    settings: Settings,
    runtime_config: RuntimeProviderConfigState | None = None,
) -> MarketDataProvider:
    market_provider = str(_runtime_value(runtime_config, "market_provider", settings.market_provider))
    if market_provider == "fake":
        return FakeMarketDataProvider()
    if market_provider == "tickflow":
        return TickFlowMarketDataProvider(
            api_key=settings.tickflow_api_key,
            base_url=settings.tickflow_base_url,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    raise ValueError(f"Unsupported MARKET_PROVIDER: {market_provider}")
```

Update news provider:

```python
def _create_news_provider(
    settings: Settings,
    runtime_config: RuntimeProviderConfigState | None = None,
) -> NewsProvider:
    news_provider = str(_runtime_value(runtime_config, "news_provider", settings.news_provider))
    fallback_enabled = bool(_runtime_value(runtime_config, "fallback_enabled", settings.provider_fallback_enabled))
    if news_provider == "fake":
        return FakeNewsProvider()
    if news_provider == "anspire":
        return FallbackNewsProvider(
            primary=AnspireNewsProvider(
                api_key=settings.anspire_api_key,
                base_url=settings.anspire_base_url,
                top_k=settings.news_top_k,
                lookback_hours=settings.news_lookback_hours,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            fallback=FakeNewsProvider(),
            fallback_enabled=fallback_enabled,
        )
    if news_provider == "eastmoney_global":
        return FallbackNewsProvider(
            primary=EastmoneyGlobalNewsProvider(
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            fallback=FakeNewsProvider(),
            fallback_enabled=fallback_enabled,
        )
    raise ValueError(f"Unsupported NEWS_PROVIDER: {news_provider}")
```

Update review source provider:

```python
def _create_review_source_provider(
    settings: Settings,
    runtime_config: RuntimeProviderConfigState | None = None,
) -> ReviewSourceAggregator | None:
    if runtime_config is None:
        if not settings.review_sources_enabled:
            return None
        review_sources = ["ths_fupan", "eastmoney_ztfp"]
        if settings.thsdk_enabled:
            review_sources.append("thsdk")
    else:
        review_sources = runtime_config.review_sources
    providers: list[object] = []
    if "ths_fupan" in review_sources:
        providers.append(
            ThsFupanProvider(
                source_url=settings.ths_fupan_url,
                timeout_seconds=settings.provider_timeout_seconds,
            )
        )
    if "eastmoney_ztfp" in review_sources:
        providers.append(
            EastmoneyZtFpProvider(
                source_url=settings.eastmoney_ztfp_url,
                timeout_seconds=settings.provider_timeout_seconds,
            )
        )
    if "thsdk" in review_sources:
        providers.append(ThsdkProvider.from_installed_package())
    if "a_stock_ths_hot" in review_sources:
        providers.append(AStockThsHotProvider(timeout_seconds=settings.provider_timeout_seconds))
    if "a_stock_industry_rank" in review_sources:
        providers.append(AStockIndustryRankProvider(timeout_seconds=settings.provider_timeout_seconds))
    return ReviewSourceAggregator(providers=providers) if providers else None
```

Update production validation signature:

```python
def _validate_production_providers(
    settings: Settings,
    runtime_config: RuntimeProviderConfigState | None = None,
) -> None:
    if settings.app_env != "production" or settings.production_allow_fake_providers:
        return
    market_provider = str(_runtime_value(runtime_config, "market_provider", settings.market_provider))
    news_provider = str(_runtime_value(runtime_config, "news_provider", settings.news_provider))
    fallback_enabled = bool(_runtime_value(runtime_config, "fallback_enabled", settings.provider_fallback_enabled))
    fake_providers = {
        "MARKET_PROVIDER": market_provider,
        "NEWS_PROVIDER": news_provider,
        "LLM_PROVIDER": settings.llm_provider,
        "OCR_PROVIDER": settings.ocr_provider,
        "TICKFLOW_PROVIDER": settings.tickflow_provider,
    }
    for name, value in fake_providers.items():
        if value == "fake":
            raise ValueError(f"Production cannot use fake provider: {name}")
    if fallback_enabled:
        raise ValueError("Production cannot use fake fallback: PROVIDER_FALLBACK_ENABLED")
    if settings.ocr_fallback_enabled:
        raise ValueError("Production cannot use fake fallback: OCR_FALLBACK_ENABLED")
    if settings.structured_review_fallback_enabled and settings.structured_review_provider == "llm":
        raise ValueError("Production cannot use fake fallback: STRUCTURED_REVIEW_FALLBACK_ENABLED")
```

- [ ] **Step 4: Use runtime config in report endpoints**

In `apps/api/app/main.py`, update `_create_report_response()` or the helper that constructs `create_provider_bundle(settings)` for close/midday reports. Replace:

```python
with create_provider_bundle(settings) as providers:
```

With:

```python
runtime_config = get_runtime_provider_config(app.state.engine, settings)
with create_provider_bundle(settings, runtime_config=runtime_config) as providers:
```

Do not change weekly generation unless tests require it; spec says weekly client remains unchanged.

- [ ] **Step 5: Run integration test**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_report_api.py::test_create_report_uses_runtime_data_source_options -q
```

Expected: PASS.

---

### Task 5: Frontend API Types and Client

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Test: `apps/web/lib/dataSourceStatusPanel.test.ts`

- [ ] **Step 1: Write failing static test**

Replace `apps/web/lib/dataSourceStatusPanel.test.ts` with:

```typescript
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("data source panel supports runtime provider options", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
  const panelSource = readFileSync(new URL("../components/DataSourceStatusPanel.tsx", import.meta.url), "utf8");

  assert.match(typesSource, /DataSourceOptionsResponse/);
  assert.match(typesSource, /DataSourceOptionsUpdate/);
  assert.match(apiSource, /getDataSourceOptions/);
  assert.match(apiSource, /updateDataSourceOptions/);
  assert.match(panelSource, /fallback_enabled/);
  assert.match(panelSource, /review_sources/);
  assert.match(panelSource, /onSave/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
corepack pnpm --filter @stock-review/web test -- lib/dataSourceStatusPanel.test.ts
```

Expected: FAIL because types/client/panel do not yet include runtime options.

- [ ] **Step 3: Add TypeScript types**

Append to `apps/web/lib/types.ts`:

```typescript
export type DataSourceSelectionMode = "single" | "multiple";

export type DataSourceOptionItem = {
  key: string;
  label: string;
  role: string;
  configured: boolean;
  enabled: boolean;
  status: ConfigStatusState;
  requires_key: boolean;
  experimental: boolean;
  detail: string;
};

export type DataSourceOptionCategory = {
  key: "market_provider" | "news_provider" | "review_sources";
  label: string;
  selection: DataSourceSelectionMode;
  options: DataSourceOptionItem[];
};

export type DataSourceOptionsCurrent = {
  market_provider: string;
  news_provider: string;
  review_sources: string[];
  fallback_enabled: boolean;
  updated_at: string | null;
};

export type DataSourceOptionsResponse = {
  current: DataSourceOptionsCurrent;
  categories: DataSourceOptionCategory[];
};

export type DataSourceOptionsUpdate = {
  market_provider: string;
  news_provider: string;
  review_sources: string[];
  fallback_enabled: boolean;
};
```

- [ ] **Step 4: Add API client functions**

In `apps/web/lib/api.ts`, add imports:

```typescript
  DataSourceOptionsResponse,
  DataSourceOptionsUpdate,
```

Then add functions after `getConfigStatus()`:

```typescript
export async function getDataSourceOptions(): Promise<DataSourceOptionsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/data-sources/options`);
  if (!response.ok) {
    throw new Error(`读取数据源选项失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<DataSourceOptionsResponse>;
}

export async function updateDataSourceOptions(
  payload: DataSourceOptionsUpdate,
): Promise<DataSourceOptionsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/data-sources/options`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`保存数据源选项失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<DataSourceOptionsResponse>;
}
```

- [ ] **Step 5: Run frontend test**

Run:

```bash
corepack pnpm --filter @stock-review/web test -- lib/dataSourceStatusPanel.test.ts
```

Expected: Still FAIL until panel is implemented in Task 6, but TypeScript compile errors from missing types/functions should be resolved.

---

### Task 6: Frontend Configurable Data Source Panel

**Files:**
- Modify: `apps/web/components/DataSourceStatusPanel.tsx`
- Modify: `apps/web/app/page.tsx`
- Test: `apps/web/lib/dataSourceStatusPanel.test.ts`

- [ ] **Step 1: Replace panel props and implementation**

Replace `apps/web/components/DataSourceStatusPanel.tsx` with:

```tsx
import type {
  ConfigStatusItem,
  DataSourceOptionsCurrent,
  DataSourceOptionsResponse,
} from "../lib/types";

const statusCopy: Record<ConfigStatusItem["status"], { label: string; dot: string; badge: string }> = {
  ready: {
    label: "已就绪",
    dot: "bg-emerald-500",
    badge: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  },
  missing_key: {
    label: "缺少 Key",
    dot: "bg-amber-500",
    badge: "bg-amber-50 text-amber-700 ring-amber-100",
  },
  disabled: {
    label: "未启用",
    dot: "bg-slate-300",
    badge: "bg-slate-100 text-slate-500 ring-slate-200",
  },
  local: {
    label: "本地",
    dot: "bg-sky-500",
    badge: "bg-sky-50 text-sky-700 ring-sky-100",
  },
  experimental: {
    label: "实验",
    dot: "bg-violet-500",
    badge: "bg-violet-50 text-violet-700 ring-violet-100",
  },
};

const unknownStatusCopy = {
  label: "未知",
  dot: "bg-slate-400",
  badge: "bg-slate-100 text-slate-600 ring-slate-200",
};

export function DataSourceStatusPanel({
  items,
  options,
  draft,
  saving,
  error,
  onDraftChange,
  onSave,
}: {
  items: ConfigStatusItem[];
  options: DataSourceOptionsResponse | null;
  draft: DataSourceOptionsCurrent | null;
  saving: boolean;
  error: string | null;
  onDraftChange: (draft: DataSourceOptionsCurrent) => void;
  onSave: () => void;
}) {
  return (
    <section id="sources" className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Data Sources</p>
          <h2 className="mt-1 text-xl font-black tracking-tight text-slate-950">数据源配置状态</h2>
        </div>
        <p className="text-sm text-slate-500">运行时配置保存到本地 SQLite，不显示 API Key 明文。</p>
      </div>

      {options && draft && (
        <div className="mt-4 space-y-4 rounded-2xl border border-slate-100 bg-slate-50 p-4">
          {options.categories.map((category) => (
            <fieldset key={category.key} className="space-y-2">
              <legend className="text-sm font-black text-slate-800">{category.label}</legend>
              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {category.options.map((option) => {
                  const checked =
                    category.key === "review_sources"
                      ? draft.review_sources.includes(option.key)
                      : draft[category.key] === option.key;
                  return (
                    <label
                      key={`${category.key}-${option.key}`}
                      className={`flex min-h-20 cursor-pointer items-start gap-3 rounded-2xl border bg-white p-3 text-sm transition ${
                        checked ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <input
                        checked={checked}
                        className="mt-1 h-4 w-4 accent-slate-950"
                        name={category.key}
                        onChange={() => onDraftChange(updateDraft(draft, category.key, option.key))}
                        type={category.selection === "multiple" ? "checkbox" : "radio"}
                      />
                      <span className="min-w-0">
                        <span className="block font-black text-slate-950">{option.label}</span>
                        <span className="mt-1 block text-xs font-semibold text-slate-500">{option.role}</span>
                        <span className="mt-1 block text-xs leading-5 text-slate-500">{option.detail}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))}

          <label className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-3">
            <span>
              <span className="block text-sm font-black text-slate-950">数据源失败时允许 fake 回退</span>
              <span className="mt-1 block text-xs text-slate-500">关闭后真实源失败会直接让报告生成失败。</span>
            </span>
            <input
              checked={draft.fallback_enabled}
              className="h-5 w-5 accent-slate-950"
              onChange={(event) => onDraftChange({ ...draft, fallback_enabled: event.target.checked })}
              type="checkbox"
            />
          </label>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-xs text-slate-500">
              {draft.updated_at ? `上次保存：${new Date(draft.updated_at).toLocaleString("zh-CN")}` : "当前使用环境变量默认配置"}
            </div>
            <button
              className="rounded-full bg-slate-950 px-4 py-2 text-sm font-bold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
              disabled={saving}
              onClick={onSave}
              type="button"
            >
              {saving ? "保存中" : "保存数据源选项"}
            </button>
          </div>
          {error && <p className="rounded-2xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        </div>
      )}

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => {
          const view = statusCopy[item.status] ?? unknownStatusCopy;
          return (
            <article key={item.name} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${view.dot}`} aria-hidden="true" />
                    <h3 className="font-black text-slate-950">{item.name}</h3>
                  </div>
                  <p className="mt-1 text-xs font-semibold text-slate-500">{item.role}</p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${view.badge}`}>
                  {view.label}
                </span>
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-500">{item.detail}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function updateDraft(
  draft: DataSourceOptionsCurrent,
  key: "market_provider" | "news_provider" | "review_sources",
  value: string,
): DataSourceOptionsCurrent {
  if (key === "review_sources") {
    return {
      ...draft,
      review_sources: draft.review_sources.includes(value)
        ? draft.review_sources.filter((item) => item !== value)
        : [...draft.review_sources, value],
    };
  }
  return { ...draft, [key]: value };
}
```

- [ ] **Step 2: Wire page state and API calls**

In `apps/web/app/page.tsx`, update import:

```typescript
import {
  createReport,
  deleteReport,
  getConfigStatus,
  getDataSourceOptions,
  listReports,
  reportAssetUrl,
  updateDataSourceOptions,
} from "../lib/api";
```

Update type import:

```typescript
import type {
  ConfigStatusItem,
  CreateReportResponse,
  DataSourceOptionsCurrent,
  DataSourceOptionsResponse,
  ReportKind,
  ReportListItem,
} from "../lib/types";
```

Add state near `configItems`:

```typescript
const [dataSourceOptions, setDataSourceOptions] = useState<DataSourceOptionsResponse | null>(null);
const [dataSourceDraft, setDataSourceDraft] = useState<DataSourceOptionsCurrent | null>(null);
const [savingDataSources, setSavingDataSources] = useState(false);
const [dataSourceError, setDataSourceError] = useState<string | null>(null);
```

Add function:

```typescript
async function refreshDataSourceOptions() {
  try {
    const response = await getDataSourceOptions();
    setDataSourceOptions(response);
    setDataSourceDraft(response.current);
    setDataSourceError(null);
  } catch (err) {
    setDataSourceOptions(null);
    setDataSourceDraft(null);
    setDataSourceError(err instanceof Error ? err.message : "读取数据源选项失败");
  }
}
```

Update initial `useEffect()` to call it:

```typescript
void refreshDataSourceOptions();
```

Add save handler:

```typescript
async function handleSaveDataSources() {
  if (!dataSourceDraft) {
    return;
  }
  setSavingDataSources(true);
  setDataSourceError(null);
  try {
    const response = await updateDataSourceOptions({
      market_provider: dataSourceDraft.market_provider,
      news_provider: dataSourceDraft.news_provider,
      review_sources: dataSourceDraft.review_sources,
      fallback_enabled: dataSourceDraft.fallback_enabled,
    });
    setDataSourceOptions(response);
    setDataSourceDraft(response.current);
    await refreshConfigStatus();
  } catch (err) {
    setDataSourceError(err instanceof Error ? err.message : "保存数据源选项失败");
  } finally {
    setSavingDataSources(false);
  }
}
```

Replace panel usage:

```tsx
<DataSourceStatusPanel
  error={dataSourceError}
  items={configItems}
  onDraftChange={setDataSourceDraft}
  onSave={() => void handleSaveDataSources()}
  options={dataSourceOptions}
  draft={dataSourceDraft}
  saving={savingDataSources}
/>
```

- [ ] **Step 3: Run frontend tests**

Run:

```bash
corepack pnpm --filter @stock-review/web test
```

Expected: PASS.

---

### Task 7: End-to-End Verification and Cleanup

**Files:**
- All touched files

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_runtime_provider_config.py tests/test_a_stock_data_provider.py tests/test_report_api.py::test_data_source_options_api_returns_current_options tests/test_report_api.py::test_data_source_options_api_saves_runtime_config tests/test_report_api.py::test_data_source_options_api_rejects_unknown_provider tests/test_report_api.py::test_create_report_uses_runtime_data_source_options -q
```

Expected: PASS.

- [ ] **Step 2: Run backend lint on touched app modules**

Run:

```bash
cd apps/api
.venv/bin/python -m ruff check app/providers/runtime_config.py app/providers/a_stock_data.py app/providers/factory.py app/main.py app/db/models.py
```

Expected: PASS.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
corepack pnpm --filter @stock-review/web test
```

Expected: PASS.

- [ ] **Step 4: Inspect git diff**

Run:

```bash
git diff --stat
git diff --check
```

Expected: no whitespace errors; diff limited to planned files and tests.

- [ ] **Step 5: Commit implementation**

Stage only files changed for this feature:

```bash
git add apps/api/app/db/models.py \
  apps/api/app/providers/runtime_config.py \
  apps/api/app/providers/a_stock_data.py \
  apps/api/app/providers/factory.py \
  apps/api/app/main.py \
  apps/api/tests/test_runtime_provider_config.py \
  apps/api/tests/test_a_stock_data_provider.py \
  apps/api/tests/test_report_api.py \
  apps/web/lib/types.ts \
  apps/web/lib/api.ts \
  apps/web/components/DataSourceStatusPanel.tsx \
  apps/web/app/page.tsx \
  apps/web/lib/dataSourceStatusPanel.test.ts
git commit -m "feat: add runtime data source options"
```

Expected: commit succeeds.
