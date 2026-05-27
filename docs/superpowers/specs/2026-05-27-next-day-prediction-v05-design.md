# Next-Day Prediction v0.5 Design Spec

## Goal

Build a built-in next-day prediction module for the daily A-share review report. The module converts same-day strong-sector evidence into explicit next-day observation probabilities, trigger conditions, invalidation conditions, front-row stocks, and risk labels.

The HTML report is the primary product artifact. The prediction module must make the report better at answering one question: after the close, which sectors and stocks were strongest today, and what would need to happen tomorrow for that strength to continue?

## User-Approved Direction

The selected approach is **B: probability + condition model**.

The report should not output buy/sell instructions. It should use language such as:

- 观察
- 确认
- 回避
- 承接
- 分歧
- 失效

The report must not fabricate production content. If factual inputs are missing, the module should output evidence-insufficient wording instead of fake sectors, fake stocks, fake probabilities, or fake catalysts.

## Source Boundary

The prediction module must preserve the existing source boundary:

| Data role | Allowed source |
| --- | --- |
| Curated daily review evidence | 同花顺复盘 `https://stock.10jqka.com.cn/fupan/` and 东方财富涨停复盘 `https://stock.eastmoney.com/a/cztfp.html` only |
| Market / quote strength | TickFlow first, including official Python SDK / HTTP API quote data; existing market provider as fallback only where already supported |
| News / catalyst evidence | Anspire news provider |
| Watchlist observation | User-imported watchlist, disabled by default |

AkShare or other market data adapters must not be described as curated review sources.

## Non-Goals

- No intraday real-time trading assistant in v0.5; TickFlow intraday data is reserved for confirmation signals and a later v0.6 intraday monitor.
- No order instructions, price targets, position sizing orders, or guaranteed recommendations.
- No LLM-dependent scoring for v0.5. The MVP scoring model is deterministic and testable.
- No fake fallback content in production paths.
- No expansion of curated review sources beyond 同花顺 and 东方财富 in this version.

## Inputs

The prediction module consumes only normalized data that already exists in the report pipeline, plus small additions to carry source evidence more explicitly.

### SectorCandidate Inputs

For each `SectorCandidate`:

- `name`: sector name.
- `rank`: current report rank.
- `score`: existing sector strength score.
- `pct_change`: same-day sector change.
- `factor_scores`: existing factor breakdown.
- `top_stocks`: parsed front-row stock candidates from review sources.
- `news_summaries`: Anspire or configured news summaries matched to the sector.
- `review_sources`: curated review sources that confirmed the sector.
- `review_notes`: notes from 同花顺/东方财富.

### Market Inputs

TickFlow should be treated as the preferred market data provider because its official Python SDK / API supports A-shares, ETFs, US stocks, Hong Kong stocks, domestic futures, realtime quotes, universe data, intraday bars, and WebSocket streams. In v0.5, the prediction module should consume TickFlow-derived close or latest quote strength through the existing normalized report pipeline. It should not introduce a live polling loop inside report generation.

From `ReportDTO`:

- `breadth.limit_up_count`
- `breadth.limit_down_count`
- `breadth.up_count`
- `breadth.down_count`
- `turnover_cny`
- `market_state_tags`
- TickFlow-derived all-market quote breadth and strong-stock grouping when `MARKET_PROVIDER=tickflow`.

### Review Source Inputs

From `ReviewSourceResult`:

- `source`
- `source_url`
- `themes`
- `hot_stocks`
- `market_notes`
- `board_efficiency`

The scoring module should not call web providers directly. `ReportGenerator` already owns provider collection and should pass normalized sector/report data into the predictor.

## Output Model

Add a prediction DTO to `apps/api/app/schemas/report.py`.

Recommended DTO shape:

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

Add to `ReportDTO`:

```python
next_day_predictions: list[NextDayPrediction] = Field(default_factory=list)
```

Add algorithm version:

```python
"next_day_prediction": "next_day_prediction_v0_5"
```

## Scoring Model

The model outputs a `0-100` continuation probability only when evidence is sufficient.

### Evidence Sufficiency Gate

A sector is eligible for a numeric probability when it has at least one of these:

- Confirmed by 同花顺 or 东方财富 in `review_sources`.
- Has at least one parsed front-row stock from curated review evidence.
- Has strong market rank and source note evidence: `rank <= 3` and non-empty `review_notes`.

If the sector fails the gate:

- `continuation_probability = None`
- `confidence = "insufficient"`
- `headline = "证据不足，仅保留观察"`
- Conditions explain which evidence is missing.

### Score Components

Start from `base = 35` for eligible sectors. Add and subtract the following deterministic components:

| Component | Rule | Points |
| --- | --- | --- |
| Review confirmation | One curated source confirms sector | `+8` |
| Review confirmation | Both curated sources confirm sector | `+15` total |
| Market strength | Existing `sector.score` mapped as `round(min(score, 100) * 0.25)` | `0..25` |
| Rank bonus | `rank == 1` | `+5` |
| Rank bonus | `rank == 2 or rank == 3` | `+3` |
| Sector pct change | `pct_change >= 3` | `+5` |
| Sector pct change | `pct_change <= 0` | `-5` |
| Front-row quality | Each front-row stock | `+5`, capped at `+15` |
| Front-row quality | Any stock with `pct_change >= 19.5` or `20CM` tag/note | `+4` |
| Height evidence | Stock note contains board-height pattern such as `连板`, `N板`, `天N板`, `高度` | `+6` |
| Board quality | `board_efficiency` contains positive wording such as `高`, `强`, `较好` | `+5` |
| Board quality | `board_efficiency` contains weak wording such as `低`, `弱`, `较差` | `-5` |
| Catalyst | Matched Anspire/news summary exists | `+5` |
| Catalyst | Two or more distinct news summaries exist | `+8` total |
| Risk penalty | No parsed front-row stock | `-10` |
| Risk penalty | Only one weak review note and no news catalyst | `-5` |
| Risk penalty | `limit_down_count >= 10` or market tag contains high-risk wording | `-5` |

Clamp final score to `0..100` and round to integer.

### Confidence Mapping

- `>= 70`: `high`
- `50..69`: `medium`
- `< 50`: `low`
- Evidence gate failed: `insufficient`

### Risk Labels

Risk labels are deterministic and explain why a probability should not be treated as certainty:

- `前排缺失`: no parsed front-row stocks.
- `单源确认`: only one curated review source confirms sector.
- `高位加速`: height evidence exists or note contains high-board wording.
- `情绪分歧`: limit-down count elevated or market tags imply分化/退潮/缩量.
- `催化不足`: no matched news/catalyst summary.
- `后排补涨风险`: review evidence weak but sector score remains high.

## Trigger and Invalidation Conditions

The module should generate sector-specific, readable conditions.

### Trigger Conditions

For each prediction, include 3-5 concrete observations:

- Front-row stocks open with承接 rather than immediate放量核按钮.
- Sector remains in top market strength group during the first hour.
- Same-day leader or front-row names do not出现集体负反馈.
- Review-source catalyst continues to be discussed by market participants.
- Index does not放量下杀 and成交额 remains in an active range.

When front-row stocks exist, mention names directly:

- `观察胜宏科技、方正科技竞价是否强于板块平均。`

When front-row stocks do not exist, use evidence-limited wording:

- `暂未解析到明确前排股，需先确认板块内主动领涨标的。`

### Invalidation Conditions

Include 3-5 concrete invalidation rules:

- Front-row stocks集体低开低走.
- Sector opens high but quickly跌出强势排名.
- Review-source theme has no new承接 and后排补涨明显回落.
- Index放量下杀 while high-board stocks open板.
- Catalyst news does not map to price strength.

## Integration Points

### TickFlow Provider Direction

The existing `apps/api/app/providers/tickflow.py` already has an HTTP provider shape for batch quotes, universe quotes, A-share universe strength, industry universes, and watchlist quotes. During implementation, keep the report predictor behind normalized provider methods instead of binding directly to a specific SDK call.

Implementation should support two compatible directions:

1. Preserve the current HTTP adapter as the stable default.
2. Add a thin SDK-backed adapter later if the official `tickflow` Python package is installed and offers equivalent quote/universe/intraday methods.

The prediction service should not know which adapter supplied the data. It should only consume `ReportDTO`, sector candidates, and optional review-source evidence.

### Future Intraday Confirmation

TickFlow intraday support should become a separate module after v0.5, not a blocker for this implementation. The proposed v0.6 extension is:

- Store prediction candidates after close.
- During the next trading day, use TickFlow realtime quotes / intraday bars / WebSocket streams to check trigger conditions.
- Mark each candidate as `confirmed`, `watching`, or `invalidated`.
- Append an intraday confirmation block to a later report or dashboard without rewriting the original after-close evidence.

### Service

Create `apps/api/app/services/next_day_prediction.py`.

Responsibilities:

- Accept `ReportDTO` and optional `review_source_results`.
- Return `list[NextDayPrediction]`.
- Keep all scoring deterministic and side-effect free.
- Include small private helpers for evidence gates, scoring, risk labels, and condition generation.

Public function:

```python
def build_next_day_predictions(
    report: ReportDTO,
    review_source_results: list[ReviewSourceResult] | None = None,
    max_items: int = 5,
) -> list[NextDayPrediction]:
    ...
```

### Report Generator

Modify `apps/api/app/services/report_generator.py`:

1. Build `sector_candidates` as today.
2. Create `ReportDTO`.
3. Run `build_next_day_predictions(report, review_source_results)` before structured review generation.
4. Assign `report.next_day_predictions`.
5. Persist predictions automatically through existing `report.model_dump()` paths.
6. Include `next_day_prediction_v0_5` in algorithm versions.

The structured review builder can consume `report.next_day_predictions` in a later task, but v0.5 should at least render the dedicated HTML module directly from `ReportDTO`.

### HTML Report

Modify `apps/api/app/renderers/templates/mobile_report.html.j2`.

Add a prominent section after `02 先给结论` and before `03 盘面总览`:

- Title: `次日强势概率与观察条件`
- Each prediction card shows:
  - sector name and rank
  - continuation probability or `证据不足`
  - confidence badge
  - front-row stocks table
  - trigger conditions
  - invalidation conditions
  - risk labels
  - source basis

Renumber later sections dynamically or insert the section as `03` and shift following structured sections by one. The template should avoid duplicated section numbers when watchlist is enabled.

### Structured Review Builder

Modify `apps/api/app/services/structured_review_builder.py` only enough to avoid contradiction:

- If `report.next_day_predictions` exists, `TomorrowJudgement.most_likely_to_continue` should prefer the highest numeric prediction sector.
- `NextDayOpportunityPlan.focus_candidates` should use prediction front-row observations when available.
- Existing fallback behavior remains when predictions are empty.

This keeps the new module aligned with the legacy structured review sections.

## No-Data Behavior

If curated review sources fail or produce no usable evidence:

- Do not manufacture strong sectors.
- Preserve existing provider status in `snapshot.json`.
- Render a prediction module with a muted no-data card:
  - `同花顺/东方财富复盘证据不足，今日不生成强势概率。`
  - `可继续查看盘面总览与强势板块，但次日强势判断需等待复盘源恢复。`

If some sectors pass the evidence gate and others do not:

- Show numeric probability for eligible sectors.
- Show `证据不足` for top-ranked but unconfirmed sectors only if they are included for context.
- Default `max_items=5` and order by probability descending, then report rank.

## Tests

Add focused tests before implementation.

### `apps/api/tests/test_next_day_prediction.py`

Required cases:

1. **Double-source sector gets high confidence**
   - Build a `ReportDTO` sector with two review sources, front-row stocks, news summary, and high sector score.
   - Assert probability is numeric, `>= 70`, confidence is `high`, and source basis includes both review sources.

2. **No curated evidence produces insufficient result**
   - Build a top-ranked sector with market score but no review source, no review note, and no front-row stock.
   - Assert `continuation_probability is None`, confidence is `insufficient`, and headline says evidence is insufficient.

3. **Front-row stock names appear in trigger conditions**
   - Use two front-row stocks.
   - Assert trigger condition text contains at least one stock name.

4. **Risk labels are deterministic**
   - Single-source sector with no news summary.
   - Assert labels include `单源确认` and `催化不足`.

5. **No fake content is generated**
   - Empty report sectors.
   - Assert returned predictions are an empty list.

### Existing Tests to Update

- `apps/api/tests/test_structured_review.py`
  - Add assertion that structured review can consume predictions without changing existing fallback behavior.
- `apps/api/tests/test_report_api.py`
  - Assert `report.next_day_predictions` exists in API response and snapshot.
  - Assert `algorithm_versions.next_day_prediction == "next_day_prediction_v0_5"`.
- `apps/api/tests/test_review_sources.py`
  - Add or preserve cases for parsed front-row stocks and height notes from 东方财富/同花顺 samples.

## Validation Commands

Run from repo root:

```bash
cd apps/api && .venv/bin/python -m ruff check app tests
cd apps/api && .venv/bin/python -m pytest -q
```

Expected final result:

- Ruff passes.
- Pytest passes.
- Snapshot JSON includes `next_day_predictions`.
- HTML report includes `次日强势概率与观察条件`.
- No generated production path contains fake prediction sectors or fake stock names.

## Implementation Order

1. Add prediction schema types and algorithm version field.
2. Add failing prediction service tests.
3. Implement deterministic prediction service.
4. Wire predictions into `ReportGenerator`.
5. Render prediction cards in mobile HTML template.
6. Align structured review builder with prediction output.
7. Update API/snapshot/HTML tests.
8. Run ruff and pytest.

## Acceptance Criteria

The feature is complete when:

- Main report generation includes next-day predictions as part of `ReportDTO`.
- TickFlow remains the preferred normalized market/quote layer, with SDK/intraday support reserved behind provider interfaces rather than embedded inside scoring logic.
- The HTML report prominently displays next-day probability and observation conditions.
- Predictions are based on curated review evidence plus market/news strength, not fabricated text.
- Missing evidence produces clear evidence-insufficient output.
- Tests cover scoring, no-data behavior, report persistence, and HTML rendering.
- Existing source boundary remains intact: 同花顺/东方财富 for review, TickFlow for market/quotes, Anspire for news.
