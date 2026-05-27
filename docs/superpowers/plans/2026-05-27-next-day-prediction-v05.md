# Next-Day Prediction v0.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a built-in next-day prediction module to the main A-share daily HTML report, using curated review evidence plus TickFlow-derived market strength and Anspire news catalysts without fabricating production content.

**Architecture:** Add deterministic prediction DTOs to the report schema, implement a side-effect-free `next_day_prediction` service, wire it into `ReportGenerator`, and render a prominent prediction module in the mobile HTML template. Keep TickFlow behind normalized provider/report data; do not add intraday polling in v0.5.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, Jinja2, pytest, ruff, existing TickFlow/Anspire/review-source providers.

---

## File Structure

- Modify `apps/api/app/schemas/report.py`
  - Add prediction DTOs and `ReportDTO.next_day_predictions`.
  - Add algorithm version `next_day_prediction_v0_5`.
- Create `apps/api/app/services/next_day_prediction.py`
  - Own evidence gates, scoring, risk labels, condition text, and sorting.
  - Public function: `build_next_day_predictions(report, review_source_results=None, max_items=5)`.
- Modify `apps/api/app/services/report_generator.py`
  - Import and call the prediction service after `ReportDTO` creation and before structured review generation.
  - Persist predictions through existing DTO/snapshot writers.
- Modify `apps/api/app/services/structured_review_builder.py`
  - Prefer highest numeric prediction for `TomorrowJudgement` and focus candidates when predictions exist.
  - Preserve existing fallback behavior when predictions are empty.
- Modify `apps/api/app/renderers/templates/mobile_report.html.j2`
  - Add `次日强势概率与观察条件` section after section `02`.
  - Render no-data card when predictions are empty.
  - Shift subsequent structured section numbers to avoid duplicates.
- Create `apps/api/tests/test_next_day_prediction.py`
  - Unit coverage for scoring, no-data, front-row names, risk labels, and no fake content.
- Modify `apps/api/tests/test_report_api.py`
  - Assert API and snapshot include predictions and algorithm version.
  - Assert generated HTML contains the new section.
- Modify `apps/api/tests/test_structured_review.py`
  - Assert structured review uses predictions when present and preserves fallback when absent.

---

### Task 1: Add Prediction Schemas

**Files:**
- Modify: `apps/api/app/schemas/report.py`
- Test: `apps/api/tests/test_next_day_prediction.py`

- [ ] **Step 1: Add schema serialization test**

Create `apps/api/tests/test_next_day_prediction.py` with this first test:

```python
from app.schemas.report import (
    NextDayPrediction,
    PredictionConfidence,
    PredictionScoreBreakdown,
    PredictionStockFocus,
)


def test_next_day_prediction_schema_serializes_core_fields() -> None:
    prediction = NextDayPrediction(
        sector="PCB",
        rank=1,
        continuation_probability=76,
        confidence=PredictionConfidence.HIGH,
        headline="PCB 延续概率较高，观察前排承接。",
        front_row_stocks=[
            PredictionStockFocus(
                code="300476.SZ",
                name="胜宏科技",
                pct_change=20.0,
                role="前排强势股",
                source_tags=["同花顺复盘", "东方财富涨停复盘"],
                observation="观察胜宏科技竞价是否强于板块平均。",
            )
        ],
        trigger_conditions=["观察胜宏科技竞价是否强于板块平均。"],
        invalidation_conditions=["前排股集体低开低走。"],
        risk_labels=["高位加速"],
        score_breakdown=PredictionScoreBreakdown(
            review_confirmation=15,
            market_strength=20,
            front_row_quality=15,
            board_quality=5,
            catalyst=5,
            risk_penalty=-5,
            total=76,
        ),
        source_basis=["同花顺复盘", "东方财富涨停复盘"],
        evidence_notes=["两家复盘源共同确认 PCB 强势。"],
    )

    payload = prediction.model_dump(mode="json")

    assert payload["sector"] == "PCB"
    assert payload["confidence"] == "high"
    assert payload["front_row_stocks"][0]["name"] == "胜宏科技"
    assert payload["score_breakdown"]["total"] == 76
```

- [ ] **Step 2: Run schema test to verify it fails**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_next_day_prediction.py::test_next_day_prediction_schema_serializes_core_fields -q
```

Expected: FAIL with an import error for `NextDayPrediction` or related DTOs.

- [ ] **Step 3: Implement prediction DTOs**

Modify `apps/api/app/schemas/report.py`:

```python
class PredictionConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class PredictionStockFocus(BaseModel):
    code: str = ""
    name: str
    pct_change: float | None = None
    role: str
    source_tags: list[str] = Field(default_factory=list)
    observation: str


class PredictionScoreBreakdown(BaseModel):
    review_confirmation: int = 0
    market_strength: int = 0
    front_row_quality: int = 0
    board_quality: int = 0
    catalyst: int = 0
    risk_penalty: int = 0
    total: int


class NextDayPrediction(BaseModel):
    sector: str
    rank: int
    continuation_probability: int | None
    confidence: PredictionConfidence
    headline: str
    front_row_stocks: list[PredictionStockFocus] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    risk_labels: list[str] = Field(default_factory=list)
    score_breakdown: PredictionScoreBreakdown | None = None
    source_basis: list[str] = Field(default_factory=list)
    evidence_notes: list[str] = Field(default_factory=list)
```

Add this field to `ReportDTO` after `structured_review`:

```python
next_day_predictions: list[NextDayPrediction] = Field(default_factory=list)
```

Add this key to the `algorithm_versions` default factory:

```python
"next_day_prediction": "next_day_prediction_v0_5",
```

- [ ] **Step 4: Run schema test to verify it passes**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_next_day_prediction.py::test_next_day_prediction_schema_serializes_core_fields -q
```

Expected: PASS.

- [ ] **Step 5: Commit schema changes**

Run:

```bash
git add apps/api/app/schemas/report.py apps/api/tests/test_next_day_prediction.py
git commit -m "feat: add next-day prediction schema"
```

---

### Task 2: Implement Deterministic Prediction Service

**Files:**
- Create: `apps/api/app/services/next_day_prediction.py`
- Modify: `apps/api/tests/test_next_day_prediction.py`

- [ ] **Step 1: Add service behavior tests**

Append these tests and helpers to `apps/api/tests/test_next_day_prediction.py`:

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
from app.services.next_day_prediction import build_next_day_predictions


def _prediction_report(sectors: list[SectorCandidate]) -> ReportDTO:
    return ReportDTO(
        trade_date="2026-05-27",
        kind=ReportKind.CLOSE,
        title="2026-05-27 A股复盘",
        indices=[IndexSnapshot(name="上证指数", code="000001", close=4145.37, pct_change=0.5)],
        breadth=MarketBreadth(up_count=3200, down_count=1800, limit_up_count=86, limit_down_count=4),
        turnover_cny=12345.67,
        market_state_tags=["放量", "分化"],
        sectors=sectors,
        narrative=ReportNarrative(
            conclusion="",
            overview="",
            sector_commentary=[],
            watchlist=[],
            tomorrow="",
            risks=[],
        ),
        news=[],
    )


def _sector(
    *,
    name: str = "PCB",
    rank: int = 1,
    score: float = 82.0,
    pct_change: float = 4.5,
    top_stocks: list[StockCandidate] | None = None,
    news_summaries: list[str] | None = None,
    review_sources: list[str] | None = None,
    review_notes: list[str] | None = None,
) -> SectorCandidate:
    return SectorCandidate(
        name=name,
        score=score,
        rank=rank,
        pct_change=pct_change,
        reason="强度与复盘源共同确认",
        top_stocks=top_stocks or [],
        news_summaries=news_summaries or [],
        factor_scores={"limit_up": 80.0, "pct_change": 70.0},
        review_sources=review_sources or [],
        review_notes=review_notes or [],
    )


def test_double_source_sector_gets_high_confidence_prediction() -> None:
    report = _prediction_report(
        [
            _sector(
                top_stocks=[
                    StockCandidate(
                        code="300476.SZ",
                        name="胜宏科技",
                        pct_change=20.0,
                        tags=["同花顺复盘", "东方财富涨停复盘", "20CM"],
                    ),
                    StockCandidate(
                        code="600601.SH",
                        name="方正科技",
                        pct_change=10.0,
                        tags=["东方财富涨停复盘"],
                    ),
                ],
                news_summaries=["PCB 产业链催化延续。"],
                review_sources=["同花顺复盘", "东方财富涨停复盘"],
                review_notes=["PCB 方向前排强势，封板效率较高。"],
            )
        ]
    )

    predictions = build_next_day_predictions(report)

    assert predictions[0].sector == "PCB"
    assert predictions[0].continuation_probability is not None
    assert predictions[0].continuation_probability >= 70
    assert predictions[0].confidence == PredictionConfidence.HIGH
    assert predictions[0].source_basis == ["同花顺复盘", "东方财富涨停复盘"]


def test_no_curated_evidence_produces_insufficient_prediction() -> None:
    report = _prediction_report([_sector(review_sources=[], review_notes=[], top_stocks=[])])

    predictions = build_next_day_predictions(report)

    assert predictions[0].continuation_probability is None
    assert predictions[0].confidence == PredictionConfidence.INSUFFICIENT
    assert "证据不足" in predictions[0].headline


def test_front_row_stock_names_appear_in_trigger_conditions() -> None:
    report = _prediction_report(
        [
            _sector(
                top_stocks=[
                    StockCandidate(code="300476.SZ", name="胜宏科技", pct_change=20.0, tags=["同花顺复盘"]),
                    StockCandidate(code="600601.SH", name="方正科技", pct_change=10.0, tags=["东方财富涨停复盘"]),
                ],
                review_sources=["同花顺复盘"],
                review_notes=["PCB 前排强势。"],
            )
        ]
    )

    predictions = build_next_day_predictions(report)
    condition_text = "\n".join(predictions[0].trigger_conditions)

    assert "胜宏科技" in condition_text or "方正科技" in condition_text


def test_risk_labels_are_deterministic() -> None:
    report = _prediction_report(
        [
            _sector(
                review_sources=["同花顺复盘"],
                review_notes=["PCB 前排活跃。"],
                news_summaries=[],
                top_stocks=[],
            )
        ]
    )

    predictions = build_next_day_predictions(report)

    assert "单源确认" in predictions[0].risk_labels
    assert "催化不足" in predictions[0].risk_labels


def test_empty_report_generates_no_prediction_content() -> None:
    report = _prediction_report([])

    assert build_next_day_predictions(report) == []
```

- [ ] **Step 2: Run service tests to verify they fail**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_next_day_prediction.py -q
```

Expected: FAIL with import error for `app.services.next_day_prediction`.

- [ ] **Step 3: Implement prediction service**

Create `apps/api/app/services/next_day_prediction.py` with deterministic helpers matching the spec:

```python
import re

from app.providers.review_sources import ReviewSourceResult
from app.schemas.report import (
    NextDayPrediction,
    PredictionConfidence,
    PredictionScoreBreakdown,
    PredictionStockFocus,
    ReportDTO,
    SectorCandidate,
    StockCandidate,
)

CURATED_REVIEW_SOURCES = {"同花顺复盘", "东方财富涨停复盘"}
HEIGHT_PATTERN = re.compile(r"(?:\d+板|\d+天\d+板|连板|高度)")
POSITIVE_BOARD_WORDS = ("高", "强", "较好")
WEAK_BOARD_WORDS = ("低", "弱", "较差")
HIGH_RISK_MARKET_TAGS = ("分化", "退潮", "缩量")


def build_next_day_predictions(
    report: ReportDTO,
    review_source_results: list[ReviewSourceResult] | None = None,
    max_items: int = 5,
) -> list[NextDayPrediction]:
    if max_items <= 0 or not report.sectors:
        return []
    board_efficiency = _board_efficiency(review_source_results or [])
    predictions = [_prediction_for_sector(report, sector, board_efficiency) for sector in report.sectors[:max_items]]
    return sorted(
        predictions,
        key=lambda item: (
            item.continuation_probability is not None,
            item.continuation_probability or -1,
            -item.rank,
        ),
        reverse=True,
    )


def _prediction_for_sector(
    report: ReportDTO,
    sector: SectorCandidate,
    board_efficiency: str | None,
) -> NextDayPrediction:
    source_basis = _curated_sources(sector.review_sources)
    evidence_notes = _evidence_notes(sector)
    front_row = [_stock_focus(stock) for stock in sector.top_stocks if stock.name]
    if not _has_sufficient_evidence(sector, source_basis):
        return NextDayPrediction(
            sector=sector.name,
            rank=sector.rank,
            continuation_probability=None,
            confidence=PredictionConfidence.INSUFFICIENT,
            headline="证据不足，仅保留观察",
            front_row_stocks=front_row,
            trigger_conditions=_insufficient_trigger_conditions(sector),
            invalidation_conditions=_invalidation_conditions(report, sector),
            risk_labels=_risk_labels(report, sector, source_basis),
            score_breakdown=None,
            source_basis=source_basis,
            evidence_notes=evidence_notes,
        )

    breakdown = _score_breakdown(report, sector, source_basis, board_efficiency)
    probability = breakdown.total
    confidence = _confidence(probability)
    return NextDayPrediction(
        sector=sector.name,
        rank=sector.rank,
        continuation_probability=probability,
        confidence=confidence,
        headline=_headline(sector.name, probability),
        front_row_stocks=front_row,
        trigger_conditions=_trigger_conditions(report, sector),
        invalidation_conditions=_invalidation_conditions(report, sector),
        risk_labels=_risk_labels(report, sector, source_basis),
        score_breakdown=breakdown,
        source_basis=source_basis,
        evidence_notes=evidence_notes,
    )
```

Complete the helpers in the same file:

```python
def _curated_sources(sources: list[str]) -> list[str]:
    return [source for source in sources if source in CURATED_REVIEW_SOURCES]


def _has_sufficient_evidence(sector: SectorCandidate, source_basis: list[str]) -> bool:
    return bool(source_basis or sector.top_stocks or (sector.rank <= 3 and sector.review_notes))


def _stock_focus(stock: StockCandidate) -> PredictionStockFocus:
    return PredictionStockFocus(
        code=stock.code,
        name=stock.name,
        pct_change=stock.pct_change,
        role="前排强势股",
        source_tags=stock.tags,
        observation=f"观察{stock.name}竞价与开盘承接是否强于板块平均。",
    )


def _score_breakdown(
    report: ReportDTO,
    sector: SectorCandidate,
    source_basis: list[str],
    board_efficiency: str | None,
) -> PredictionScoreBreakdown:
    review_confirmation = 15 if len(set(source_basis)) >= 2 else 8 if source_basis else 0
    market_strength = round(min(max(sector.score, 0), 100) * 0.25)
    rank_bonus = 5 if sector.rank == 1 else 3 if sector.rank in {2, 3} else 0
    pct_bonus = 5 if sector.pct_change >= 3 else -5 if sector.pct_change <= 0 else 0
    front_row_quality = min(len(sector.top_stocks) * 5, 15)
    if any(_is_20cm_stock(stock) for stock in sector.top_stocks):
        front_row_quality += 4
    if _has_height_evidence(sector):
        front_row_quality += 6
    board_quality = _board_quality_points(board_efficiency)
    catalyst = 8 if len(_distinct_text(sector.news_summaries)) >= 2 else 5 if sector.news_summaries else 0
    risk_penalty = _risk_penalty(report, sector)
    total = _clamp_int(
        35
        + review_confirmation
        + market_strength
        + rank_bonus
        + pct_bonus
        + front_row_quality
        + board_quality
        + catalyst
        + risk_penalty
    )
    return PredictionScoreBreakdown(
        review_confirmation=review_confirmation,
        market_strength=market_strength + rank_bonus + pct_bonus,
        front_row_quality=front_row_quality,
        board_quality=board_quality,
        catalyst=catalyst,
        risk_penalty=risk_penalty,
        total=total,
    )


def _risk_penalty(report: ReportDTO, sector: SectorCandidate) -> int:
    penalty = 0
    if not sector.top_stocks:
        penalty -= 10
    if len(sector.review_notes) <= 1 and not sector.news_summaries:
        penalty -= 5
    if report.breadth.limit_down_count >= 10 or any(tag in "".join(report.market_state_tags) for tag in HIGH_RISK_MARKET_TAGS):
        penalty -= 5
    return penalty


def _risk_labels(report: ReportDTO, sector: SectorCandidate, source_basis: list[str]) -> list[str]:
    labels: list[str] = []
    if not sector.top_stocks:
        labels.append("前排缺失")
    if len(set(source_basis)) == 1:
        labels.append("单源确认")
    if _has_height_evidence(sector):
        labels.append("高位加速")
    if report.breadth.limit_down_count >= 10 or any(tag in "".join(report.market_state_tags) for tag in HIGH_RISK_MARKET_TAGS):
        labels.append("情绪分歧")
    if not sector.news_summaries:
        labels.append("催化不足")
    if sector.score >= 70 and len(sector.review_notes) <= 1:
        labels.append("后排补涨风险")
    return _dedupe(labels)
```

Add the remaining helper functions:

```python
def _trigger_conditions(report: ReportDTO, sector: SectorCandidate) -> list[str]:
    stocks = [stock.name for stock in sector.top_stocks if stock.name][:3]
    stock_text = "、".join(stocks)
    first = (
        f"观察{stock_text}竞价是否强于板块平均。"
        if stock_text
        else "暂未解析到明确前排股，需先确认板块内主动领涨标的。"
    )
    return [
        first,
        f"观察{sector.name}是否继续处于市场强势组前列。",
        "指数不出现明显放量下杀，成交额维持活跃区间。",
        "前排分歧温和，板块内不出现集体负反馈。",
    ]


def _insufficient_trigger_conditions(sector: SectorCandidate) -> list[str]:
    return [
        "同花顺/东方财富复盘证据不足，暂不生成强势概率。",
        f"需要先确认{sector.name}是否有明确前排股和复盘源确认。",
        "仅保留观察，不把市场排名单独当作延续依据。",
    ]


def _invalidation_conditions(report: ReportDTO, sector: SectorCandidate) -> list[str]:
    stocks = [stock.name for stock in sector.top_stocks if stock.name][:3]
    stock_text = "、".join(stocks) if stocks else "前排股"
    return [
        f"{stock_text}集体低开低走。",
        f"{sector.name}高开后快速跌出强势排名。",
        "指数放量下杀且高位股开板反馈扩大。",
        "催化消息不能映射到价格强度。",
    ]


def _headline(sector_name: str, probability: int) -> str:
    if probability >= 70:
        return f"{sector_name}延续概率较高，重点观察前排分歧承接。"
    if probability >= 50:
        return f"{sector_name}处于延续观察区，需要前排确认。"
    return f"{sector_name}延续条件偏弱，优先等待确认。"


def _confidence(probability: int) -> PredictionConfidence:
    if probability >= 70:
        return PredictionConfidence.HIGH
    if probability >= 50:
        return PredictionConfidence.MEDIUM
    return PredictionConfidence.LOW


def _evidence_notes(sector: SectorCandidate) -> list[str]:
    return _dedupe([*sector.review_notes, *sector.news_summaries])[:4]


def _board_efficiency(results: list[ReviewSourceResult]) -> str | None:
    for result in results:
        if result.board_efficiency:
            return result.board_efficiency
    return None


def _board_quality_points(board_efficiency: str | None) -> int:
    if not board_efficiency:
        return 0
    if any(word in board_efficiency for word in POSITIVE_BOARD_WORDS):
        return 5
    if any(word in board_efficiency for word in WEAK_BOARD_WORDS):
        return -5
    return 0


def _is_20cm_stock(stock: StockCandidate) -> bool:
    tag_text = " ".join(stock.tags)
    return stock.pct_change >= 19.5 or "20CM" in tag_text.upper()


def _has_height_evidence(sector: SectorCandidate) -> bool:
    text = "\n".join([*sector.review_notes, *(tag for stock in sector.top_stocks for tag in stock.tags)])
    return bool(HEIGHT_PATTERN.search(text))


def _distinct_text(values: list[str]) -> list[str]:
    return _dedupe([value.strip() for value in values if value.strip()])


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _clamp_int(value: int) -> int:
    return max(0, min(100, int(round(value))))
```

- [ ] **Step 4: Run service tests to verify they pass**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_next_day_prediction.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit prediction service**

Run:

```bash
git add apps/api/app/services/next_day_prediction.py apps/api/tests/test_next_day_prediction.py
git commit -m "feat: score next-day prediction candidates"
```

---

### Task 3: Wire Predictions Into Report Generation

**Files:**
- Modify: `apps/api/app/services/report_generator.py`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add report persistence assertions**

In `apps/api/tests/test_report_api.py`, extend `test_report_generator_writes_structured_review_to_report_and_snapshot` with:

```python
    assert result.report.next_day_predictions
    assert result.report.algorithm_versions["next_day_prediction"] == "next_day_prediction_v0_5"
    assert report_dto["next_day_predictions"] == snapshot["report"]["next_day_predictions"]
    assert snapshot["report"]["algorithm_versions"]["next_day_prediction"] == "next_day_prediction_v0_5"
```

In `test_create_close_report_api_returns_generated_report`, add:

```python
    assert "next_day_predictions" in payload["report"]
    assert payload["report"]["algorithm_versions"]["next_day_prediction"] == "next_day_prediction_v0_5"
```

- [ ] **Step 2: Run report API tests to verify they fail**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_report_api.py::test_report_generator_writes_structured_review_to_report_and_snapshot tests/test_report_api.py::test_create_close_report_api_returns_generated_report -q
```

Expected: FAIL because `next_day_predictions` is empty or not wired.

- [ ] **Step 3: Wire prediction service in `ReportGenerator`**

Modify imports in `apps/api/app/services/report_generator.py`:

```python
from app.services.next_day_prediction import build_next_day_predictions
```

After `report = ReportDTO(...)` and before `generate_structured_review(...)`, add:

```python
        report.next_day_predictions = build_next_day_predictions(
            report=report,
            review_source_results=review_source_results,
        )
```

- [ ] **Step 4: Run report API tests to verify they pass**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_report_api.py::test_report_generator_writes_structured_review_to_report_and_snapshot tests/test_report_api.py::test_create_close_report_api_returns_generated_report -q
```

Expected: PASS.

- [ ] **Step 5: Commit report generator wiring**

Run:

```bash
git add apps/api/app/services/report_generator.py apps/api/tests/test_report_api.py
git commit -m "feat: persist next-day predictions in reports"
```

---

### Task 4: Align Structured Review With Predictions

**Files:**
- Modify: `apps/api/app/services/structured_review_builder.py`
- Modify: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Add structured review prediction alignment test**

In `apps/api/tests/test_structured_review.py`, import these DTOs:

```python
from app.schemas.report import NextDayPrediction, PredictionConfidence, PredictionStockFocus
```

Add this test:

```python
def test_build_structured_review_prefers_highest_prediction_for_tomorrow_view() -> None:
    report = _fake_report()
    report.next_day_predictions = [
        NextDayPrediction(
            sector="PCB",
            rank=2,
            continuation_probability=78,
            confidence=PredictionConfidence.HIGH,
            headline="PCB 延续概率较高，重点观察前排分歧承接。",
            front_row_stocks=[
                PredictionStockFocus(
                    code="300476.SZ",
                    name="胜宏科技",
                    pct_change=20.0,
                    role="前排强势股",
                    source_tags=["同花顺复盘"],
                    observation="观察胜宏科技竞价与开盘承接是否强于板块平均。",
                )
            ],
            trigger_conditions=["观察胜宏科技竞价是否强于板块平均。"],
            invalidation_conditions=["胜宏科技低开低走。"],
            risk_labels=[],
            source_basis=["同花顺复盘"],
        )
    ]

    review = build_structured_review(report)

    assert review.tomorrow_judgement.most_likely_to_continue == "PCB"
    assert review.next_day_opportunity.focus_candidates[0] == "观察胜宏科技竞价与开盘承接是否强于板块平均。"
```

- [ ] **Step 2: Run structured review test to verify it fails**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_structured_review.py::test_build_structured_review_prefers_highest_prediction_for_tomorrow_view -q
```

Expected: FAIL because builder still uses `report.sectors[0]`.

- [ ] **Step 3: Implement prediction-aware builder helpers**

Modify `apps/api/app/services/structured_review_builder.py`.

Add import:

```python
from app.schemas.report import NextDayPrediction
```

Add helper functions near existing private helpers:

```python
def _top_numeric_prediction(report: ReportDTO) -> NextDayPrediction | None:
    numeric = [item for item in report.next_day_predictions if item.continuation_probability is not None]
    if not numeric:
        return None
    return sorted(numeric, key=lambda item: (item.continuation_probability or 0, -item.rank), reverse=True)[0]


def _prediction_focus_candidates(report: ReportDTO) -> list[str]:
    prediction = _top_numeric_prediction(report)
    if prediction is None:
        return []
    focus = [stock.observation for stock in prediction.front_row_stocks[:3] if stock.observation]
    if focus:
        return focus
    return prediction.trigger_conditions[:2]
```

In `build_structured_review`, add after `leader` and `runner_up`:

```python
    top_prediction = _top_numeric_prediction(report)
    leader_name = top_prediction.sector if top_prediction is not None else leader.name if leader else "暂无主线"
```

Keep `runner_up_name` as existing sector-based fallback.

Modify `_build_next_day_opportunity`:

```python
def _build_next_day_opportunity(report: ReportDTO, leader: SectorCandidate | None) -> NextDayOpportunityPlan:
    prediction_focus = _prediction_focus_candidates(report)
    if prediction_focus:
        focus = prediction_focus
    else:
        leader_name = leader.name if leader else "主线"
        focus = [f"{leader_name}核心股承接确认"]
        focus.extend(f"{sector.name}前排分歧转强" for sector in report.sectors[1:3])
    return NextDayOpportunityPlan(
        focus_candidates=focus,
        position_discipline=["只观察确认后的承接，不追一致加速。", "弱分支只看修复，不做主线预设。"],
        trigger_conditions=["指数不出现明显放量下杀", "主线前排分歧温和", "成交额维持活跃区间"],
        avoid_conditions=["缩量冲高回落", "无催化后排补涨", "高位一致加速后的被动追高"],
    )
```

- [ ] **Step 4: Run structured review tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_structured_review.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit structured builder alignment**

Run:

```bash
git add apps/api/app/services/structured_review_builder.py apps/api/tests/test_structured_review.py
git commit -m "feat: align structured review with predictions"
```

---

### Task 5: Render Prediction Module In HTML

**Files:**
- Modify: `apps/api/app/renderers/templates/mobile_report.html.j2`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add HTML rendering assertions**

In `apps/api/tests/test_report_api.py`, add a new test near renderer tests:

```python
def test_mobile_report_html_renders_next_day_prediction_section() -> None:
    report = ReportDTO(
        trade_date="2026-05-27",
        kind=ReportKind.CLOSE,
        title="2026-05-27 A股复盘",
        indices=[IndexSnapshot(name="上证指数", code="000001", close=4145.37, pct_change=0.5)],
        breadth=MarketBreadth(up_count=3200, down_count=1800, limit_up_count=86, limit_down_count=4),
        turnover_cny=12345.67,
        market_state_tags=["放量", "分化"],
        sectors=[SectorCandidate(name="PCB", score=82, rank=1, pct_change=4.5, reason="强势")],
        narrative=FakeLLMProvider().generate_narrative({"raw_sectors": []}),
        news=[],
        next_day_predictions=[
            NextDayPrediction(
                sector="PCB",
                rank=1,
                continuation_probability=76,
                confidence=PredictionConfidence.HIGH,
                headline="PCB 延续概率较高，重点观察前排分歧承接。",
                trigger_conditions=["观察胜宏科技竞价是否强于板块平均。"],
                invalidation_conditions=["胜宏科技低开低走。"],
                risk_labels=["高位加速"],
                source_basis=["同花顺复盘"],
            )
        ],
    )
    report.structured_review = build_structured_review(report)

    html = render_mobile_report_html(report)

    assert "次日强势概率与观察条件" in html
    assert "PCB" in html
    assert "76%" in html
    assert "观察胜宏科技竞价是否强于板块平均。" in html
```

Add `NextDayPrediction` and `PredictionConfidence` to the existing `app.schemas.report` imports in this test file.

- [ ] **Step 2: Run HTML test to verify it fails**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_report_api.py::test_mobile_report_html_renders_next_day_prediction_section -q
```

Expected: FAIL because template does not render prediction section.

- [ ] **Step 3: Add template styles**

Modify `apps/api/app/renderers/templates/mobile_report.html.j2` style block with:

```css
    .prediction-card { background: linear-gradient(180deg, #fffaf0, var(--panel)); border: 1px solid var(--gold); border-radius: 16px; padding: 14px; margin-top: 12px; }
    .prediction-head { display: flex; justify-content: space-between; gap: 10px; align-items: center; border-bottom: 1px solid var(--line); padding-bottom: 8px; margin-bottom: 10px; }
    .probability { color: var(--red); font-size: 24px; font-weight: 950; white-space: nowrap; }
    .confidence { border-radius: 999px; padding: 3px 9px; background: var(--navy); color: var(--gold); font-size: 11px; font-weight: 900; }
    .risk-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .risk-label { border: 1px solid var(--line); background: #fff; color: var(--muted); border-radius: 999px; padding: 3px 8px; font-size: 11px; font-weight: 800; }
```

- [ ] **Step 4: Render prediction section after section 02**

Insert after the `02 先给结论` section:

```jinja2
          {% set predictions = report.next_day_predictions %}
          <section>
            <div class="section-title"><span class="section-num">03</span><h2>次日强势概率与观察条件</h2></div>
            <p class="lead">概率只表示延续观察强度，必须由次日触发条件确认。</p>
            {% if predictions %}
              {% for prediction in predictions %}
                <article class="prediction-card">
                  <div class="prediction-head">
                    <div>
                      <strong>{{ loop.index }}. {{ prediction.sector }}</strong>
                      <span class="confidence">{{ prediction.confidence|upper }}</span>
                      <p class="muted">{{ prediction.headline }}</p>
                    </div>
                    <div class="probability">{% if prediction.continuation_probability is not none %}{{ prediction.continuation_probability }}%{% else %}证据不足{% endif %}</div>
                  </div>
                  {% if prediction.front_row_stocks %}
                    <table aria-label="次日前排观察">
                      <tr><th>前排股</th><th>涨跌幅</th><th>观察</th></tr>
                      {% for stock in prediction.front_row_stocks %}
                        <tr><td>{{ stock.name }} {% if stock.code %}{{ stock.code }}{% endif %}</td><td>{% if stock.pct_change is not none %}{{ "%+.2f"|format(stock.pct_change) }}%{% else %}-{% endif %}</td><td>{{ stock.observation }}</td></tr>
                      {% endfor %}
                    </table>
                  {% endif %}
                  <div class="grid-2">
                    <div><div class="mini-title">触发条件</div><ul>{% for item in prediction.trigger_conditions %}<li>{{ item }}</li>{% endfor %}</ul></div>
                    <div><div class="mini-title">失效条件</div><ul>{% for item in prediction.invalidation_conditions %}<li>{{ item }}</li>{% endfor %}</ul></div>
                  </div>
                  {% if prediction.risk_labels %}<div class="risk-row">{% for label in prediction.risk_labels %}<span class="risk-label">{{ label }}</span>{% endfor %}</div>{% endif %}
                  {% if prediction.source_basis %}<p class="muted subsection">依据：{{ prediction.source_basis|join("、") }}</p>{% endif %}
                </article>
              {% endfor %}
            {% else %}
              <div class="note-card">
                <p>同花顺/东方财富复盘证据不足，今日不生成强势概率。</p>
                <p class="muted">可继续查看盘面总览与强势板块，但次日强势判断需等待复盘源恢复。</p>
              </div>
            {% endif %}
          </section>
```

Shift later static section numbers:

- `盘面总览`: `04`
- `各板块详细分析`: `05`
- `盘后 / 隔夜消息梳理`: `06`
- `板块持续性排序`: `07`
- `资金轮动路径分析`: `08`
- `明日可介入标的与仓位建议`: `09`
- Watchlist: `10`
- Dynamic final numbers become `11/10`, `12/11`, `13/12` depending on watchlist.

- [ ] **Step 5: Run HTML test to verify it passes**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_report_api.py::test_mobile_report_html_renders_next_day_prediction_section -q
```

Expected: PASS.

- [ ] **Step 6: Commit HTML rendering**

Run:

```bash
git add apps/api/app/renderers/templates/mobile_report.html.j2 apps/api/tests/test_report_api.py
git commit -m "feat: render next-day prediction module"
```

---

### Task 6: Full Validation And Fixups

**Files:**
- Modify only files needed to fix test or lint failures from prior tasks.

- [ ] **Step 1: Run ruff**

Run:

```bash
cd apps/api && .venv/bin/python -m ruff check app tests
```

Expected: PASS.

- [ ] **Step 2: Run full pytest**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest -q
```

Expected: PASS with all existing tests plus new prediction tests.

- [ ] **Step 3: Inspect generated report manually if tests pass**

Run an API generation path already covered by tests or use an existing generated HTML artifact. Confirm the rendered HTML includes:

- `次日强势概率与观察条件`
- Numeric probability for eligible candidates.
- `证据不足` only for insufficient candidates.
- No fabricated sector or stock names.

- [ ] **Step 4: Commit validation fixups if any**

If changes were made during validation, run:

```bash
git add apps/api/app apps/api/tests
git commit -m "fix: stabilize next-day prediction validation"
```

If no changes were needed, do not create an empty commit.

---

## Final Verification Checklist

- [ ] `apps/api/app/schemas/report.py` contains prediction DTOs and `ReportDTO.next_day_predictions`.
- [ ] `apps/api/app/services/next_day_prediction.py` is deterministic and has no provider/network calls.
- [ ] `apps/api/app/services/report_generator.py` assigns predictions before structured review generation.
- [ ] `apps/api/app/services/structured_review_builder.py` uses predictions when present and falls back when absent.
- [ ] `apps/api/app/renderers/templates/mobile_report.html.j2` renders the new HTML module prominently.
- [ ] `apps/api/tests/test_next_day_prediction.py` covers scoring, insufficient evidence, stock names, risk labels, and empty reports.
- [ ] `cd apps/api && .venv/bin/python -m ruff check app tests` passes.
- [ ] `cd apps/api && .venv/bin/python -m pytest -q` passes.
