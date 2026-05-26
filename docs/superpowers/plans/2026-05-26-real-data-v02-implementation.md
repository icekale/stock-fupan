# v0.2 Real Data Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add AkShare market data and Anspire news search as default real providers with detailed fallback diagnostics and fake-provider safety.

**Architecture:** Keep provider implementations behind the existing `MarketDataProvider` and `NewsProvider` protocols, add fallback wrappers that record provider status, and expose those diagnostics through `GeneratedReport`, API responses, snapshots, and the frontend preview. The endpoint should build providers through a factory instead of directly instantiating fake providers.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, AkShare, httpx, pytest, Next.js, TypeScript, Tailwind, pnpm, uv.

---

## File Structure

Create or modify these files:

```text
apps/api/app/
  config.py                         # add provider settings
  main.py                           # use provider factory and return provider_status
  providers/
    market.py                       # add ProviderStatus, fallback wrapper, AkShare provider
    news.py                         # add fallback wrapper and Anspire provider
    factory.py                      # create configured provider bundle
  services/
    report_generator.py             # return/write provider_status
  tests/
    test_real_providers.py          # provider conversion/fallback unit tests
    test_report_api.py              # API/snapshot provider_status assertions
apps/web/
  lib/types.ts                      # provider_status response types
  components/ProviderStatusPanel.tsx # data-source diagnostic UI
  components/ReportPreview.tsx      # render diagnostic panel
README.md                           # document real provider env vars
.env.example                        # add provider settings
```

---

### Task 1: Add Provider Status Contracts

**Files:**
- Modify: `apps/api/app/providers/market.py`
- Modify: `apps/api/app/providers/news.py`
- Create: `apps/api/tests/test_real_providers.py`

- [ ] **Step 1: Write provider status tests**

Create `apps/api/tests/test_real_providers.py`:

```python
from app.providers.market import ProviderStatus
from app.providers.news import SectorNewsResult
from app.schemas.report import NewsItem


def test_provider_status_serializes_for_snapshot() -> None:
    status = ProviderStatus(
        provider="akshare",
        status="fallback",
        fallback_used=True,
        reason="AkShare v0.2 暂不支持历史日期",
    )

    assert status.model_dump(mode="json") == {
        "provider": "akshare",
        "status": "fallback",
        "fallback_used": True,
        "reason": "AkShare v0.2 暂不支持历史日期",
    }


def test_sector_news_result_keeps_sector_status_and_items() -> None:
    item = NewsItem(
        title="机器人产业链催化增强",
        url="https://example.com/news",
        source="示例财经",
        summary="机器人方向出现政策和产业消息共振。",
        matched_sector="机器人",
        weight=0.8,
    )
    result = SectorNewsResult(
        sector="机器人",
        items=[item],
        status=ProviderStatus(
            provider="anspire",
            status="success",
            fallback_used=False,
            reason=None,
        ),
    )

    assert result.sector == "机器人"
    assert result.items == [item]
    assert result.status.provider == "anspire"
    assert result.status.status == "success"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py -v
```

Expected: FAIL because `ProviderStatus` and `SectorNewsResult` do not exist.

- [ ] **Step 3: Add status models**

Modify `apps/api/app/providers/market.py` near imports:

```python
from typing import Literal, Protocol

from pydantic import BaseModel
```

Add before `MarketCloseSnapshot`:

```python
ProviderState = Literal["success", "fallback", "disabled", "failed"]


class ProviderStatus(BaseModel):
    provider: str
    status: ProviderState
    fallback_used: bool = False
    reason: str | None = None
```

Modify `apps/api/app/providers/news.py` imports:

```python
from pydantic import BaseModel

from app.providers.market import ProviderStatus
from app.schemas.report import NewsItem
```

Add before `NewsProvider`:

```python
class SectorNewsResult(BaseModel):
    sector: str
    items: list[NewsItem]
    status: ProviderStatus
```

- [ ] **Step 4: Run status tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/providers/market.py apps/api/app/providers/news.py apps/api/tests/test_real_providers.py
git commit -m "feat: add provider status contracts"
```

---

### Task 2: Add Fallback Provider Wrappers

**Files:**
- Modify: `apps/api/app/providers/market.py`
- Modify: `apps/api/app/providers/news.py`
- Modify: `apps/api/tests/test_real_providers.py`

- [ ] **Step 1: Append fallback wrapper tests**

Append to `apps/api/tests/test_real_providers.py`:

```python
import pytest

from app.providers.market import (
    FakeMarketDataProvider,
    FallbackMarketDataProvider,
    MarketCloseSnapshot,
    ProviderFallbackError,
)
from app.providers.news import FakeNewsProvider, FallbackNewsProvider


class BrokenMarketProvider:
    provider_name = "akshare"

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        raise ProviderFallbackError("AkShare v0.2 暂不支持历史日期")


class BrokenNewsProvider:
    provider_name = "anspire"

    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        raise ProviderFallbackError("ANSPIRE_API_KEY 未配置")


def test_market_fallback_returns_fake_snapshot_and_reason() -> None:
    provider = FallbackMarketDataProvider(
        primary=BrokenMarketProvider(),
        fallback=FakeMarketDataProvider(),
        fallback_enabled=True,
    )

    snapshot, status = provider.get_close_snapshot_with_status("2026-05-25")

    assert snapshot.raw_sectors[0].name == "机器人"
    assert status.provider == "akshare"
    assert status.status == "fallback"
    assert status.fallback_used is True
    assert status.reason == "AkShare v0.2 暂不支持历史日期"


def test_market_fallback_can_raise_when_disabled() -> None:
    provider = FallbackMarketDataProvider(
        primary=BrokenMarketProvider(),
        fallback=FakeMarketDataProvider(),
        fallback_enabled=False,
    )

    with pytest.raises(ProviderFallbackError):
        provider.get_close_snapshot_with_status("2026-05-25")


def test_news_fallback_returns_fake_items_and_reason() -> None:
    provider = FallbackNewsProvider(
        primary=BrokenNewsProvider(),
        fallback=FakeNewsProvider(),
        fallback_enabled=True,
    )

    result = provider.search_sector_news_with_status("机器人", "2026-05-26")

    assert result.items[0].matched_sector == "机器人"
    assert result.status.provider == "anspire"
    assert result.status.status == "fallback"
    assert result.status.fallback_used is True
    assert result.status.reason == "ANSPIRE_API_KEY 未配置"
```

- [ ] **Step 2: Run fallback tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py::test_market_fallback_returns_fake_snapshot_and_reason tests/test_real_providers.py::test_news_fallback_returns_fake_items_and_reason -v
```

Expected: FAIL because wrappers do not exist.

- [ ] **Step 3: Implement market fallback wrapper**

Modify `apps/api/app/providers/market.py`.

Add after `ProviderStatus`:

```python
class ProviderFallbackError(RuntimeError):
    pass


def _provider_name(provider: object, default: str) -> str:
    value = getattr(provider, "provider_name", default)
    return value if isinstance(value, str) and value else default
```

Add after `FakeMarketDataProvider`:

```python
class FallbackMarketDataProvider:
    def __init__(
        self,
        primary: MarketDataProvider,
        fallback: MarketDataProvider,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        snapshot, _status = self.get_close_snapshot_with_status(trade_date)
        return snapshot

    def get_close_snapshot_with_status(self, trade_date: str) -> tuple[MarketCloseSnapshot, ProviderStatus]:
        provider = _provider_name(self.primary, "market")
        try:
            snapshot = self.primary.get_close_snapshot(trade_date)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            if not self.fallback_enabled:
                raise
            return self.fallback.get_close_snapshot(trade_date), ProviderStatus(
                provider=provider,
                status="fallback",
                fallback_used=True,
                reason=reason,
            )

        return snapshot, ProviderStatus(
            provider=provider,
            status="success",
            fallback_used=False,
            reason=None,
        )
```

- [ ] **Step 4: Implement news fallback wrapper**

Modify `apps/api/app/providers/news.py`.

Add helper:

```python
def _provider_name(provider: object, default: str) -> str:
    value = getattr(provider, "provider_name", default)
    return value if isinstance(value, str) and value else default
```

Add after `FakeNewsProvider`:

```python
class FallbackNewsProvider:
    def __init__(
        self,
        primary: NewsProvider,
        fallback: NewsProvider,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        result = self.search_sector_news_with_status(sector_name, trade_date)
        return result.items

    def search_sector_news_with_status(self, sector_name: str, trade_date: str) -> SectorNewsResult:
        provider = _provider_name(self.primary, "news")
        try:
            items = self.primary.search_sector_news(sector_name, trade_date)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            if not self.fallback_enabled:
                raise
            return SectorNewsResult(
                sector=sector_name,
                items=self.fallback.search_sector_news(sector_name, trade_date),
                status=ProviderStatus(
                    provider=provider,
                    status="fallback",
                    fallback_used=True,
                    reason=reason,
                ),
            )

        return SectorNewsResult(
            sector=sector_name,
            items=items,
            status=ProviderStatus(
                provider=provider,
                status="success",
                fallback_used=False,
                reason=None,
            ),
        )
```

- [ ] **Step 5: Run fallback tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/providers/market.py apps/api/app/providers/news.py apps/api/tests/test_real_providers.py
git commit -m "feat: add provider fallback wrappers"
```

---

### Task 3: Implement AkShare Market Provider

**Files:**
- Modify: `apps/api/app/providers/market.py`
- Modify: `apps/api/tests/test_real_providers.py`

- [ ] **Step 1: Append AkShare provider tests**

Append to `apps/api/tests/test_real_providers.py`:

```python
from datetime import date

import pandas as pd

from app.providers.market import AkShareMarketDataProvider


def test_akshare_provider_builds_current_market_snapshot(monkeypatch) -> None:
    class FakeAkshare:
        @staticmethod
        def stock_zh_index_spot_em() -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"名称": "上证指数", "代码": "000001", "最新价": 3100.5, "涨跌幅": 1.2},
                    {"名称": "创业板指", "代码": "399006", "最新价": 1950.2, "涨跌幅": 2.1},
                ]
            )

        @staticmethod
        def stock_zh_a_spot_em() -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"代码": "000001", "名称": "平安银行", "涨跌幅": 1.0, "成交额": 100000000},
                    {"代码": "000002", "名称": "万科A", "涨跌幅": -1.0, "成交额": 200000000},
                    {"代码": "000003", "名称": "涨停股", "涨跌幅": 10.0, "成交额": 300000000},
                    {"代码": "000004", "名称": "跌停股", "涨跌幅": -10.0, "成交额": 400000000},
                ]
            )

        @staticmethod
        def stock_board_industry_name_em() -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"板块名称": "机器人", "涨跌幅": 5.88, "上涨家数": 41, "下跌家数": 9, "总成交额": 35000000000},
                    {"板块名称": "PCB", "涨跌幅": 3.6, "上涨家数": 35, "下跌家数": 15, "总成交额": 22000000000},
                ]
            )

    provider = AkShareMarketDataProvider(
        akshare_module=FakeAkshare,
        today=date(2026, 5, 26),
    )

    snapshot = provider.get_close_snapshot("2026-05-26")

    assert snapshot.indices[0].name == "上证指数"
    assert snapshot.breadth.up_count == 2
    assert snapshot.breadth.down_count == 2
    assert snapshot.breadth.limit_up_count == 1
    assert snapshot.breadth.limit_down_count == 1
    assert snapshot.turnover_cny == 10.0
    assert snapshot.raw_sectors[0].name == "机器人"
    assert snapshot.raw_sectors[0].stock_up_ratio == 0.82


def test_akshare_provider_rejects_historical_date() -> None:
    provider = AkShareMarketDataProvider(today=date(2026, 5, 26))

    with pytest.raises(ProviderFallbackError, match="历史日期"):
        provider.get_close_snapshot("2026-05-25")
```

- [ ] **Step 2: Run AkShare tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py::test_akshare_provider_builds_current_market_snapshot tests/test_real_providers.py::test_akshare_provider_rejects_historical_date -v
```

Expected: FAIL because `AkShareMarketDataProvider` does not exist.

- [ ] **Step 3: Implement AkShare provider**

Modify `apps/api/app/providers/market.py` imports:

```python
from datetime import date
from types import ModuleType
```

Add helper functions before `AkShareMarketDataProvider`:

```python
def _to_float(value: object, default: float | None = None) -> float:
    try:
        if value is None:
            raise TypeError
        return float(value)
    except (TypeError, ValueError):
        if default is None:
            raise ProviderFallbackError("AkShare 返回了非数字字段")
        return default


def _pick(row: object, *names: str) -> object:
    for name in names:
        try:
            value = row[name]
        except Exception:
            continue
        if value is not None:
            return value
    raise ProviderFallbackError(f"AkShare 缺少字段: {'/'.join(names)}")
```

Add class after `FakeMarketDataProvider`:

```python
class AkShareMarketDataProvider:
    provider_name = "akshare"

    def __init__(self, akshare_module: ModuleType | object | None = None, today: date | None = None) -> None:
        self.akshare_module = akshare_module
        self.today = today

    def _akshare(self) -> ModuleType | object:
        if self.akshare_module is not None:
            return self.akshare_module
        import akshare as ak

        return ak

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        current_date = self.today or date.today()
        if trade_date != current_date.isoformat():
            raise ProviderFallbackError("AkShare v0.2 暂不支持历史日期")

        ak = self._akshare()
        index_df = ak.stock_zh_index_spot_em()
        stock_df = ak.stock_zh_a_spot_em()
        sector_df = ak.stock_board_industry_name_em()
        if index_df.empty or stock_df.empty or sector_df.empty:
            raise ProviderFallbackError("AkShare 返回空数据")

        indices = self._build_indices(index_df)
        pct_changes = [_to_float(row["涨跌幅"], 0.0) for _idx, row in stock_df.iterrows()]
        up_count = sum(1 for value in pct_changes if value > 0)
        down_count = sum(1 for value in pct_changes if value < 0)
        turnover_cny = round(
            sum(_to_float(row["成交额"], 0.0) for _idx, row in stock_df.iterrows()) / 100_000_000,
            2,
        )
        raw_sectors = self._build_sectors(sector_df)

        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=indices,
            breadth=MarketBreadth(
                up_count=up_count,
                down_count=down_count,
                limit_up_count=sum(1 for value in pct_changes if value >= 9.8),
                limit_down_count=sum(1 for value in pct_changes if value <= -9.8),
            ),
            turnover_cny=turnover_cny,
            market_state_tags=self._build_market_tags(up_count, down_count, turnover_cny),
            raw_sectors=raw_sectors,
        )

    def _build_indices(self, index_df: object) -> list[IndexSnapshot]:
        targets = {"上证指数", "创业板指"}
        indices: list[IndexSnapshot] = []
        for _idx, row in index_df.iterrows():
            name = str(_pick(row, "名称", "指数名称"))
            if name not in targets:
                continue
            indices.append(
                IndexSnapshot(
                    name=name,
                    code=str(_pick(row, "代码")),
                    close=_to_float(_pick(row, "最新价", "收盘")),
                    pct_change=_to_float(_pick(row, "涨跌幅")),
                )
            )
        if not indices:
            raise ProviderFallbackError("AkShare 未返回核心指数")
        return indices

    def _build_sectors(self, sector_df: object) -> list[RawSectorInput]:
        sectors: list[RawSectorInput] = []
        for _idx, row in sector_df.head(10).iterrows():
            up_count = _to_float(_pick(row, "上涨家数"), 0.0)
            down_count = _to_float(_pick(row, "下跌家数"), 0.0)
            total_count = up_count + down_count
            stock_up_ratio = round(up_count / total_count, 2) if total_count > 0 else 0.0
            pct_change = _to_float(_pick(row, "涨跌幅"), 0.0)
            sectors.append(
                RawSectorInput(
                    name=str(_pick(row, "板块名称", "名称")),
                    pct_change=pct_change,
                    limit_up_count=0,
                    stock_up_ratio=stock_up_ratio,
                    turnover_change=0.0,
                    news_weight=min(max(abs(pct_change) / 8, 0.0), 1.0),
                )
            )
        if not sectors:
            raise ProviderFallbackError("AkShare 未返回板块数据")
        return sectors

    def _build_market_tags(self, up_count: int, down_count: int, turnover_cny: float) -> list[str]:
        tags: list[str] = []
        if up_count > down_count * 1.5:
            tags.append("普涨")
        elif down_count > up_count * 1.5:
            tags.append("普跌")
        else:
            tags.append("分化")
        tags.append("放量" if turnover_cny >= 10000 else "缩量")
        return tags
```

- [ ] **Step 4: Run AkShare tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/providers/market.py apps/api/tests/test_real_providers.py
git commit -m "feat: add akshare market provider"
```

---

### Task 4: Implement Anspire News Provider

**Files:**
- Modify: `apps/api/app/providers/news.py`
- Modify: `apps/api/tests/test_real_providers.py`

- [ ] **Step 1: Append Anspire provider tests**

Append to `apps/api/tests/test_real_providers.py`:

```python
from app.providers.news import AnspireNewsProvider


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise ProviderFallbackError(f"Anspire HTTP {self.status_code}")

    def json(self) -> dict[str, object]:
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.last_headers: dict[str, str] = {}
        self.last_params: dict[str, object] = {}

    def get(self, _url: str, headers: dict[str, str], params: dict[str, object], timeout: float) -> FakeResponse:
        self.last_headers = headers
        self.last_params = params
        return self.response


def test_anspire_provider_maps_results_to_news_items() -> None:
    client = FakeHttpClient(
        FakeResponse(
            200,
            {
                "data": [
                    {
                        "title": "机器人产业链催化增强",
                        "url": "https://example.com/robot",
                        "source": "财联社",
                        "summary": "机器人方向出现政策催化。",
                        "published_at": "2026-05-26T14:30:00+08:00",
                    }
                ]
            },
        )
    )
    provider = AnspireNewsProvider(
        api_key="secret-key",
        base_url="https://plugin.anspire.cn/api/ntsearch/search",
        top_k=5,
        lookback_hours=36,
        http_client=client,
    )

    items = provider.search_sector_news("机器人", "2026-05-26")

    assert client.last_headers["Authorization"] == "Bearer secret-key"
    assert client.last_params["query"] == "机器人 A股"
    assert client.last_params["top_k"] == 5
    assert items[0].title == "机器人产业链催化增强"
    assert items[0].source == "财联社"
    assert items[0].matched_sector == "机器人"
    assert items[0].weight == 0.9


def test_anspire_provider_rejects_missing_key() -> None:
    provider = AnspireNewsProvider(api_key="")

    with pytest.raises(ProviderFallbackError, match="ANSPIRE_API_KEY"):
        provider.search_sector_news("机器人", "2026-05-26")


def test_anspire_provider_rejects_empty_results() -> None:
    provider = AnspireNewsProvider(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeResponse(200, {"data": []})),
    )

    with pytest.raises(ProviderFallbackError, match="无结果"):
        provider.search_sector_news("机器人", "2026-05-26")
```

- [ ] **Step 2: Run Anspire tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py::test_anspire_provider_maps_results_to_news_items tests/test_real_providers.py::test_anspire_provider_rejects_missing_key tests/test_real_providers.py::test_anspire_provider_rejects_empty_results -v
```

Expected: FAIL because `AnspireNewsProvider` does not exist.

- [ ] **Step 3: Implement Anspire provider**

Modify `apps/api/app/providers/news.py` imports:

```python
from datetime import datetime, timedelta
from typing import Any, Protocol

import httpx
```

Add after `FakeNewsProvider`:

```python
class AnspireNewsProvider:
    provider_name = "anspire"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://plugin.anspire.cn/api/ntsearch/search",
        top_k: int = 10,
        lookback_hours: int = 36,
        timeout_seconds: float = 12,
        http_client: object | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.top_k = top_k
        self.lookback_hours = lookback_hours
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client or httpx.Client()

    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        if not self.api_key:
            raise ProviderFallbackError("ANSPIRE_API_KEY 未配置")

        to_time = datetime.fromisoformat(f"{trade_date}T23:59:59")
        from_time = to_time - timedelta(hours=self.lookback_hours)
        response = self.http_client.get(
            self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={
                "query": f"{sector_name} A股",
                "top_k": self.top_k,
                "search_type": "hybrid",
                "FromTime": from_time.isoformat(),
                "ToTime": to_time.isoformat(),
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ProviderFallbackError(f"Anspire 请求失败: {exc}") from exc

        raw_items = self._extract_items(payload)
        if not raw_items:
            raise ProviderFallbackError("Anspire 无结果")

        return [self._to_news_item(raw_item, sector_name) for raw_item in raw_items[: self.top_k]]

    def _extract_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data") or payload.get("results") or payload.get("items")
        if isinstance(data, dict):
            nested = data.get("list") or data.get("items") or data.get("results")
            data = nested
        if not isinstance(data, list):
            raise ProviderFallbackError("Anspire 响应结构异常")
        return [item for item in data if isinstance(item, dict)]

    def _to_news_item(self, raw_item: dict[str, Any], sector_name: str) -> NewsItem:
        title = str(raw_item.get("title") or raw_item.get("name") or "未命名新闻")
        url = str(raw_item.get("url") or raw_item.get("link") or "")
        summary = str(raw_item.get("summary") or raw_item.get("snippet") or raw_item.get("content") or title)
        source = raw_item.get("source") or raw_item.get("site")
        source_text = str(source) if source is not None else None
        return NewsItem(
            title=title,
            url=url,
            source=source_text,
            summary=summary,
            published_at=raw_item.get("published_at") or raw_item.get("publish_time") or raw_item.get("time"),
            matched_sector=sector_name,
            weight=self._source_weight(source_text),
        )

    def _source_weight(self, source: str | None) -> float:
        if not source:
            return 0.5
        trusted_sources = ("财联社", "东方财富", "证券时报", "上海证券报", "上证报", "交易所")
        return 0.9 if any(name in source for name in trusted_sources) else 0.6
```

Also import `ProviderFallbackError` from market at top:

```python
from app.providers.market import ProviderFallbackError, ProviderStatus
```

- [ ] **Step 4: Run Anspire tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/providers/news.py apps/api/tests/test_real_providers.py
git commit -m "feat: add anspire news provider"
```

---

### Task 5: Add Provider Factory and Settings

**Files:**
- Modify: `apps/api/app/config.py`
- Modify: `.env.example`
- Create: `apps/api/app/providers/factory.py`
- Modify: `apps/api/tests/test_real_providers.py`

- [ ] **Step 1: Append provider factory tests**

Append to `apps/api/tests/test_real_providers.py`:

```python
from app.config import Settings
from app.providers.factory import create_provider_bundle
from app.providers.market import AkShareMarketDataProvider, FallbackMarketDataProvider
from app.providers.news import AnspireNewsProvider, FallbackNewsProvider


def test_provider_factory_uses_real_providers_by_default() -> None:
    settings = Settings(
        market_provider="akshare",
        news_provider="anspire",
        provider_fallback_enabled=True,
        anspire_api_key="secret-key",
    )

    bundle = create_provider_bundle(settings)

    assert isinstance(bundle.market_provider, FallbackMarketDataProvider)
    assert isinstance(bundle.market_provider.primary, AkShareMarketDataProvider)
    assert isinstance(bundle.news_provider, FallbackNewsProvider)
    assert isinstance(bundle.news_provider.primary, AnspireNewsProvider)


def test_provider_factory_can_force_fake_providers() -> None:
    settings = Settings(market_provider="fake", news_provider="fake")

    bundle = create_provider_bundle(settings)

    assert isinstance(bundle.market_provider, FakeMarketDataProvider)
    assert isinstance(bundle.news_provider, FakeNewsProvider)
```

- [ ] **Step 2: Run factory tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py::test_provider_factory_uses_real_providers_by_default tests/test_real_providers.py::test_provider_factory_can_force_fake_providers -v
```

Expected: FAIL because settings and factory do not exist.

- [ ] **Step 3: Add settings**

Modify `apps/api/app/config.py` `Settings`:

```python
    market_provider: str = "akshare"
    provider_fallback_enabled: bool = True
    provider_timeout_seconds: float = 12
    anspire_base_url: str = "https://plugin.anspire.cn/api/ntsearch/search"
```

Keep existing `news_provider`, `anspire_api_key`, `news_top_k`, `news_lookback_hours` fields.

Modify `.env.example` to include:

```dotenv
MARKET_PROVIDER=akshare
PROVIDER_FALLBACK_ENABLED=true
PROVIDER_TIMEOUT_SECONDS=12
ANSPIRE_BASE_URL=https://plugin.anspire.cn/api/ntsearch/search
```

- [ ] **Step 4: Implement provider factory**

Create `apps/api/app/providers/factory.py`:

```python
from dataclasses import dataclass

from app.config import Settings
from app.providers.llm import FakeLLMProvider, LLMProvider
from app.providers.market import (
    AkShareMarketDataProvider,
    FakeMarketDataProvider,
    FallbackMarketDataProvider,
    MarketDataProvider,
)
from app.providers.news import AnspireNewsProvider, FakeNewsProvider, FallbackNewsProvider, NewsProvider


@dataclass(frozen=True)
class ProviderBundle:
    market_provider: MarketDataProvider
    news_provider: NewsProvider
    llm_provider: LLMProvider


def create_provider_bundle(settings: Settings) -> ProviderBundle:
    market_provider = _create_market_provider(settings)
    news_provider = _create_news_provider(settings)
    return ProviderBundle(
        market_provider=market_provider,
        news_provider=news_provider,
        llm_provider=FakeLLMProvider(),
    )


def _create_market_provider(settings: Settings) -> MarketDataProvider:
    if settings.market_provider == "fake":
        return FakeMarketDataProvider()
    if settings.market_provider == "akshare":
        return FallbackMarketDataProvider(
            primary=AkShareMarketDataProvider(),
            fallback=FakeMarketDataProvider(),
            fallback_enabled=settings.provider_fallback_enabled,
        )
    raise ValueError(f"Unsupported MARKET_PROVIDER: {settings.market_provider}")


def _create_news_provider(settings: Settings) -> NewsProvider:
    if settings.news_provider == "fake":
        return FakeNewsProvider()
    if settings.news_provider == "anspire":
        return FallbackNewsProvider(
            primary=AnspireNewsProvider(
                api_key=settings.anspire_api_key,
                base_url=settings.anspire_base_url,
                top_k=settings.news_top_k,
                lookback_hours=settings.news_lookback_hours,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            fallback=FakeNewsProvider(),
            fallback_enabled=settings.provider_fallback_enabled,
        )
    raise ValueError(f"Unsupported NEWS_PROVIDER: {settings.news_provider}")
```

- [ ] **Step 5: Run factory tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .env.example apps/api/app/config.py apps/api/app/providers/factory.py apps/api/tests/test_real_providers.py
git commit -m "feat: create configured provider bundle"
```

---

### Task 6: Thread Provider Status Through Generator and API

**Files:**
- Modify: `apps/api/app/services/report_generator.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add API and snapshot tests**

Append to `apps/api/tests/test_report_api.py`:

```python

def test_create_close_report_api_returns_provider_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path))
    monkeypatch.setenv("MARKET_PROVIDER", "fake")
    monkeypatch.setenv("NEWS_PROVIDER", "fake")

    with TestClient(app) as client:
        response = client.post("/api/reports/close", json={"trade_date": "2026-05-26"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_status"]["market"] == {
        "provider": "fake",
        "status": "success",
        "fallback_used": False,
        "reason": None,
    }
    assert payload["provider_status"]["news"][0]["sector"] == "机器人"

    snapshot_path = Path(payload["assets"]["root"]) / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["provider_status"] == payload["provider_status"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_create_close_report_api_returns_provider_status -v
```

Expected: FAIL because API does not return `provider_status`.

- [ ] **Step 3: Update GeneratedReport and generator**

Modify `apps/api/app/services/report_generator.py` imports:

```python
from app.providers.market import ProviderStatus
from app.providers.news import SectorNewsResult
```

Update dataclass:

```python
@dataclass(frozen=True)
class GeneratedReport:
    report: ReportDTO
    validation: ValidationResult
    assets: AssetPaths
    provider_status: dict[str, object]
```

In `generate_close_report`, replace market snapshot call:

```python
        if hasattr(self.market_provider, "get_close_snapshot_with_status"):
            market_snapshot, market_status = self.market_provider.get_close_snapshot_with_status(trade_date)
        else:
            market_snapshot = self.market_provider.get_close_snapshot(trade_date)
            market_status = ProviderStatus(
                provider=getattr(self.market_provider, "provider_name", "fake"),
                status="success",
                fallback_used=False,
                reason=None,
            )
```

Replace news loop:

```python
        news_items = []
        news_statuses = []
        for sector in scored_sectors:
            if hasattr(self.news_provider, "search_sector_news_with_status"):
                sector_news = self.news_provider.search_sector_news_with_status(sector.name, trade_date)
            else:
                sector_news = SectorNewsResult(
                    sector=sector.name,
                    items=self.news_provider.search_sector_news(sector.name, trade_date),
                    status=ProviderStatus(
                        provider=getattr(self.news_provider, "provider_name", "fake"),
                        status="success",
                        fallback_used=False,
                        reason=None,
                    ),
                )
            news_items.extend(sector_news.items)
            news_statuses.append(
                {
                    "sector": sector_news.sector,
                    **sector_news.status.model_dump(mode="json"),
                }
            )
```

Before writing snapshot:

```python
        provider_status = {
            "market": market_status.model_dump(mode="json"),
            "news": news_statuses,
        }
```

Update snapshot write:

```python
                "provider_status": provider_status,
```

Update return:

```python
        return GeneratedReport(
            report=report,
            validation=validation,
            assets=assets,
            provider_status=provider_status,
        )
```

- [ ] **Step 4: Update main to use factory and return status**

Modify `apps/api/app/main.py` imports:

```python
from app.providers.factory import create_provider_bundle
```

Remove fake provider imports.

Replace provider construction:

```python
    providers = create_provider_bundle(settings)
    generator = ReportGenerator(
        reports_root=Path(settings.reports_root),
        market_provider=providers.market_provider,
        news_provider=providers.news_provider,
        llm_provider=providers.llm_provider,
    )
```

Add response field:

```python
        "provider_status": result.provider_status,
```

- [ ] **Step 5: Run API status test**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_create_close_report_api_returns_provider_status -v
```

Expected: PASS.

- [ ] **Step 6: Run report tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/services/report_generator.py apps/api/app/main.py apps/api/tests/test_report_api.py
git commit -m "feat: expose provider diagnostics"
```

---

### Task 7: Add Frontend Provider Diagnostics

**Files:**
- Modify: `apps/web/lib/types.ts`
- Create: `apps/web/components/ProviderStatusPanel.tsx`
- Modify: `apps/web/components/ReportPreview.tsx`

- [ ] **Step 1: Add frontend types**

Modify `apps/web/lib/types.ts` to add:

```ts
export type ProviderStatus = {
  provider: string;
  status: "success" | "fallback" | "disabled" | "failed";
  fallback_used: boolean;
  reason: string | null;
};

export type SectorProviderStatus = ProviderStatus & {
  sector: string;
};

export type ProviderStatusSummary = {
  market: ProviderStatus;
  news: SectorProviderStatus[];
};
```

Add to `CreateReportResponse`:

```ts
  provider_status: ProviderStatusSummary;
```

- [ ] **Step 2: Add ProviderStatusPanel component**

Create `apps/web/components/ProviderStatusPanel.tsx`:

```tsx
import type { ProviderStatusSummary, SectorProviderStatus } from "../lib/types";

export function ProviderStatusPanel({ status }: { status: ProviderStatusSummary }) {
  const newsFallbacks = status.news.filter((item) => item.fallback_used);
  const allReal = !status.market.fallback_used && newsFallbacks.length === 0;

  if (allReal) {
    return (
      <section className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
        真实数据源已使用：行情 {status.market.provider}，新闻 {summarizeNewsProviders(status.news)}。
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <div className="font-bold">数据源回退提示</div>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {status.market.fallback_used && (
          <li>
            行情源 {status.market.provider} 已回退 fake：{status.market.reason ?? "未知原因"}
          </li>
        )}
        {newsFallbacks.slice(0, 5).map((item) => (
          <li key={`${item.sector}-${item.provider}`}>
            新闻源 {item.provider}（{item.sector}）已回退 fake：{item.reason ?? "未知原因"}
          </li>
        ))}
        {newsFallbacks.length > 5 && <li>还有 {newsFallbacks.length - 5} 条新闻源回退。</li>}
      </ul>
    </section>
  );
}

function summarizeNewsProviders(items: SectorProviderStatus[]) {
  const providers = Array.from(new Set(items.map((item) => item.provider)));
  return providers.length > 0 ? providers.join("、") : "无新闻源";
}
```

- [ ] **Step 3: Render panel in report preview**

Modify `apps/web/components/ReportPreview.tsx`:

```tsx
import { ProviderStatusPanel } from "./ProviderStatusPanel";
```

Inside component after header/version area and before metrics:

```tsx
      <div className="mt-5">
        <ProviderStatusPanel status={result.provider_status} />
      </div>
```

- [ ] **Step 4: Run frontend typecheck**

Run:

```bash
corepack pnpm --filter @stock-review/web test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/types.ts apps/web/components/ProviderStatusPanel.tsx apps/web/components/ReportPreview.tsx
git commit -m "feat: show provider diagnostics in frontend"
```

---

### Task 8: Document and Verify v0.2 Real Providers

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: Update README**

Add to `README.md` after backend startup:

```markdown
## Real Data Providers

v0.2 defaults to real providers with fake fallback:

```dotenv
MARKET_PROVIDER=akshare
NEWS_PROVIDER=anspire
PROVIDER_FALLBACK_ENABLED=true
ANSPIRE_API_KEY=
```

Behavior:

- AkShare is used only for the current date/current close snapshot in v0.2.
- Historical dates fall back to fake data and show a provider diagnostic in the frontend.
- Anspire requires `ANSPIRE_API_KEY`; missing key, API errors, timeouts, and empty results fall back to fake news.
- Provider diagnostics are returned in `provider_status` and saved in `snapshot.json`.
```

- [ ] **Step 2: Run full backend checks**

Run:

```bash
cd apps/api
uv run pytest -v
uv run ruff check .
```

Expected: PASS.

- [ ] **Step 3: Run frontend checks**

Run:

```bash
corepack pnpm --filter @stock-review/web test
corepack pnpm --filter @stock-review/web lint
```

Expected: PASS.

- [ ] **Step 4: Run fallback API smoke**

Run:

```bash
cd apps/api
MARKET_PROVIDER=akshare NEWS_PROVIDER=anspire ANSPIRE_API_KEY= uv run python - <<'PY'
from fastapi.testclient import TestClient
from app.config import get_settings
from app.main import app

get_settings.cache_clear()
with TestClient(app) as client:
    response = client.post('/api/reports/close', json={'trade_date': '2026-05-25'})
response.raise_for_status()
payload = response.json()
print(payload['provider_status'])
assert payload['provider_status']['market']['fallback_used'] is True
assert payload['provider_status']['news'][0]['fallback_used'] is True
PY
```

Expected: prints provider diagnostics with AkShare historical-date fallback and Anspire missing-key fallback.

- [ ] **Step 5: Commit**

```bash
git add README.md .env.example
git commit -m "docs: document real data provider fallback"
```

---

## Self-Review

Spec coverage:

- Default real providers with fake fallback: Tasks 2, 5, 6.
- AkShare current-date only behavior: Task 3.
- Anspire API key/search behavior: Task 4.
- Detailed frontend fallback reasons: Task 7.
- Snapshot/API `provider_status`: Task 6.
- Tests avoiding real network: Tasks 1-6.
- Docs and smoke: Task 8.

Placeholder scan:

- No `TBD`, `TODO`, or vague “add tests” placeholders remain.
- Each task includes exact files, code blocks, commands, expected outcomes, and commit commands.

Type consistency:

- Backend `ProviderStatus` maps to frontend `ProviderStatus`.
- `SectorNewsResult.status` uses the same provider status model.
- API field is consistently named `provider_status`.
- `fallback_used` uses snake_case because API responses currently use backend JSON field names.
