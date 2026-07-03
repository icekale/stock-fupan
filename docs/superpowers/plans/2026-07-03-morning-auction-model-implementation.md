# Morning Auction Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the V1 morning auction research pipeline: labels, rule filtering, a-stock-data-backed cold-start features, JSONL datasets, train/backtest commands, prediction output, and API access.

**Architecture:** Add a focused `app.services.morning_auction` package. Free data from the existing a-stock-data provider feeds cold-start daily/sector/fund-flow features, while historical 9:15-9:25 auction snapshots come only from self-collected JSONL files. Training uses a single LightGBM classifier for `open_to_close_return >= 3%`, with `>=5%` kept as a strong-signal evaluation label.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, httpx, pytest, LightGBM, JSONL artifacts under `data/morning_auction/` and `artifacts/morning_auction/`.

---

## Scope Notes

This plan implements the cold-start V1 path. It does not fabricate historical auction snapshots from free data. If a symbol/date has no self-collected auction snapshot, the feature builder emits `auction_data_available = 0` and excludes sequence-only auction fields.

## File Structure

- Create `apps/api/app/services/morning_auction/__init__.py`: package marker and exported version.
- Create `apps/api/app/services/morning_auction/schemas.py`: DTOs for bars, auction snapshots, samples, predictions, and run summaries.
- Create `apps/api/app/services/morning_auction/filters.py`: deterministic tradability and risk filters.
- Create `apps/api/app/services/morning_auction/features.py`: cold-start and auction-aware feature builder.
- Create `apps/api/app/services/morning_auction/artifacts.py`: JSONL/JSON model artifact paths and read/write helpers.
- Create `apps/api/app/services/morning_auction/dataset.py`: sample and label construction from normalized inputs.
- Create `apps/api/app/services/morning_auction/trainer.py`: LightGBM training and model metadata persistence.
- Create `apps/api/app/services/morning_auction/backtest.py`: time-series Top N backtest.
- Create `apps/api/app/services/morning_auction/predictor.py`: prediction bucketing and explanation output.
- Create `apps/api/app/cli/morning_auction.py`: CLI for dataset, train, backtest, predict.
- Modify `apps/api/app/main.py`: add `POST /api/morning-auction/predict` and `GET /api/morning-auction/runs/{run_id}`.
- Modify `apps/api/pyproject.toml`: add `lightgbm`.
- Create `apps/api/tests/test_morning_auction_labels.py`.
- Create `apps/api/tests/test_morning_auction_features.py`.
- Create `apps/api/tests/test_morning_auction_dataset.py`.
- Create `apps/api/tests/test_morning_auction_training_backtest.py`.
- Create `apps/api/tests/test_morning_auction_cli_api.py`.

---

### Task 1: Labels, Schemas, And Rule Filters

**Files:**
- Create: `apps/api/app/services/morning_auction/__init__.py`
- Create: `apps/api/app/services/morning_auction/schemas.py`
- Create: `apps/api/app/services/morning_auction/filters.py`
- Test: `apps/api/tests/test_morning_auction_labels.py`

- [ ] **Step 1: Write failing tests for labels and filters**

Add `apps/api/tests/test_morning_auction_labels.py`:

```python
from app.services.morning_auction.filters import evaluate_candidate_filters
from app.services.morning_auction.schemas import DailyBar, MorningAuctionSample


def test_sample_labels_use_open_to_close_return() -> None:
    sample = MorningAuctionSample(
        trade_date="2026-07-03",
        symbol="600001.SH",
        name="测试股份",
        features={"prev_return": 1.2},
        open_price=10.0,
        close_price=10.31,
    )

    assert sample.open_to_close_return == 0.031
    assert sample.main_label is True
    assert sample.strong_label is False
    assert sample.safe_label is True
    assert sample.risk_label is False


def test_sample_strong_and_risk_labels() -> None:
    strong = MorningAuctionSample(
        trade_date="2026-07-03",
        symbol="600002.SH",
        name="强势股份",
        features={},
        open_price=10.0,
        close_price=10.55,
    )
    risk = MorningAuctionSample(
        trade_date="2026-07-03",
        symbol="600003.SH",
        name="风险股份",
        features={},
        open_price=10.0,
        close_price=9.69,
    )

    assert strong.main_label is True
    assert strong.strong_label is True
    assert risk.safe_label is False
    assert risk.risk_label is True


def test_filters_reject_untradable_and_overheated_candidates() -> None:
    latest = DailyBar(
        trade_date="2026-07-02",
        open=10.0,
        high=10.3,
        low=9.8,
        close=10.2,
        volume=1_000_000,
        amount=20_000_000,
        turnover_rate=3.0,
    )

    accepted = evaluate_candidate_filters(
        symbol="600001.SH",
        name="正常股份",
        listed_days=300,
        is_st=False,
        is_suspended=False,
        auction_return=3.0,
        auction_amount=15_000_000,
        daily_bars=[latest],
    )
    rejected = evaluate_candidate_filters(
        symbol="600002.SH",
        name="过热股份",
        listed_days=300,
        is_st=False,
        is_suspended=False,
        auction_return=8.5,
        auction_amount=15_000_000,
        daily_bars=[latest],
    )

    assert accepted.passed is True
    assert accepted.risk_flags == []
    assert rejected.passed is False
    assert "竞价涨幅过高" in rejected.risk_flags


def test_filters_allow_missing_auction_for_cold_start_training() -> None:
    latest = DailyBar(
        trade_date="2026-07-02",
        open=10.0,
        high=10.3,
        low=9.8,
        close=10.2,
        volume=1_000_000,
        amount=20_000_000,
        turnover_rate=3.0,
    )

    result = evaluate_candidate_filters(
        symbol="600001.SH",
        name="冷启动股份",
        listed_days=300,
        is_st=False,
        is_suspended=False,
        auction_return=None,
        auction_amount=None,
        daily_bars=[latest],
        require_auction_data=False,
    )

    assert result.passed is True
    assert result.risk_flags == []
```

- [ ] **Step 2: Run labels test to verify it fails**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_labels.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.morning_auction'`.

- [ ] **Step 3: Add schemas and label properties**

Create `apps/api/app/services/morning_auction/__init__.py`:

```python
MORNING_AUCTION_VERSION = "morning_auction_v1"
```

Create `apps/api/app/services/morning_auction/schemas.py`:

```python
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class MorningAuctionBucket(StrEnum):
    SELECTED = "selected"
    ATTACK = "attack"
    WATCH = "watch"
    AVOID = "avoid"


class DailyBar(BaseModel):
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    turnover_rate: float | None = None


class AuctionSnapshot(BaseModel):
    trade_date: str
    symbol: str
    name: str = ""
    snapshot_time: str
    indicative_price: float | None = None
    prev_close: float | None = None
    auction_volume: float | None = None
    auction_amount: float | None = None
    bid_volume: float | None = None
    ask_volume: float | None = None
    unmatched_volume: float | None = None


class FilterResult(BaseModel):
    passed: bool
    risk_flags: list[str] = Field(default_factory=list)


class MorningAuctionSample(BaseModel):
    trade_date: str
    symbol: str
    name: str
    features: dict[str, float | int | None] = Field(default_factory=dict)
    open_price: float
    close_price: float

    @property
    def open_to_close_return(self) -> float:
        if self.open_price <= 0:
            return 0.0
        return round(self.close_price / self.open_price - 1, 6)

    @property
    def main_label(self) -> bool:
        return self.open_to_close_return >= 0.03

    @property
    def strong_label(self) -> bool:
        return self.open_to_close_return >= 0.05

    @property
    def safe_label(self) -> bool:
        return self.open_to_close_return > 0

    @property
    def risk_label(self) -> bool:
        return self.open_to_close_return <= -0.03


class MorningAuctionPredictionItem(BaseModel):
    symbol: str
    name: str
    prob_3pct: float
    strong_5pct_score: float
    bucket: MorningAuctionBucket
    auction_reasons: list[str] = Field(default_factory=list)
    trend_reasons: list[str] = Field(default_factory=list)
    sector_reasons: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    data_quality: list[str] = Field(default_factory=list)


class MorningAuctionRun(BaseModel):
    run_id: str
    trade_date: str
    model_version: str
    feature_version: str
    source_status: dict[str, str] = Field(default_factory=dict)
    selected_pool: list[MorningAuctionPredictionItem] = Field(default_factory=list)
    attack_pool: list[MorningAuctionPredictionItem] = Field(default_factory=list)
    watch_pool: list[MorningAuctionPredictionItem] = Field(default_factory=list)
    avoid_pool: list[MorningAuctionPredictionItem] = Field(default_factory=list)
    items: list[MorningAuctionPredictionItem] = Field(default_factory=list)
```

- [ ] **Step 4: Add rule filter implementation**

Create `apps/api/app/services/morning_auction/filters.py`:

```python
from __future__ import annotations

from app.services.morning_auction.schemas import DailyBar, FilterResult


def evaluate_candidate_filters(
    *,
    symbol: str,
    name: str,
    listed_days: int,
    is_st: bool,
    is_suspended: bool,
    auction_return: float | None,
    auction_amount: float | None,
    daily_bars: list[DailyBar],
    require_auction_data: bool = False,
) -> FilterResult:
    risk_flags: list[str] = []
    if is_st or "ST" in name.upper():
        risk_flags.append("ST股票")
    if listed_days < 100:
        risk_flags.append("上市不足100天")
    if is_suspended:
        risk_flags.append("停牌")
    if require_auction_data and auction_return is None:
        risk_flags.append("竞价涨幅缺失")
    elif auction_return is not None and auction_return >= 8:
        risk_flags.append("竞价涨幅过高")
    if require_auction_data and auction_amount is None:
        risk_flags.append("竞价成交额缺失")
    elif auction_amount is not None and auction_amount < 5_000_000:
        risk_flags.append("竞价成交额不足")
    if not daily_bars:
        risk_flags.append("日K缺失")
    else:
        latest = daily_bars[-1]
        if latest.close <= 0 or latest.amount <= 0:
            risk_flags.append("日K成交异常")
    return FilterResult(passed=not risk_flags, risk_flags=risk_flags)
```

- [ ] **Step 5: Run labels test to verify it passes**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_labels.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add apps/api/app/services/morning_auction/__init__.py apps/api/app/services/morning_auction/schemas.py apps/api/app/services/morning_auction/filters.py apps/api/tests/test_morning_auction_labels.py
git commit -m "feat: add morning auction labels and filters"
```

---

### Task 2: Free Data Source Adapter Contracts

**Files:**
- Create: `apps/api/app/services/morning_auction/data_sources.py`
- Test: `apps/api/tests/test_morning_auction_dataset.py`

- [ ] **Step 1: Write failing tests for free-source normalized inputs**

Add this content to `apps/api/tests/test_morning_auction_dataset.py`:

```python
from app.services.morning_auction.data_sources import InMemoryMorningAuctionDataSource


def test_in_memory_data_source_returns_daily_bars_and_auction_snapshots() -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()

    bars = source.daily_bars("600001.SH", end_date="2026-07-03", lookback=3)
    auction = source.auction_snapshot("600001.SH", trade_date="2026-07-03")
    universe = source.candidate_universe("2026-07-03")

    assert [bar.trade_date for bar in bars] == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert auction is not None
    assert auction.snapshot_time == "09:25:00"
    assert universe[0]["symbol"] == "600001.SH"
```

- [ ] **Step 2: Run dataset test to verify it fails**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_dataset.py
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `data_sources`.

- [ ] **Step 3: Add normalized data source protocol and in-memory fake**

Create `apps/api/app/services/morning_auction/data_sources.py`:

```python
from __future__ import annotations

from typing import Protocol

from app.services.morning_auction.schemas import AuctionSnapshot, DailyBar


class MorningAuctionDataSource(Protocol):
    def candidate_universe(self, trade_date: str) -> list[dict[str, object]]:
        raise NotImplementedError

    def daily_bars(self, symbol: str, *, end_date: str, lookback: int) -> list[DailyBar]:
        raise NotImplementedError

    def auction_snapshot(self, symbol: str, *, trade_date: str) -> AuctionSnapshot | None:
        raise NotImplementedError

    def sector_strength(self, symbol: str, *, trade_date: str) -> float | None:
        raise NotImplementedError

    def capital_strength(self, symbol: str, *, trade_date: str) -> float | None:
        raise NotImplementedError


class InMemoryMorningAuctionDataSource:
    def __init__(
        self,
        universe: list[dict[str, object]],
        bars_by_symbol: dict[str, list[DailyBar]],
        auctions_by_key: dict[tuple[str, str], AuctionSnapshot],
        sector_by_symbol: dict[str, float] | None = None,
        capital_by_symbol: dict[str, float] | None = None,
    ) -> None:
        self._universe = universe
        self._bars_by_symbol = bars_by_symbol
        self._auctions_by_key = auctions_by_key
        self._sector_by_symbol = sector_by_symbol or {}
        self._capital_by_symbol = capital_by_symbol or {}

    @classmethod
    def with_fixture(cls) -> "InMemoryMorningAuctionDataSource":
        bars = [
            DailyBar(trade_date="2026-07-01", open=9.6, high=9.9, low=9.5, close=9.8, volume=900_000, amount=8_900_000, turnover_rate=2.1),
            DailyBar(trade_date="2026-07-02", open=9.8, high=10.2, low=9.7, close=10.0, volume=1_000_000, amount=10_100_000, turnover_rate=2.3),
            DailyBar(trade_date="2026-07-03", open=10.1, high=10.7, low=10.0, close=10.5, volume=1_200_000, amount=12_700_000, turnover_rate=2.8),
        ]
        return cls(
            universe=[
                {
                    "symbol": "600001.SH",
                    "name": "测试股份",
                    "listed_days": 300,
                    "is_st": False,
                    "is_suspended": False,
                    "market_cap_float": 8_000_000_000,
                }
            ],
            bars_by_symbol={"600001.SH": bars},
            auctions_by_key={
                ("600001.SH", "2026-07-03"): AuctionSnapshot(
                    trade_date="2026-07-03",
                    symbol="600001.SH",
                    name="测试股份",
                    snapshot_time="09:25:00",
                    indicative_price=10.1,
                    prev_close=10.0,
                    auction_volume=1_000_000,
                    auction_amount=10_100_000,
                    bid_volume=400_000,
                    ask_volume=250_000,
                    unmatched_volume=150_000,
                )
            },
            sector_by_symbol={"600001.SH": 78.0},
            capital_by_symbol={"600001.SH": 62.0},
        )

    def candidate_universe(self, trade_date: str) -> list[dict[str, object]]:
        return list(self._universe)

    def daily_bars(self, symbol: str, *, end_date: str, lookback: int) -> list[DailyBar]:
        return self._bars_by_symbol.get(symbol, [])[-lookback:]

    def auction_snapshot(self, symbol: str, *, trade_date: str) -> AuctionSnapshot | None:
        return self._auctions_by_key.get((symbol, trade_date))

    def sector_strength(self, symbol: str, *, trade_date: str) -> float | None:
        return self._sector_by_symbol.get(symbol)

    def capital_strength(self, symbol: str, *, trade_date: str) -> float | None:
        return self._capital_by_symbol.get(symbol)
```

- [ ] **Step 4: Run dataset test to verify it passes**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_dataset.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add apps/api/app/services/morning_auction/data_sources.py apps/api/tests/test_morning_auction_dataset.py
git commit -m "feat: add morning auction data source contracts"
```

---

### Task 3: Feature Builder With No Future Leakage

**Files:**
- Create: `apps/api/app/services/morning_auction/features.py`
- Test: `apps/api/tests/test_morning_auction_features.py`

- [ ] **Step 1: Write failing feature tests**

Add `apps/api/tests/test_morning_auction_features.py`:

```python
from app.services.morning_auction.data_sources import InMemoryMorningAuctionDataSource
from app.services.morning_auction.features import build_feature_row


def test_feature_row_uses_prior_bars_and_auction_snapshot() -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()
    bars = source.daily_bars("600001.SH", end_date="2026-07-03", lookback=3)
    auction = source.auction_snapshot("600001.SH", trade_date="2026-07-03")

    row = build_feature_row(
        symbol="600001.SH",
        market_cap_float=8_000_000_000,
        daily_bars=bars[:2],
        auction=auction,
        sector_strength=78.0,
        capital_strength=62.0,
    )

    assert row["auction_data_available"] == 1
    assert row["auction_return"] == 1.0
    assert row["prev_return"] == 2.0408
    assert row["close_vs_ma5"] == 0.0
    assert row["sector_strength"] == 78.0
    assert row["capital_strength"] == 62.0


def test_feature_row_marks_missing_auction_data() -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()
    bars = source.daily_bars("600001.SH", end_date="2026-07-03", lookback=3)

    row = build_feature_row(
        symbol="600001.SH",
        market_cap_float=8_000_000_000,
        daily_bars=bars[:2],
        auction=None,
        sector_strength=None,
        capital_strength=None,
    )

    assert row["auction_data_available"] == 0
    assert row["auction_return"] is None
    assert row["sector_strength"] is None
```

- [ ] **Step 2: Run feature tests to verify they fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_features.py
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `features`.

- [ ] **Step 3: Add feature builder**

Create `apps/api/app/services/morning_auction/features.py`:

```python
from __future__ import annotations

from app.services.morning_auction.schemas import AuctionSnapshot, DailyBar

FEATURE_VERSION = "morning_auction_features_v1"


def build_feature_row(
    *,
    symbol: str,
    market_cap_float: float | None,
    daily_bars: list[DailyBar],
    auction: AuctionSnapshot | None,
    sector_strength: float | None,
    capital_strength: float | None,
) -> dict[str, float | int | None]:
    latest = daily_bars[-1] if daily_bars else None
    previous = daily_bars[-2] if len(daily_bars) >= 2 else None
    close_values = [bar.close for bar in daily_bars]
    volume_values = [bar.volume for bar in daily_bars]
    amount_values = [bar.amount for bar in daily_bars]

    row: dict[str, float | int | None] = {
        "market_cap_float": _round_or_none(market_cap_float),
        "prev_return": _pct_change(latest.close, previous.close) if latest and previous else None,
        "prev_turnover": latest.turnover_rate if latest else None,
        "return_3d": _window_return(close_values, 3),
        "return_5d": _window_return(close_values, 5),
        "volume_ratio_3d": _last_vs_average(volume_values, 3),
        "amount_ratio_3d": _last_vs_average(amount_values, 3),
        "close_vs_ma5": _close_vs_ma(close_values, 5),
        "close_vs_ma10": _close_vs_ma(close_values, 10),
        "close_vs_ma20": _close_vs_ma(close_values, 20),
        "new_high_60d": _new_high(close_values, 60),
        "sector_strength": _round_or_none(sector_strength),
        "capital_strength": _round_or_none(capital_strength),
    }
    row.update(_auction_features(auction, latest))
    row["risk_score"] = _risk_score(row)
    return row


def _auction_features(auction: AuctionSnapshot | None, latest: DailyBar | None) -> dict[str, float | int | None]:
    if auction is None:
        return {
            "auction_data_available": 0,
            "auction_return": None,
            "auction_volume_ratio": None,
            "auction_amount_ratio": None,
            "bid_ask_imbalance": None,
            "unmatched_buy_ratio": None,
        }
    prev_close = auction.prev_close or (latest.close if latest else None)
    return {
        "auction_data_available": 1,
        "auction_return": _pct_change(auction.indicative_price, prev_close),
        "auction_volume_ratio": _ratio(auction.auction_volume, latest.volume if latest else None),
        "auction_amount_ratio": _ratio(auction.auction_amount, latest.amount if latest else None),
        "bid_ask_imbalance": _imbalance(auction.bid_volume, auction.ask_volume),
        "unmatched_buy_ratio": _ratio(auction.unmatched_volume, auction.auction_volume),
    }


def _pct_change(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or base == 0:
        return None
    return round((value / base - 1) * 100, 4)


def _ratio(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or base == 0:
        return None
    return round(value / base, 6)


def _imbalance(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or bid + ask == 0:
        return None
    return round((bid - ask) / (bid + ask), 6)


def _window_return(values: list[float], window: int) -> float | None:
    if len(values) < window or values[-window] == 0:
        return None
    return round((values[-1] / values[-window] - 1) * 100, 4)


def _last_vs_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    base_values = values[-window:-1]
    if not base_values:
        return None
    average = sum(base_values) / len(base_values)
    if average == 0:
        return None
    return round(values[-1] / average, 6)


def _close_vs_ma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return 0.0
    average = sum(values[-window:]) / window
    if average == 0:
        return None
    return round((values[-1] / average - 1) * 100, 4)


def _new_high(values: list[float], window: int) -> int:
    if not values:
        return 0
    recent = values[-window:]
    return int(values[-1] >= max(recent))


def _risk_score(row: dict[str, float | int | None]) -> float:
    score = 0.0
    auction_return = row.get("auction_return")
    if isinstance(auction_return, (int, float)) and auction_return >= 7:
        score += 20
    prev_return = row.get("prev_return")
    if isinstance(prev_return, (int, float)) and prev_return <= -3:
        score += 10
    return score


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)
```

- [ ] **Step 4: Run feature tests to verify they pass**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_features.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add apps/api/app/services/morning_auction/features.py apps/api/tests/test_morning_auction_features.py
git commit -m "feat: add morning auction feature builder"
```

---

### Task 4: Dataset And Artifact Storage

**Files:**
- Create: `apps/api/app/services/morning_auction/artifacts.py`
- Create: `apps/api/app/services/morning_auction/dataset.py`
- Modify: `apps/api/tests/test_morning_auction_dataset.py`

- [ ] **Step 1: Extend dataset tests for sample building and JSONL persistence**

Append to `apps/api/tests/test_morning_auction_dataset.py`:

```python
from pathlib import Path

from app.services.morning_auction.artifacts import read_jsonl, write_jsonl
from app.services.morning_auction.dataset import build_samples_for_trade_date


def test_build_samples_for_trade_date_uses_prior_bars_for_features() -> None:
    source = InMemoryMorningAuctionDataSource.with_fixture()

    samples = build_samples_for_trade_date(source, trade_date="2026-07-03", lookback=3)

    assert len(samples) == 1
    assert samples[0].symbol == "600001.SH"
    assert samples[0].open_price == 10.1
    assert samples[0].close_price == 10.5
    assert samples[0].main_label is True
    assert samples[0].features["auction_data_available"] == 1


def test_jsonl_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    rows = [{"symbol": "600001.SH", "value": 1}, {"symbol": "600002.SH", "value": 2}]

    write_jsonl(path, rows)

    assert read_jsonl(path) == rows
```

- [ ] **Step 2: Run dataset tests to verify they fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_dataset.py
```

Expected: FAIL with imports missing for `artifacts` and `dataset`.

- [ ] **Step 3: Add artifact helpers**

Create `apps/api/app/services/morning_auction/artifacts.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, object]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
```

- [ ] **Step 4: Add dataset builder**

Create `apps/api/app/services/morning_auction/dataset.py`:

```python
from __future__ import annotations

from app.services.morning_auction.data_sources import MorningAuctionDataSource
from app.services.morning_auction.features import build_feature_row
from app.services.morning_auction.filters import evaluate_candidate_filters
from app.services.morning_auction.schemas import MorningAuctionSample


def build_samples_for_trade_date(
    source: MorningAuctionDataSource,
    *,
    trade_date: str,
    lookback: int = 120,
) -> list[MorningAuctionSample]:
    samples: list[MorningAuctionSample] = []
    for candidate in source.candidate_universe(trade_date):
        symbol = str(candidate["symbol"])
        name = str(candidate.get("name", ""))
        bars = source.daily_bars(symbol, end_date=trade_date, lookback=lookback)
        if len(bars) < 2:
            continue
        auction = source.auction_snapshot(symbol, trade_date=trade_date)
        auction_return = None
        auction_amount = None
        if auction is not None and auction.indicative_price and auction.prev_close:
            auction_return = (auction.indicative_price / auction.prev_close - 1) * 100
            auction_amount = auction.auction_amount
        filter_result = evaluate_candidate_filters(
            symbol=symbol,
            name=name,
            listed_days=int(candidate.get("listed_days", 0)),
            is_st=bool(candidate.get("is_st", False)),
            is_suspended=bool(candidate.get("is_suspended", False)),
            auction_return=auction_return,
            auction_amount=auction_amount if auction_amount is not None else 10_000_000,
            daily_bars=bars[:-1],
            require_auction_data=False,
        )
        if not filter_result.passed:
            continue
        features = build_feature_row(
            symbol=symbol,
            market_cap_float=_float_or_none(candidate.get("market_cap_float")),
            daily_bars=bars[:-1],
            auction=auction,
            sector_strength=source.sector_strength(symbol, trade_date=trade_date),
            capital_strength=source.capital_strength(symbol, trade_date=trade_date),
        )
        current_bar = bars[-1]
        samples.append(
            MorningAuctionSample(
                trade_date=trade_date,
                symbol=symbol,
                name=name,
                features=features,
                open_price=current_bar.open,
                close_price=current_bar.close,
            )
        )
    return samples


def sample_to_row(sample: MorningAuctionSample) -> dict[str, object]:
    return {
        "trade_date": sample.trade_date,
        "symbol": sample.symbol,
        "name": sample.name,
        "features": sample.features,
        "open_price": sample.open_price,
        "close_price": sample.close_price,
        "open_to_close_return": sample.open_to_close_return,
        "main_label": sample.main_label,
        "strong_label": sample.strong_label,
        "safe_label": sample.safe_label,
        "risk_label": sample.risk_label,
    }


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
```

- [ ] **Step 5: Run dataset tests to verify they pass**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_dataset.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add apps/api/app/services/morning_auction/artifacts.py apps/api/app/services/morning_auction/dataset.py apps/api/tests/test_morning_auction_dataset.py
git commit -m "feat: add morning auction dataset builder"
```

---

### Task 5: Training And Backtest

**Files:**
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/uv.lock`
- Create: `apps/api/app/services/morning_auction/trainer.py`
- Create: `apps/api/app/services/morning_auction/backtest.py`
- Test: `apps/api/tests/test_morning_auction_training_backtest.py`

- [ ] **Step 1: Add failing trainer and backtest tests**

Create `apps/api/tests/test_morning_auction_training_backtest.py`:

```python
from pathlib import Path

from app.services.morning_auction.artifacts import read_json
from app.services.morning_auction.backtest import backtest_top_n
from app.services.morning_auction.trainer import build_training_matrix, save_training_metadata


def test_build_training_matrix_orders_feature_columns() -> None:
    rows = [
        {"features": {"b": 2.0, "a": 1.0}, "main_label": True},
        {"features": {"a": None, "b": 4.0}, "main_label": False},
    ]

    matrix = build_training_matrix(rows)

    assert matrix.feature_names == ["a", "b"]
    assert matrix.x == [[1.0, 2.0], [0.0, 4.0]]
    assert matrix.y == [1, 0]


def test_training_metadata_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"

    save_training_metadata(
        path,
        model_version="model-v1",
        feature_version="features-v1",
        feature_names=["a", "b"],
        train_date_range=["2026-07-01", "2026-07-03"],
    )

    metadata = read_json(path)
    assert metadata["model_version"] == "model-v1"
    assert metadata["feature_names"] == ["a", "b"]


def test_backtest_top_n_reports_average_return_and_hit_rates() -> None:
    rows = [
        {"trade_date": "2026-07-01", "symbol": "600001.SH", "prob_3pct": 0.9, "open_to_close_return": 0.04, "main_label": True, "strong_label": False},
        {"trade_date": "2026-07-01", "symbol": "600002.SH", "prob_3pct": 0.8, "open_to_close_return": -0.02, "main_label": False, "strong_label": False},
        {"trade_date": "2026-07-02", "symbol": "600003.SH", "prob_3pct": 0.95, "open_to_close_return": 0.06, "main_label": True, "strong_label": True},
    ]

    result = backtest_top_n(rows, top_n=1)

    assert result["top_n"] == 1
    assert result["trade_days"] == 2
    assert result["average_return"] == 0.05
    assert result["hit_3pct_rate"] == 1.0
    assert result["hit_5pct_rate"] == 0.5
```

- [ ] **Step 2: Run training tests to verify they fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_training_backtest.py
```

Expected: FAIL with missing `trainer` and `backtest` modules.

- [ ] **Step 3: Add LightGBM dependency**

Modify `apps/api/pyproject.toml` dependencies list:

```toml
  "lightgbm>=4.5.0",
```

Place it next to the existing runtime dependencies.

Then refresh `apps/api/uv.lock`:

```bash
cd apps/api
uv lock
```

Expected: command exits 0 and `apps/api/uv.lock` includes `lightgbm`.

- [ ] **Step 4: Add trainer utilities**

Create `apps/api/app/services/morning_auction/trainer.py`:

```python
from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.services.morning_auction.artifacts import ensure_parent, write_json


@dataclass(frozen=True)
class TrainingMatrix:
    x: list[list[float]]
    y: list[int]
    feature_names: list[str]


def build_training_matrix(rows: list[dict[str, object]]) -> TrainingMatrix:
    feature_names = sorted(
        {
            key
            for row in rows
            for key in (row.get("features") or {}).keys()
            if isinstance(row.get("features"), dict)
        }
    )
    x: list[list[float]] = []
    y: list[int] = []
    for row in rows:
        features = row.get("features") if isinstance(row.get("features"), dict) else {}
        x.append([_float_feature(features.get(name)) for name in feature_names])
        y.append(1 if row.get("main_label") else 0)
    return TrainingMatrix(x=x, y=y, feature_names=feature_names)


def train_lightgbm_model(rows: list[dict[str, object]], model_path: Path, metadata_path: Path) -> dict[str, object]:
    from lightgbm import LGBMClassifier

    matrix = build_training_matrix(rows)
    positives = sum(matrix.y)
    negatives = len(matrix.y) - positives
    scale_pos_weight = negatives / positives if positives else 1.0
    model = LGBMClassifier(
        n_estimators=120,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
    )
    model.fit(matrix.x, matrix.y)
    ensure_parent(model_path)
    with model_path.open("wb") as handle:
        pickle.dump(model, handle)
    model_version = f"morning-auction-{uuid4().hex[:8]}"
    save_training_metadata(
        metadata_path,
        model_version=model_version,
        feature_version="morning_auction_features_v1",
        feature_names=matrix.feature_names,
        train_date_range=_date_range(rows),
    )
    return {
        "model_version": model_version,
        "feature_names": matrix.feature_names,
        "positive_count": positives,
        "negative_count": negatives,
    }


def save_training_metadata(
    path: Path,
    *,
    model_version: str,
    feature_version: str,
    feature_names: list[str],
    train_date_range: list[str],
) -> None:
    write_json(
        path,
        {
            "model_version": model_version,
            "feature_version": feature_version,
            "feature_names": feature_names,
            "train_date_range": train_date_range,
        },
    )


def _float_feature(value: object) -> float:
    if value is None:
        return 0.0
    return float(value)


def _date_range(rows: list[dict[str, object]]) -> list[str]:
    dates = sorted(str(row["trade_date"]) for row in rows if row.get("trade_date"))
    if not dates:
        return []
    return [dates[0], dates[-1]]
```

- [ ] **Step 5: Add backtest utility**

Create `apps/api/app/services/morning_auction/backtest.py`:

```python
from __future__ import annotations


def backtest_top_n(rows: list[dict[str, object]], *, top_n: int) -> dict[str, object]:
    by_date: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_date.setdefault(str(row["trade_date"]), []).append(row)

    selected: list[dict[str, object]] = []
    for trade_date in sorted(by_date):
        ranked = sorted(by_date[trade_date], key=lambda row: float(row.get("prob_3pct", 0)), reverse=True)
        selected.extend(ranked[:top_n])

    returns = [float(row.get("open_to_close_return", 0)) for row in selected]
    hit_3 = [1 if row.get("main_label") else 0 for row in selected]
    hit_5 = [1 if row.get("strong_label") else 0 for row in selected]
    loss = [1 if float(row.get("open_to_close_return", 0)) < 0 else 0 for row in selected]
    return {
        "top_n": top_n,
        "trade_days": len(by_date),
        "selected_count": len(selected),
        "average_return": round(sum(returns) / len(returns), 6) if returns else 0.0,
        "hit_3pct_rate": round(sum(hit_3) / len(hit_3), 6) if hit_3 else 0.0,
        "hit_5pct_rate": round(sum(hit_5) / len(hit_5), 6) if hit_5 else 0.0,
        "loss_rate": round(sum(loss) / len(loss), 6) if loss else 0.0,
    }
```

- [ ] **Step 6: Run training tests to verify they pass**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_training_backtest.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add apps/api/pyproject.toml apps/api/uv.lock apps/api/app/services/morning_auction/trainer.py apps/api/app/services/morning_auction/backtest.py apps/api/tests/test_morning_auction_training_backtest.py
git commit -m "feat: add morning auction training and backtest"
```

---

### Task 6: Predictor And CLI

**Files:**
- Create: `apps/api/app/services/morning_auction/predictor.py`
- Create: `apps/api/app/cli/morning_auction.py`
- Test: `apps/api/tests/test_morning_auction_cli_api.py`

- [ ] **Step 1: Write failing predictor and CLI tests**

Create `apps/api/tests/test_morning_auction_cli_api.py`:

```python
from pathlib import Path

from app.cli.morning_auction import main
from app.services.morning_auction.predictor import bucket_prediction
from app.services.morning_auction.schemas import MorningAuctionBucket


def test_bucket_prediction_assigns_selected_attack_watch_and_avoid() -> None:
    assert bucket_prediction(prob_3pct=0.82, strong_5pct_score=0.7, risk_flags=[]) == MorningAuctionBucket.SELECTED
    assert bucket_prediction(prob_3pct=0.7, strong_5pct_score=0.86, risk_flags=[]) == MorningAuctionBucket.ATTACK
    assert bucket_prediction(prob_3pct=0.45, strong_5pct_score=0.2, risk_flags=[]) == MorningAuctionBucket.WATCH
    assert bucket_prediction(prob_3pct=0.9, strong_5pct_score=0.9, risk_flags=["竞价涨幅过高"]) == MorningAuctionBucket.AVOID


def test_cli_backtest_reads_prediction_jsonl(tmp_path: Path, capsys) -> None:
    path = tmp_path / "predictions.jsonl"
    path.write_text(
        '{"trade_date":"2026-07-01","symbol":"600001.SH","prob_3pct":0.9,"open_to_close_return":0.04,"main_label":true,"strong_label":false}\n',
        encoding="utf-8",
    )

    exit_code = main(["backtest", "--predictions", str(path), "--top-n", "1"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "hit_3pct_rate" in output
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_cli_api.py
```

Expected: FAIL with missing `predictor` and `app.cli.morning_auction`.

- [ ] **Step 3: Add predictor bucketing**

Create `apps/api/app/services/morning_auction/predictor.py`:

```python
from __future__ import annotations

from uuid import uuid4

from app.services.morning_auction.features import FEATURE_VERSION
from app.services.morning_auction.schemas import (
    MorningAuctionBucket,
    MorningAuctionPredictionItem,
    MorningAuctionRun,
)


def bucket_prediction(
    *,
    prob_3pct: float,
    strong_5pct_score: float,
    risk_flags: list[str],
) -> MorningAuctionBucket:
    if risk_flags:
        return MorningAuctionBucket.AVOID
    if prob_3pct >= 0.8:
        return MorningAuctionBucket.SELECTED
    if prob_3pct >= 0.65 and strong_5pct_score >= 0.8:
        return MorningAuctionBucket.ATTACK
    if prob_3pct >= 0.35:
        return MorningAuctionBucket.WATCH
    return MorningAuctionBucket.AVOID


def build_run(
    *,
    trade_date: str,
    model_version: str,
    source_status: dict[str, str],
    items: list[MorningAuctionPredictionItem],
) -> MorningAuctionRun:
    return MorningAuctionRun(
        run_id=uuid4().hex,
        trade_date=trade_date,
        model_version=model_version,
        feature_version=FEATURE_VERSION,
        source_status=source_status,
        selected_pool=[item for item in items if item.bucket == MorningAuctionBucket.SELECTED],
        attack_pool=[item for item in items if item.bucket == MorningAuctionBucket.ATTACK],
        watch_pool=[item for item in items if item.bucket == MorningAuctionBucket.WATCH],
        avoid_pool=[item for item in items if item.bucket == MorningAuctionBucket.AVOID],
        items=items,
    )
```

- [ ] **Step 4: Add CLI**

Create `apps/api/app/cli/morning_auction.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.services.morning_auction.artifacts import read_jsonl, write_json
from app.services.morning_auction.backtest import backtest_top_n
from app.services.morning_auction.trainer import train_lightgbm_model


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Morning auction model utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("--dataset", required=True)
    train_parser.add_argument("--model", required=True)
    train_parser.add_argument("--metadata", required=True)

    backtest_parser = subparsers.add_parser("backtest")
    backtest_parser.add_argument("--predictions", required=True)
    backtest_parser.add_argument("--top-n", type=int, default=3)
    backtest_parser.add_argument("--output")

    args = parser.parse_args(argv)
    if args.command == "train":
        rows = read_jsonl(Path(args.dataset))
        result = train_lightgbm_model(rows, Path(args.model), Path(args.metadata))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "backtest":
        rows = read_jsonl(Path(args.predictions))
        result = backtest_top_n(rows, top_n=args.top_n)
        if args.output:
            write_json(Path(args.output), result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run CLI tests to verify they pass**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_cli_api.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add apps/api/app/services/morning_auction/predictor.py apps/api/app/cli/morning_auction.py apps/api/tests/test_morning_auction_cli_api.py
git commit -m "feat: add morning auction predictor cli"
```

---

### Task 7: API Endpoints

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_morning_auction_cli_api.py`

- [ ] **Step 1: Add failing API test**

Append to `apps/api/tests/test_morning_auction_cli_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_morning_auction_predict_api_returns_run_payload() -> None:
    client = TestClient(app)

    response = client.post("/api/morning-auction/predict", json={"trade_date": "2026-07-03"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["trade_date"] == "2026-07-03"
    assert payload["model_version"] == "manual-cold-start"
    assert "items" in payload
```

- [ ] **Step 2: Run API test to verify it fails**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_cli_api.py::test_morning_auction_predict_api_returns_run_payload
```

Expected: FAIL with `404 Not Found`.

- [ ] **Step 3: Add request model and endpoints to `main.py`**

Modify `apps/api/app/main.py` imports:

```python
from app.services.morning_auction.predictor import build_run
```

Add request model near the other request models:

```python
class MorningAuctionPredictRequest(BaseModel):
    trade_date: str

    @field_validator("trade_date")
    @classmethod
    def validate_trade_date(cls, value: str) -> str:
        if len(value) != 10 or value[4] != "-" or value[7] != "-":
            raise ValueError("trade_date must use YYYY-MM-DD")
        date.fromisoformat(value)
        return value
```

Add in-memory run store near `logger`:

```python
MORNING_AUCTION_RUNS: dict[str, dict[str, object]] = {}
```

Add endpoints after `/health`:

```python
@app.post("/api/morning-auction/predict")
def morning_auction_predict(request: MorningAuctionPredictRequest) -> dict[str, object]:
    run = build_run(
        trade_date=request.trade_date,
        model_version="manual-cold-start",
        source_status={
            "a_stock_data": "configured",
            "auction_history": "self_collected_only",
        },
        items=[],
    )
    payload = run.model_dump(mode="json")
    MORNING_AUCTION_RUNS[run.run_id] = payload
    return payload


@app.get("/api/morning-auction/runs/{run_id}")
def morning_auction_run(run_id: str) -> dict[str, object]:
    payload = MORNING_AUCTION_RUNS.get(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Morning auction run not found")
    return payload
```

- [ ] **Step 4: Run API test to verify it passes**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_cli_api.py::test_morning_auction_predict_api_returns_run_payload
```

Expected: PASS.

- [ ] **Step 5: Commit Task 7**

```bash
git add apps/api/app/main.py apps/api/tests/test_morning_auction_cli_api.py
git commit -m "feat: add morning auction api endpoints"
```

---

### Task 8: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q \
  tests/test_morning_auction_labels.py \
  tests/test_morning_auction_features.py \
  tests/test_morning_auction_dataset.py \
  tests/test_morning_auction_training_backtest.py \
  tests/test_morning_auction_cli_api.py
```

Expected: PASS.

- [ ] **Step 2: Run existing API smoke test touched by main app imports**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_tickflow_health.py::test_tickflow_health_endpoint_uses_settings
```

Expected: PASS.

- [ ] **Step 3: Run lint on new files**

Run:

```bash
cd apps/api
.venv/bin/python -m ruff check app/services/morning_auction app/cli/morning_auction.py tests/test_morning_auction_labels.py tests/test_morning_auction_features.py tests/test_morning_auction_dataset.py tests/test_morning_auction_training_backtest.py tests/test_morning_auction_cli_api.py
```

Expected: PASS.

- [ ] **Step 4: Commit verification fixes if any were needed**

```bash
git status --short
git add apps/api/app/services/morning_auction apps/api/app/cli/morning_auction.py apps/api/app/main.py apps/api/pyproject.toml apps/api/tests/test_morning_auction_labels.py apps/api/tests/test_morning_auction_features.py apps/api/tests/test_morning_auction_dataset.py apps/api/tests/test_morning_auction_training_backtest.py apps/api/tests/test_morning_auction_cli_api.py
git commit -m "test: verify morning auction model pipeline"
```

Use this commit only if Step 1-3 required changes after Task 7.

---

## Self-Review

Spec coverage:

- Labels are covered by Task 1.
- a-stock-data cold-start boundary is covered by Task 2 and Task 3.
- Rule filtering is covered by Task 1.
- Dataset construction and JSONL artifacts are covered by Task 4.
- Training and Top N backtest are covered by Task 5.
- Prediction bucketing and CLI are covered by Task 6.
- API access is covered by Task 7.
- Verification is covered by Task 8.

No historical auction backfill is planned because the spec explicitly forbids fabricating it from free sources. The API returns an empty cold-start run until predictor wiring is expanded with live/self-collected data in a subsequent plan.
