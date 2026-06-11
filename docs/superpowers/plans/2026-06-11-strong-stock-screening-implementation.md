# Strong Stock Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a manual Web admin module that screens 20-day limit-up strong-stock candidates and applies empty-position discipline only to imported watchlist or manually supplied holdings.

**Architecture:** Add one focused backend service for strong-stock rules, with small provider adapters for candidate discovery and daily K-line data. Expose one FastAPI endpoint and one compact frontend panel wired into the existing admin homepage. Keep the empty rule out of new-stock screening by modeling it as a separate watchlist risk action.

**Tech Stack:** FastAPI, Pydantic, pytest, existing THSDK provider pattern, httpx, Next.js React, TypeScript, node:test source-structure tests.

---

## File Structure

- Create `apps/api/app/services/strong_stock_screening.py`
  - Defines request-independent models, pure rule functions, provider adapters, and `StrongStockScreeningService`.
  - Keeps `status` for screening separate from `risk_action` for watchlist or holding risk.
- Modify `apps/api/app/main.py`
  - Adds `StrongStockScreenRequest`.
  - Adds `_strong_stock_screening_service()`.
  - Adds `POST /api/strong-stocks/screen`.
- Create `apps/api/tests/test_strong_stock_screening.py`
  - Tests pure scoring, status, and risk-action behavior.
- Create `apps/api/tests/test_strong_stock_screening_api.py`
  - Tests API success, data-source failure, limit validation, and no `empty` status in screening items.
- Modify `apps/web/lib/types.ts`
  - Adds strong-stock response types.
- Modify `apps/web/lib/api.ts`
  - Adds `screenStrongStocks(tradeDate, limit)`.
- Create `apps/web/components/StrongStockScreeningPanel.tsx`
  - Displays run button, summaries, candidate results, watchlist risk results, and errors.
- Modify `apps/web/app/page.tsx`
  - Adds state, handler, import, and renders the panel in the left operations column near watchlist import.
- Create `apps/web/lib/strongStockScreeningPanel.test.ts`
  - Uses the existing source-assertion style to verify API/type/component/page wiring.

Existing dirty files related to a-stock-data vendor update must be preserved. Implementation commits should stage only files touched by this plan plus any files they intentionally depend on.

## Scope Check

This spec contains two related outputs from the same rule engine:

- new-stock screening results: `status = focus | wait_pullback | reduce_risk | data_incomplete`
- watchlist or holding risk results: `risk_action = hold_watch | reduce | empty`

They belong in one plan because they share K-line metrics and rule definitions, but each output has a separate model and test assertions to prevent scope drift.

### Task 1: Core Rule Models And Pure Screening Logic

**Files:**
- Create: `apps/api/app/services/strong_stock_screening.py`
- Test: `apps/api/tests/test_strong_stock_screening.py`

- [ ] **Step 1: Write failing pure-rule tests**

Create `apps/api/tests/test_strong_stock_screening.py` with these tests:

```python
from app.services.strong_stock_screening import (
    KlineBar,
    StrongStockCandidate,
    analyze_screening_item,
    analyze_watchlist_risk,
)


def _bars(closes: list[float], *, volumes: list[float] | None = None) -> list[KlineBar]:
    output = []
    for index, close in enumerate(closes):
        previous = closes[index - 1] if index else close
        open_price = previous * 0.99 if close >= previous else previous * 1.02
        volume = volumes[index] if volumes is not None else 1_000_000 + index * 10_000
        output.append(
            KlineBar(
                date=f"2026-01-{(index % 28) + 1:02d}",
                open=round(open_price, 2),
                close=round(close, 2),
                high=round(max(open_price, close) * 1.03, 2),
                low=round(min(open_price, close) * 0.98, 2),
                volume=volume,
            )
        )
    return output


def test_focus_candidate_rewards_trend_volume_and_new_high() -> None:
    closes = [10 + index * 0.05 for index in range(220)]
    bars = _bars(closes)
    candidate = StrongStockCandidate(symbol="603890.SH", name="春秋电子", limit_up_evidence=["20日内涨停"])

    item = analyze_screening_item(candidate, bars, trade_date="2026-06-11")

    assert item.status == "focus"
    assert item.score >= 70
    assert "20日内涨停" in item.rule_hits
    assert "收盘价在MA5上方" in item.rule_hits
    assert "200日新高" in item.rule_hits
    assert item.metrics["is_200d_high"] is True


def test_volume_stall_marks_reduce_risk_without_empty_status() -> None:
    closes = [10 + index * 0.05 for index in range(215)] + [20.0, 20.02, 20.03, 20.04, 20.05]
    volumes = [1_000_000 for _ in range(219)] + [4_000_000]
    candidate = StrongStockCandidate(symbol="002000.SZ", name="示例股份", limit_up_evidence=["20日内涨停"])

    item = analyze_screening_item(candidate, _bars(closes, volumes=volumes), trade_date="2026-06-11")

    assert item.status == "reduce_risk"
    assert "放量滞涨" in item.risk_flags
    assert item.status != "empty"


def test_empty_rule_only_applies_to_watchlist_risk() -> None:
    closes = [20 - index * 0.05 for index in range(220)]
    bars = _bars(closes)
    candidate = StrongStockCandidate(symbol="002000.SZ", name="示例股份", limit_up_evidence=["20日内涨停"])

    screening_item = analyze_screening_item(candidate, bars, trade_date="2026-06-11")
    risk_item = analyze_watchlist_risk(candidate, bars, trade_date="2026-06-11")

    assert screening_item.status in {"wait_pullback", "reduce_risk"}
    assert screening_item.status != "empty"
    assert risk_item.risk_action == "empty"
    assert "MA5拐头向下" in risk_item.risk_flags
    assert "跌在均线下方" in risk_item.risk_flags


def test_short_kline_returns_data_incomplete() -> None:
    candidate = StrongStockCandidate(symbol="603890.SH", name="春秋电子", limit_up_evidence=["20日内涨停"])

    item = analyze_screening_item(candidate, _bars([10, 10.5, 11]), trade_date="2026-06-11")

    assert item.status == "data_incomplete"
    assert item.data_status == "incomplete"
    assert "K线不足220日" in item.risk_flags
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_strong_stock_screening.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.strong_stock_screening'`.

- [ ] **Step 3: Implement minimal models and pure rules**

Create `apps/api/app/services/strong_stock_screening.py` with this core structure:

```python
from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel, Field


ScreenStatus = Literal["focus", "wait_pullback", "reduce_risk", "data_incomplete"]
RiskAction = Literal["hold_watch", "reduce", "empty"]
SourceStatusValue = Literal["success", "failed", "disabled"]


class StrongStockCandidate(BaseModel):
    symbol: str
    name: str
    limit_up_evidence: list[str] = Field(default_factory=list)
    board_note: str | None = None


class KlineBar(BaseModel):
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None


class StrongStockScreeningItem(BaseModel):
    symbol: str
    name: str
    status: ScreenStatus
    score: int
    rule_hits: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    intraday_notes: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    data_status: Literal["complete", "incomplete"] = "complete"


class StrongStockRiskItem(BaseModel):
    symbol: str
    name: str
    risk_action: RiskAction
    risk_flags: list[str] = Field(default_factory=list)
    intraday_notes: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class StrongStockSourceStatus(BaseModel):
    source: str
    status: SourceStatusValue
    detail: str


class StrongStockScreeningResult(BaseModel):
    trade_date: str
    source_status: list[StrongStockSourceStatus] = Field(default_factory=list)
    items: list[StrongStockScreeningItem] = Field(default_factory=list)
    watchlist_risk_items: list[StrongStockRiskItem] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))


class StrongStockDataUnavailable(RuntimeError):
    pass


def analyze_screening_item(
    candidate: StrongStockCandidate,
    bars: list[KlineBar],
    trade_date: str,
) -> StrongStockScreeningItem:
    if len(bars) < 220:
        return StrongStockScreeningItem(
            symbol=candidate.symbol,
            name=candidate.name,
            status="data_incomplete",
            score=0,
            rule_hits=list(candidate.limit_up_evidence),
            risk_flags=["K线不足220日"],
            intraday_notes=_intraday_notes("wait_pullback"),
            metrics={},
            data_status="incomplete",
        )

    enriched = _with_moving_averages(bars)
    latest = enriched[-1]
    previous = enriched[-2]
    recent20 = enriched[-20:]
    recent200 = enriched[-200:]
    score = 0
    rule_hits = list(candidate.limit_up_evidence or ["20日内涨停"])
    risk_flags: list[str] = []

    red_body, green_body, up_volume, down_volume = _body_and_volume_metrics(recent20)
    if red_body > green_body:
        score += 25
        rule_hits.append("阳线实体强于阴线")
    else:
        risk_flags.append("阴线实体不弱")
    if up_volume > down_volume:
        score += 15
        rule_hits.append("上涨日量能强于下跌日")
    else:
        risk_flags.append("下跌日放量")

    if latest.close > (latest.ma5 or latest.close):
        score += 20
        rule_hits.append("收盘价在MA5上方")
    else:
        risk_flags.append("跌在均线下方")

    is_200d_high = latest.high >= max(bar.high for bar in recent200)
    if is_200d_high:
        score += 20
        rule_hits.append("200日新高")

    volume_ratio_5d = latest.volume / max(mean(bar.volume for bar in enriched[-5:]), 1)
    daily_pct = (latest.close - previous.close) / previous.close * 100 if previous.close else 0.0
    if daily_pct > 0 and volume_ratio_5d >= 1.2:
        score += 15
        rule_hits.append("放量上涨")
    if volume_ratio_5d >= 1.8 and daily_pct < 1.0:
        risk_flags.append("放量滞涨")
        score -= 20

    ma5_down = (latest.ma5 or latest.close) < (previous.ma5 or previous.close)
    if ma5_down:
        risk_flags.append("MA5拐头向下")
        score -= 20
    if latest.close < (latest.ma10 or latest.close):
        risk_flags.append("跌在均线下方")
        score -= 15
    if latest.close < latest.open and abs(latest.open - latest.close) / max(latest.open, 1) >= 0.03:
        risk_flags.append("实体阴线")
        score -= 15

    score = max(0, min(100, round(score)))
    if "放量滞涨" in risk_flags:
        status: ScreenStatus = "reduce_risk"
    elif ma5_down or latest.close < (latest.ma10 or latest.close):
        status = "wait_pullback"
    elif score >= 70:
        status = "focus"
    else:
        status = "wait_pullback"

    return StrongStockScreeningItem(
        symbol=candidate.symbol,
        name=candidate.name,
        status=status,
        score=score,
        rule_hits=_dedupe(rule_hits),
        risk_flags=_dedupe(risk_flags),
        intraday_notes=_intraday_notes(status),
        metrics={
            "close": latest.close,
            "ma5": latest.ma5,
            "ma10": latest.ma10,
            "ma20": latest.ma20,
            "volume_ratio_5d": round(volume_ratio_5d, 2),
            "is_200d_high": is_200d_high,
        },
    )


def analyze_watchlist_risk(
    candidate: StrongStockCandidate,
    bars: list[KlineBar],
    trade_date: str,
) -> StrongStockRiskItem:
    if len(bars) < 20:
        return StrongStockRiskItem(
            symbol=candidate.symbol,
            name=candidate.name,
            risk_action="hold_watch",
            risk_flags=["K线不足20日"],
            intraday_notes=_intraday_notes("wait_pullback"),
        )
    enriched = _with_moving_averages(bars)
    latest = enriched[-1]
    previous = enriched[-2]
    risk_flags: list[str] = []
    ma5_down = (latest.ma5 or latest.close) < (previous.ma5 or previous.close)
    if ma5_down:
        risk_flags.append("MA5拐头向下")
    if latest.close < (latest.ma5 or latest.close) or latest.close < (latest.ma10 or latest.close):
        risk_flags.append("跌在均线下方")
    if latest.close < latest.open and abs(latest.open - latest.close) / max(latest.open, 1) >= 0.03:
        risk_flags.append("实体阴线且断板未修复")
    if {"MA5拐头向下", "跌在均线下方"} <= set(risk_flags) or "实体阴线且断板未修复" in risk_flags:
        action: RiskAction = "empty"
    elif risk_flags:
        action = "reduce"
    else:
        action = "hold_watch"
    return StrongStockRiskItem(
        symbol=candidate.symbol,
        name=candidate.name,
        risk_action=action,
        risk_flags=risk_flags,
        intraday_notes=_intraday_notes(action),
        metrics={"close": latest.close, "ma5": latest.ma5, "ma10": latest.ma10, "ma20": latest.ma20},
    )
```

Add helpers in the same file:

```python
def _with_moving_averages(bars: list[KlineBar]) -> list[KlineBar]:
    output: list[KlineBar] = []
    for index, bar in enumerate(bars):
        closes = [item.close for item in bars[: index + 1]]
        output.append(
            bar.model_copy(
                update={
                    "ma5": bar.ma5 if bar.ma5 is not None else _ma(closes, 5),
                    "ma10": bar.ma10 if bar.ma10 is not None else _ma(closes, 10),
                    "ma20": bar.ma20 if bar.ma20 is not None else _ma(closes, 20),
                }
            )
        )
    return output


def _ma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return round(mean(values[-window:]), 4)


def _body_and_volume_metrics(bars: list[KlineBar]) -> tuple[float, float, float, float]:
    red_bodies = [bar.close - bar.open for bar in bars if bar.close > bar.open]
    green_bodies = [bar.open - bar.close for bar in bars if bar.open > bar.close]
    up_volumes = [bar.volume for bar in bars if bar.close > bar.open]
    down_volumes = [bar.volume for bar in bars if bar.open > bar.close]
    return (
        mean(red_bodies) if red_bodies else 0.0,
        mean(green_bodies) if green_bodies else 0.0,
        mean(up_volumes) if up_volumes else 0.0,
        mean(down_volumes) if down_volumes else 0.0,
    )


def _intraday_notes(status_or_action: str) -> list[str]:
    if status_or_action == "focus":
        return ["买点优先看分歧回落承接，不追红盘急拉"]
    if status_or_action in {"reduce_risk", "reduce", "empty"}:
        return ["冲高反弹优先兑现，不在绿盘恐慌卖出"]
    return ["趋势或买点不明确，等待回踩承接确认"]


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
```

- [ ] **Step 4: Run pure-rule tests**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_strong_stock_screening.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add apps/api/app/services/strong_stock_screening.py apps/api/tests/test_strong_stock_screening.py
git commit -m "feat: add strong stock screening rules"
```

### Task 2: Candidate And K-Line Provider Adapters

**Files:**
- Modify: `apps/api/app/services/strong_stock_screening.py`
- Test: `apps/api/tests/test_strong_stock_screening.py`

- [ ] **Step 1: Add failing adapter parser tests**

Append these tests to `apps/api/tests/test_strong_stock_screening.py`:

```python
from app.services.strong_stock_screening import parse_baidu_kline_payload, parse_thsdk_candidate_rows


def test_parse_thsdk_candidate_rows_filters_st_and_normalizes_symbols() -> None:
    rows = [
        {"股票简称": "*ST美丽", "股票代码": "000010.SZ", "涨停[20260611]": "涨停"},
        {"股票简称": "春秋电子", "股票代码": "603890.SH", "涨停[20260611]": "涨停"},
        {"名称": "天健集团", "代码": "000090", "连续涨停天数[20260611]": 2},
    ]

    candidates = parse_thsdk_candidate_rows(rows)

    assert [item.symbol for item in candidates] == ["603890.SH", "000090.SZ"]
    assert candidates[0].name == "春秋电子"
    assert "20日内涨停" in candidates[0].limit_up_evidence


def test_parse_baidu_kline_payload_maps_ma_fields() -> None:
    payload = {
        "Result": {
            "newMarketData": {
                "keys": ["time", "open", "close", "high", "low", "volume", "amount", "ma5avgprice", "ma10avgprice", "ma20avgprice"],
                "marketData": "2026-06-10,10,11,11.5,9.8,10000,1,10.5,10.2,10.0;2026-06-11,11,12,12.5,10.8,15000,1,11.1,10.5,10.1",
            }
        }
    }

    bars = parse_baidu_kline_payload(payload)

    assert len(bars) == 2
    assert bars[-1].date == "2026-06-11"
    assert bars[-1].close == 12
    assert bars[-1].ma5 == 11.1
    assert bars[-1].volume == 15000
```

- [ ] **Step 2: Run parser tests to verify they fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_strong_stock_screening.py::test_parse_thsdk_candidate_rows_filters_st_and_normalizes_symbols tests/test_strong_stock_screening.py::test_parse_baidu_kline_payload_maps_ma_fields
```

Expected: FAIL with import errors for `parse_thsdk_candidate_rows` and `parse_baidu_kline_payload`.

- [ ] **Step 3: Implement parser functions and provider classes**

Add imports:

```python
import re
import time
from collections.abc import Protocol

import httpx
```

Add interfaces and provider implementations:

```python
BAIDU_KLINE_URL = "https://finance.pae.baidu.com/selfselect/getstockquotation"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"


class CandidateProvider(Protocol):
    source_name: str

    def get_candidates(self, trade_date: str) -> list[StrongStockCandidate]:
        ...


class KlineProvider(Protocol):
    source_name: str

    def get_klines(self, symbol: str, count: int = 220) -> list[KlineBar]:
        ...


class ThsdkStrongStockCandidateProvider:
    source_name = "THSDK 问财"

    def __init__(self, client_factory: object | None = None) -> None:
        self.client_factory = client_factory

    @classmethod
    def from_installed_package(cls) -> "ThsdkStrongStockCandidateProvider":
        try:
            from thsdk import THS
        except ModuleNotFoundError:
            return cls(client_factory=None)
        return cls(client_factory=THS)

    def get_candidates(self, trade_date: str) -> list[StrongStockCandidate]:
        if self.client_factory is None:
            raise StrongStockDataUnavailable("THSDK 未安装，无法查询20日内涨停候选池")
        query = "20日内有过涨停，非ST，A股"
        with self.client_factory() as ths:
            response = ths.wencai_nlp(query)
        if not getattr(response, "success", False):
            raise StrongStockDataUnavailable(str(getattr(response, "error", "") or "THSDK 问财返回失败"))
        return parse_thsdk_candidate_rows(getattr(response, "data", None) or [])


class BaiduKlineProvider:
    source_name = "百度股市通K线"

    def __init__(self, timeout_seconds: float = 12, http_client: object | None = None, sleep_seconds: float = 0.15) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()
        self.sleep_seconds = sleep_seconds

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def get_klines(self, symbol: str, count: int = 220) -> list[KlineBar]:
        response = self.http_client.get(
            BAIDU_KLINE_URL,
            headers={
                "User-Agent": UA,
                "Accept": "application/vnd.finance-web.v1+json",
                "Origin": "https://gushitong.baidu.com",
                "Referer": "https://gushitong.baidu.com/",
            },
            params={
                "all": "1",
                "isIndex": "false",
                "isBk": "false",
                "isBlock": "false",
                "isFutures": "false",
                "isStock": "true",
                "newFormat": "1",
                "group": "quotation_kline_ab",
                "finClientType": "pc",
                "code": _symbol_code(symbol),
                "start_time": "",
                "ktype": "1",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)
        return parse_baidu_kline_payload(response.json())[-count:]
```

Add parser helpers:

```python
def parse_thsdk_candidate_rows(rows: object) -> list[StrongStockCandidate]:
    if not isinstance(rows, list):
        return []
    candidates: list[StrongStockCandidate] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _text_value(row, "股票简称", "名称", "name")
        code = _text_value(row, "股票代码", "代码", "code")
        if not name or not code or "ST" in name.upper():
            continue
        symbol = _normalize_symbol(code)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        note = _limit_up_note(row)
        candidates.append(
            StrongStockCandidate(
                symbol=symbol,
                name=name,
                limit_up_evidence=["20日内涨停"],
                board_note=note,
            )
        )
    return candidates


def parse_baidu_kline_payload(payload: dict[str, Any]) -> list[KlineBar]:
    market_data = payload.get("Result", {}).get("newMarketData", {})
    keys = market_data.get("keys", [])
    raw_rows = str(market_data.get("marketData") or "").split(";")
    bars: list[KlineBar] = []
    for raw in raw_rows:
        values = raw.split(",")
        if len(values) < len(keys) or not raw.strip():
            continue
        item = dict(zip(keys, values, strict=False))
        bar = KlineBar(
            date=str(item.get("time") or ""),
            open=_float(item.get("open")) or 0.0,
            close=_float(item.get("close")) or 0.0,
            high=_float(item.get("high")) or 0.0,
            low=_float(item.get("low")) or 0.0,
            volume=_float(item.get("volume")) or 0.0,
            ma5=_float(item.get("ma5avgprice")),
            ma10=_float(item.get("ma10avgprice")),
            ma20=_float(item.get("ma20avgprice")),
        )
        if bar.date and bar.close > 0:
            bars.append(bar)
    return bars
```

Add value helpers:

```python
def _text_value(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _limit_up_note(row: dict[str, Any]) -> str | None:
    for key, value in row.items():
        if "涨停" in str(key) and value not in (None, ""):
            return f"{key}: {value}"
    return None


def _normalize_symbol(value: str) -> str:
    code = value.strip().upper()
    if "." in code:
        raw, exchange = code.split(".", 1)
        return f"{raw.zfill(6)}.{exchange}"
    code = re.sub(r"\D", "", code)
    if len(code) != 6:
        return ""
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    if code.startswith(("8", "4")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _symbol_code(symbol: str) -> str:
    return symbol.strip().split(".", 1)[0]


def _float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_strong_stock_screening.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add apps/api/app/services/strong_stock_screening.py apps/api/tests/test_strong_stock_screening.py
git commit -m "feat: add strong stock data adapters"
```

### Task 3: Screening Service And FastAPI Endpoint

**Files:**
- Modify: `apps/api/app/services/strong_stock_screening.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_strong_stock_screening_api.py`

- [ ] **Step 1: Add failing API tests**

Create `apps/api/tests/test_strong_stock_screening_api.py`:

```python
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.strong_stock_screening import (
    StrongStockDataUnavailable,
    StrongStockScreeningItem,
    StrongStockScreeningResult,
    StrongStockRiskItem,
    StrongStockSourceStatus,
)


class FakeStrongStockService:
    def screen(self, trade_date: str, limit: int, watchlist_items: object | None = None) -> StrongStockScreeningResult:
        return StrongStockScreeningResult(
            trade_date=trade_date,
            source_status=[StrongStockSourceStatus(source="THSDK 问财", status="success", detail="返回 2 只 20 日涨停候选")],
            items=[
                StrongStockScreeningItem(
                    symbol="603890.SH",
                    name="春秋电子",
                    status="focus",
                    score=82,
                    rule_hits=["20日内涨停", "收盘价在MA5上方"],
                    risk_flags=[],
                    intraday_notes=["买点优先看分歧回落承接，不追红盘急拉"],
                    metrics={"is_200d_high": True},
                ),
                StrongStockScreeningItem(
                    symbol="002000.SZ",
                    name="示例股份",
                    status="reduce_risk",
                    score=56,
                    rule_hits=["20日内涨停"],
                    risk_flags=["放量滞涨"],
                    intraday_notes=["冲高反弹优先兑现，不在绿盘恐慌卖出"],
                    metrics={},
                ),
            ][:limit],
            watchlist_risk_items=[
                StrongStockRiskItem(
                    symbol="000001.SZ",
                    name="平安银行",
                    risk_action="empty",
                    risk_flags=["MA5拐头向下", "跌在均线下方"],
                )
            ],
        )


class FailingStrongStockService:
    def screen(self, trade_date: str, limit: int, watchlist_items: object | None = None) -> StrongStockScreeningResult:
        raise StrongStockDataUnavailable("THSDK 未安装，无法查询20日内涨停候选池")


@pytest.fixture
def injected_service() -> Iterator[None]:
    original = getattr(app.state, "strong_stock_screening_service", None)
    app.state.strong_stock_screening_service = FakeStrongStockService()
    try:
        yield
    finally:
        if original is None:
            delattr(app.state, "strong_stock_screening_service")
        else:
            app.state.strong_stock_screening_service = original


def test_strong_stock_screen_api_returns_screening_and_watchlist_risk(injected_service: None) -> None:
    with TestClient(app) as client:
        response = client.post("/api/strong-stocks/screen", json={"trade_date": "2026-06-11", "limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["trade_date"] == "2026-06-11"
    assert [item["symbol"] for item in payload["items"]] == ["603890.SH"]
    assert payload["items"][0]["status"] == "focus"
    assert payload["watchlist_risk_items"][0]["risk_action"] == "empty"
    assert all(item["status"] != "empty" for item in payload["items"])


def test_strong_stock_screen_api_maps_candidate_source_failure_to_503() -> None:
    original = getattr(app.state, "strong_stock_screening_service", None)
    app.state.strong_stock_screening_service = FailingStrongStockService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/strong-stocks/screen", json={"trade_date": "2026-06-11", "limit": 30})
    finally:
        if original is None:
            delattr(app.state, "strong_stock_screening_service")
        else:
            app.state.strong_stock_screening_service = original

    assert response.status_code == 503
    assert "THSDK 未安装" in response.text


def test_strong_stock_screen_api_validates_limit() -> None:
    with TestClient(app) as client:
        response = client.post("/api/strong-stocks/screen", json={"trade_date": "2026-06-11", "limit": 0})

    assert response.status_code == 422
```

- [ ] **Step 2: Run API tests to verify they fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_strong_stock_screening_api.py
```

Expected: FAIL with `404 Not Found` for `/api/strong-stocks/screen`.

- [ ] **Step 3: Implement `StrongStockScreeningService`**

Append to `apps/api/app/services/strong_stock_screening.py`:

```python
class StrongStockScreeningService:
    def __init__(
        self,
        candidate_provider: CandidateProvider,
        kline_provider: KlineProvider,
    ) -> None:
        self.candidate_provider = candidate_provider
        self.kline_provider = kline_provider

    def close(self) -> None:
        close = getattr(self.kline_provider, "close", None)
        if callable(close):
            close()

    def screen(
        self,
        trade_date: str,
        limit: int = 30,
        watchlist_items: object | None = None,
    ) -> StrongStockScreeningResult:
        candidates = self.candidate_provider.get_candidates(trade_date)
        if not candidates:
            raise StrongStockDataUnavailable("20日内涨停候选池为空")
        items: list[StrongStockScreeningItem] = []
        source_status = [
            StrongStockSourceStatus(
                source=getattr(self.candidate_provider, "source_name", "candidate_provider"),
                status="success",
                detail=f"返回 {len(candidates)} 只 20 日涨停候选",
            )
        ]
        kline_failures = 0
        for candidate in candidates:
            try:
                bars = self.kline_provider.get_klines(candidate.symbol, count=220)
            except Exception:
                kline_failures += 1
                continue
            item = analyze_screening_item(candidate, bars, trade_date=trade_date)
            if item.status != "data_incomplete":
                items.append(item)
        if kline_failures:
            source_status.append(
                StrongStockSourceStatus(
                    source=getattr(self.kline_provider, "source_name", "kline_provider"),
                    status="failed",
                    detail=f"{kline_failures} 只股票K线获取失败",
                )
            )
        ranked = sorted(items, key=lambda item: (item.status == "focus", item.score), reverse=True)[:limit]
        return StrongStockScreeningResult(
            trade_date=trade_date,
            source_status=source_status,
            items=ranked,
            watchlist_risk_items=self._watchlist_risks(watchlist_items, trade_date),
        )

    def _watchlist_risks(self, watchlist_items: object | None, trade_date: str) -> list[StrongStockRiskItem]:
        raw_items = getattr(watchlist_items, "items", watchlist_items) or []
        risks: list[StrongStockRiskItem] = []
        for item in raw_items:
            symbol = str(getattr(item, "symbol", "") or "")
            if not symbol:
                continue
            name = getattr(item, "name", None) or symbol
            try:
                bars = self.kline_provider.get_klines(symbol, count=220)
            except Exception:
                continue
            risks.append(
                analyze_watchlist_risk(
                    StrongStockCandidate(symbol=symbol, name=name, limit_up_evidence=[]),
                    bars,
                    trade_date=trade_date,
                )
            )
        return risks
```

- [ ] **Step 4: Add FastAPI endpoint**

Modify `apps/api/app/main.py`.

Add imports:

```python
from pydantic import BaseModel, Field

from app.services.strong_stock_screening import (
    BaiduKlineProvider,
    StrongStockDataUnavailable,
    StrongStockScreeningService,
    ThsdkStrongStockCandidateProvider,
)
```

If `BaseModel` already exists in the import line, replace it with `BaseModel, Field`.

Add request model near existing request models:

```python
class StrongStockScreenRequest(BaseModel):
    trade_date: str
    limit: int = Field(default=30, ge=1, le=100)
```

Add service factory near `_a_stock_vendor_updater()`:

```python
def _strong_stock_screening_service() -> StrongStockScreeningService:
    injected = getattr(app.state, "strong_stock_screening_service", None)
    if injected is not None:
        return injected
    settings = get_settings()
    return StrongStockScreeningService(
        candidate_provider=ThsdkStrongStockCandidateProvider.from_installed_package(),
        kline_provider=BaiduKlineProvider(timeout_seconds=settings.provider_timeout_seconds),
    )
```

Add endpoint near data-source endpoints:

```python
@app.post("/api/strong-stocks/screen")
def screen_strong_stocks(request: StrongStockScreenRequest) -> dict[str, object]:
    service = _strong_stock_screening_service()
    try:
        result = service.screen(
            trade_date=request.trade_date,
            limit=request.limit,
            watchlist_items=_watchlist_service().get_latest(),
        )
    except StrongStockDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        if getattr(app.state, "strong_stock_screening_service", None) is None:
            close = getattr(service, "close", None)
            if callable(close):
                close()
    return result.model_dump(mode="json")
```

- [ ] **Step 5: Run API and pure-rule tests**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_strong_stock_screening.py tests/test_strong_stock_screening_api.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add apps/api/app/services/strong_stock_screening.py apps/api/app/main.py apps/api/tests/test_strong_stock_screening_api.py
git commit -m "feat: expose strong stock screening api"
```

### Task 4: Frontend Types And API Client

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Test: `apps/web/lib/strongStockScreeningPanel.test.ts`

- [ ] **Step 1: Add failing frontend source test**

Create `apps/web/lib/strongStockScreeningPanel.test.ts`:

```ts
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("strong stock screening types and api are wired", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");

  assert.match(typesSource, /StrongStockScreeningResponse/);
  assert.match(typesSource, /StrongStockScreeningItem/);
  assert.match(typesSource, /WatchlistRiskItem/);
  assert.match(typesSource, /status: "focus" \\| "wait_pullback" \\| "reduce_risk" \\| "data_incomplete"/);
  assert.match(typesSource, /risk_action: "hold_watch" \\| "reduce" \\| "empty"/);
  assert.match(apiSource, /screenStrongStocks/);
  assert.match(apiSource, /\\/api\\/strong-stocks\\/screen/);
  assert.doesNotMatch(typesSource, /status: .*"empty"/);
});
```

- [ ] **Step 2: Run frontend test to verify it fails**

Run:

```bash
corepack pnpm --filter @stock-review/web test -- strongStockScreeningPanel.test.ts
```

Expected: FAIL because `StrongStockScreeningResponse` and `screenStrongStocks` do not exist.

- [ ] **Step 3: Add TypeScript types**

Append to `apps/web/lib/types.ts`:

```ts
export type StrongStockScreeningStatus = "focus" | "wait_pullback" | "reduce_risk" | "data_incomplete";

export type WatchlistRiskAction = "hold_watch" | "reduce" | "empty";

export type StrongStockSourceStatus = {
  source: string;
  status: "success" | "failed" | "disabled";
  detail: string;
};

export type StrongStockScreeningItem = {
  symbol: string;
  name: string;
  status: StrongStockScreeningStatus;
  score: number;
  rule_hits: string[];
  risk_flags: string[];
  intraday_notes: string[];
  metrics: Record<string, unknown>;
  data_status: "complete" | "incomplete";
};

export type WatchlistRiskItem = {
  symbol: string;
  name: string;
  risk_action: WatchlistRiskAction;
  risk_flags: string[];
  intraday_notes: string[];
  metrics: Record<string, unknown>;
};

export type StrongStockScreeningResponse = {
  trade_date: string;
  source_status: StrongStockSourceStatus[];
  items: StrongStockScreeningItem[];
  watchlist_risk_items: WatchlistRiskItem[];
  generated_at: string;
};
```

- [ ] **Step 4: Add API function**

Modify the type import in `apps/web/lib/api.ts` to include:

```ts
  StrongStockScreeningResponse,
```

Add function after `updateAStockVendorAutoCheck`:

```ts
export async function screenStrongStocks(
  tradeDate: string,
  limit = 30,
): Promise<StrongStockScreeningResponse> {
  const response = await fetch(`${API_BASE_URL}/api/strong-stocks/screen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trade_date: tradeDate, limit }),
  });
  if (!response.ok) {
    let detail = await response.text();
    try {
      const payload = JSON.parse(detail) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // Keep raw detail text.
    }
    throw new Error(`强势股筛选失败：${response.status} ${detail}`);
  }
  return response.json() as Promise<StrongStockScreeningResponse>;
}
```

- [ ] **Step 5: Run frontend type/API test**

Run:

```bash
corepack pnpm --filter @stock-review/web test -- strongStockScreeningPanel.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add apps/web/lib/types.ts apps/web/lib/api.ts apps/web/lib/strongStockScreeningPanel.test.ts
git commit -m "feat: add strong stock web api types"
```

### Task 5: Admin Homepage Panel

**Files:**
- Create: `apps/web/components/StrongStockScreeningPanel.tsx`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/lib/strongStockScreeningPanel.test.ts`

- [ ] **Step 1: Extend frontend source test**

Replace `apps/web/lib/strongStockScreeningPanel.test.ts` with:

```ts
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("strong stock screening panel is wired without empty screening status", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
  const panelSource = readFileSync(new URL("../components/StrongStockScreeningPanel.tsx", import.meta.url), "utf8");
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(typesSource, /StrongStockScreeningResponse/);
  assert.match(typesSource, /status: "focus" \\| "wait_pullback" \\| "reduce_risk" \\| "data_incomplete"/);
  assert.match(typesSource, /risk_action: "hold_watch" \\| "reduce" \\| "empty"/);
  assert.doesNotMatch(typesSource, /status: .*"empty"/);
  assert.match(apiSource, /screenStrongStocks/);
  assert.match(panelSource, /强势股规则选股与自选股风控/);
  assert.match(panelSource, /运行筛选/);
  assert.match(panelSource, /watchlist_risk_items/);
  assert.match(panelSource, /空仓纪律触发/);
  assert.match(pageSource, /StrongStockScreeningPanel/);
  assert.match(pageSource, /screenStrongStocks/);
});
```

- [ ] **Step 2: Run frontend test to verify it fails**

Run:

```bash
corepack pnpm --filter @stock-review/web test -- strongStockScreeningPanel.test.ts
```

Expected: FAIL because `StrongStockScreeningPanel.tsx` does not exist and `page.tsx` is not wired.

- [ ] **Step 3: Create panel component**

Create `apps/web/components/StrongStockScreeningPanel.tsx`:

```tsx
import type { StrongStockScreeningResponse, StrongStockScreeningStatus, WatchlistRiskAction } from "../lib/types";

const statusCopy: Record<StrongStockScreeningStatus, { label: string; badge: string }> = {
  focus: { label: "可关注", badge: "bg-emerald-50 text-emerald-700 ring-emerald-100" },
  wait_pullback: { label: "等回踩", badge: "bg-sky-50 text-sky-700 ring-sky-100" },
  reduce_risk: { label: "减仓风险", badge: "bg-amber-50 text-amber-700 ring-amber-100" },
  data_incomplete: { label: "数据不足", badge: "bg-slate-100 text-slate-600 ring-slate-200" },
};

const riskCopy: Record<WatchlistRiskAction, { label: string; badge: string }> = {
  hold_watch: { label: "继续观察", badge: "bg-sky-50 text-sky-700 ring-sky-100" },
  reduce: { label: "降低关注", badge: "bg-amber-50 text-amber-700 ring-amber-100" },
  empty: { label: "空仓纪律触发", badge: "bg-red-50 text-red-700 ring-red-100" },
};

export function StrongStockScreeningPanel({
  result,
  running,
  error,
  onRun,
}: {
  result: StrongStockScreeningResponse | null;
  running: boolean;
  error: string | null;
  onRun: () => void;
}) {
  const focusCount = result?.items.filter((item) => item.status === "focus").length ?? 0;
  const waitCount = result?.items.filter((item) => item.status === "wait_pullback").length ?? 0;
  const reduceCount = result?.items.filter((item) => item.status === "reduce_risk").length ?? 0;
  const emptyRiskCount = result?.watchlist_risk_items.filter((item) => item.risk_action === "empty").length ?? 0;

  return (
    <section id="strong-stock-screening" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Strong Stocks</p>
          <h2 className="mt-1 text-xl font-black text-slate-950">强势股规则选股与自选股风控</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">选股只看近 20 日涨停与趋势质量；空仓纪律只用于自选股风控。</p>
        </div>
      </div>

      <button
        className="mt-4 min-h-[44px] w-full rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-slate-800 active:translate-y-px disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:active:translate-y-0"
        disabled={running}
        onClick={onRun}
        type="button"
      >
        {running ? "筛选中" : "运行筛选"}
      </button>
      {error && <p className="mt-3 rounded-xl bg-red-50 p-3 text-sm leading-6 text-red-700">{error}</p>}

      {result && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-4 gap-2">
            <Metric label="候选" value={String(result.items.length)} />
            <Metric label="可关注" value={String(focusCount)} />
            <Metric label="等回踩" value={String(waitCount)} />
            <Metric label="减仓风险" value={String(reduceCount)} />
          </div>
          <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs leading-5 text-slate-600">
            自选股风控：空仓纪律触发 {emptyRiskCount} 只
          </div>
          <div className="space-y-2">
            {result.source_status.map((source) => (
              <p key={`${source.source}-${source.detail}`} className="rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500">
                {source.source}：{source.detail}
              </p>
            ))}
          </div>
          <div className="space-y-3">
            {result.items.map((item) => (
              <article key={item.symbol} className="rounded-xl border border-slate-100 bg-white p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-black text-slate-950">{item.name}</h3>
                    <p className="mt-1 text-xs font-semibold text-slate-400">{item.symbol} · 评分 {item.score}</p>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${statusCopy[item.status].badge}`}>
                    {statusCopy[item.status].label}
                  </span>
                </div>
                <p className="mt-3 text-xs leading-5 text-slate-600">{item.rule_hits.slice(0, 4).join(" / ")}</p>
                {item.risk_flags.length > 0 && <p className="mt-2 text-xs leading-5 text-amber-700">{item.risk_flags.join(" / ")}</p>}
              </article>
            ))}
          </div>
          {result.watchlist_risk_items.length > 0 && (
            <div className="space-y-2">
              {result.watchlist_risk_items.map((item) => (
                <article key={item.symbol} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-black text-slate-950">{item.name}</span>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${riskCopy[item.risk_action].badge}`}>
                      {riskCopy[item.risk_action].label}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-500">{item.risk_flags.join(" / ") || "趋势仍在观察范围"}</p>
                </article>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3 text-center ring-1 ring-slate-100">
      <div className="text-lg font-black text-slate-950">{value}</div>
      <div className="mt-1 text-[11px] font-bold text-slate-400">{label}</div>
    </div>
  );
}
```

- [ ] **Step 4: Wire panel into homepage**

Modify `apps/web/app/page.tsx`.

Add import:

```ts
import { StrongStockScreeningPanel } from "../components/StrongStockScreeningPanel";
```

Add API import:

```ts
  screenStrongStocks,
```

Add type import:

```ts
  StrongStockScreeningResponse,
```

Add state near other page state:

```ts
  const [strongStockRunning, setStrongStockRunning] = useState(false);
  const [strongStockError, setStrongStockError] = useState<string | null>(null);
  const [strongStockResult, setStrongStockResult] = useState<StrongStockScreeningResponse | null>(null);
```

Add handler near other handlers:

```ts
  async function handleStrongStockScreening() {
    setStrongStockRunning(true);
    setStrongStockError(null);
    try {
      const response = await screenStrongStocks(tradeDate, 30);
      setStrongStockResult(response);
    } catch (err) {
      setStrongStockError(err instanceof Error ? err.message : "强势股筛选失败");
    } finally {
      setStrongStockRunning(false);
    }
  }
```

Render the panel after `WatchlistImportPanel`:

```tsx
            <StrongStockScreeningPanel
              error={strongStockError}
              onRun={() => void handleStrongStockScreening()}
              result={strongStockResult}
              running={strongStockRunning}
            />
```

- [ ] **Step 5: Run frontend panel test**

Run:

```bash
corepack pnpm --filter @stock-review/web test -- strongStockScreeningPanel.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```bash
git add apps/web/components/StrongStockScreeningPanel.tsx apps/web/app/page.tsx apps/web/lib/strongStockScreeningPanel.test.ts
git commit -m "feat: add strong stock screening panel"
```

### Task 6: Final Verification

**Files:**
- Verify all files changed by Tasks 1-5.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_strong_stock_screening.py tests/test_strong_stock_screening_api.py
```

Expected: PASS.

- [ ] **Step 2: Run backend lint for touched app/tests files**

Run:

```bash
cd apps/api
.venv/bin/python -m ruff check app/services/strong_stock_screening.py app/main.py tests/test_strong_stock_screening.py tests/test_strong_stock_screening_api.py
```

Expected: PASS.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
corepack pnpm --filter @stock-review/web test
```

Expected: PASS.

- [ ] **Step 4: Run git diff checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. `git status --short` may still show pre-existing a-stock-data vendor update changes; implementation files from this plan should be either committed or intentionally staged for final review.

- [ ] **Step 5: Optional local UI smoke if implementation changed homepage layout**

Run API:

```bash
cd apps/api
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Run Web:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 corepack pnpm dev:web
```

Open `http://localhost:3000` in Browser and verify:

- the “强势股规则选股与自选股风控” panel renders in the left operations column,
- clicking `运行筛选` shows either results or a clear `THSDK 未安装` style source error,
- screening candidate badges do not display `空仓`,
- watchlist risk rows can display `空仓纪律触发`.

Stop dev servers before ending the implementation turn.

## Self-Review

Spec coverage:

- 20 日涨停 hard filter: Task 2 candidate provider and Task 3 service.
- K-line/MA/200-day high: Task 1 pure rules and Task 2 Baidu parser.
- Red-fat-green-thin and volume: Task 1 metrics and tests.
- Volume stall reduce risk: Task 1 test and status logic.
- Intraday discipline as notes only: Task 1 `_intraday_notes` and Task 5 display.
- Empty rule only for watchlist/holding risk: Task 1 test, Task 3 API test, Task 4 type test, Task 5 UI test.
- Manual backend API: Task 3.
- Admin homepage card: Task 5.
- Verification: Task 6.

Placeholder scan:

- The plan avoids placeholder words and gives exact files, test names, commands, and expected outcomes.

Type consistency:

- Backend uses `status` only for screening candidates and `risk_action` only for watchlist risk.
- Frontend mirrors the same split with `StrongStockScreeningStatus` and `WatchlistRiskAction`.
