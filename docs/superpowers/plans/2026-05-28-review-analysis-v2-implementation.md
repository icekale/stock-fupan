# Review Analysis V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade generated stock review reports from a strong-sector list into a trading-review structure matching the user-provided WeChat article: market phase, yesterday prediction verification, sector deep dives, capital rotation, sustainability ranking, and next-session strategy.

**Architecture:** Keep current data providers and the pre-rollback stable baseline. Add v2 structured-review fields and derive them from existing `ReportDTO`, historical reports, TickFlow front-row stocks, Anspire/news summaries, and 同花顺/东方财富 review-source text. Render the new v2 fields in the existing mobile HTML template without reintroducing the failed 同花顺 concept-index replacement.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Jinja2, pytest, Playwright PNG export.

---

## File Structure

- Modify `apps/api/app/schemas/structured_review.py`
  - Add backward-compatible v2 DTO models: `MarketPhaseReview`, `PredictionVerificationItem`, `SectorDeepDive`, `CapitalRotationReviewV2`, `NextSessionStrategy`.
  - Add optional/list fields to `StructuredReviewDTO` so existing JSON remains valid.

- Modify `apps/api/app/services/structured_review_builder.py`
  - Derive the v2 fields from `ReportDTO` without changing provider behavior.
  - Keep old fields populated for current template compatibility while adding richer v2 fields.

- Modify `apps/api/app/renderers/templates/mobile_report.html.j2`
  - Reorder the visible report to match the reference HTML sequence.
  - Render v2 modules when present and fall back to old fields when absent.

- Modify tests:
  - `apps/api/tests/test_structured_review.py`
  - `apps/api/tests/test_report_api.py`

---

### Task 1: Add V2 Structured Review Schema

**Files:**
- Modify: `apps/api/app/schemas/structured_review.py`
- Test: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Write the failing serialization test**

Add this test to `apps/api/tests/test_structured_review.py` near `test_structured_review_serializes_core_modules`:

```python
def test_structured_review_serializes_v2_review_modules() -> None:
    review = StructuredReviewDTO(
        topic="V型反转 · 科技扩散",
        market_phase=MarketPhaseReview(
            phase="mainline_expansion",
            headline="科技主线从集中走向扩散",
            key_signal="电子方向资金从早盘净流出转为收盘净流入。",
            yesterday_today_compare=["昨日封测单点承压", "今日CPO/MLCC/散热多点修复"],
        ),
        prediction_review=PredictionReview(
            previous_prediction="昨日判断科技惯性下探后小幅修复。",
            actual_result="创业板午后强修复，CPO前排创出新高。",
            correct_items=["惯性下探方向正确"],
            missed_items=["低估午后修复强度"],
            bias_reasons=["被前一日恐慌情绪影响"],
            revision="后续重点看科技内部分支轮动，而非全面退潮。",
        ),
        prediction_verifications=[
            PredictionVerificationItem(
                claim="科技惯性下探后小幅修复",
                verdict="部分正确",
                actual_result="下探后强修复，修复力度超预期。",
                evidence=["创业板+1.96%", "CPO前排20cm涨停"],
                bias_reason="低估主线资金回流速度。",
            )
        ],
        tomorrow_judgement=TomorrowJudgement(
            most_likely_to_continue="CPO/光模块",
            most_likely_to_diverge="白酒/消费",
            core_view="明日看科技前排分歧承接。",
        ),
        market_overview=MarketOverviewTable(capital_flow_summary="缩量修复，资金仍偏谨慎。"),
        after_hours_news=AfterHoursNewsSummary(),
        sector_reviews=[],
        sector_deep_dives=[
            SectorDeepDive(
                sector="CPO/光模块",
                stage="new_leader",
                rating="high",
                catalysts=["海外光互连指引上调"],
                core_stocks=["联特科技", "中际旭创", "新易盛"],
                capital_evidence=["机构净买入约39亿"],
                team_structure="20cm领涨+中军创新高",
                conclusion="接棒成为科技新核心。",
                watch_signals=["前排分歧后继续承接"],
                avoid_signals=["一致加速追高"],
            )
        ],
        sustainability_ranking=[],
        capital_rotation=CapitalRotationPath(
            key_finding="科技资金从封测/存储扩散到CPO/MLCC。",
        ),
        capital_rotation_v2=CapitalRotationReviewV2(
            path=["半导体封测流出", "CPO回流", "MLCC扩散"],
            rotation_type="主线内部扩散",
            key_finding="不是科技全面退潮，而是AI算力链内部重分配。",
            next_watch=["CPO前排承接", "MLCC梯队完整度"],
        ),
        historical_theme_reviews=[],
        next_day_opportunity=NextDayOpportunityPlan(),
        next_session_strategy=NextSessionStrategy(
            focus=["CPO前排分歧承接"],
            observe=["MLCC是否从补涨转持续"],
            avoid=["白酒一日游后排"],
            trigger_conditions=["指数不放量下杀"],
            invalidation_conditions=["科技前排集体低开低走"],
        ),
        practical_conclusion=PracticalConclusion(headline="明日看科技前排承接"),
        index_mid_term_outlook=IndexMidTermOutlook(current_position="结构性修复"),
        action_discipline=ActionDiscipline(final_view="不追一致加速。"),
    )

    payload = review.model_dump(mode="json")

    assert payload["market_phase"]["phase"] == "mainline_expansion"
    assert payload["prediction_verifications"][0]["verdict"] == "部分正确"
    assert payload["sector_deep_dives"][0]["stage"] == "new_leader"
    assert payload["capital_rotation_v2"]["rotation_type"] == "主线内部扩散"
    assert payload["next_session_strategy"]["avoid"] == ["白酒一日游后排"]
```

Also update the import list in the same test file to import the new classes.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py::test_structured_review_serializes_v2_review_modules -v
```

Expected: FAIL because the new classes are not defined.

- [ ] **Step 3: Add the schema models**

Add these models to `apps/api/app/schemas/structured_review.py` after `SustainabilityRating`:

```python
MarketPhase = Literal[
    "panic_decline",
    "repair",
    "structural_rebound",
    "mainline_expansion",
    "internal_rotation",
    "defensive_rotation",
    "mixed_divergence",
]
SectorStage = Literal[
    "leader",
    "new_leader",
    "branch_expansion",
    "independent_theme",
    "repair_only",
    "weakening",
    "one_day",
    "avoid",
]
ReviewVerdict = Literal["正确", "部分正确", "错误", "证据不足"]


class MarketPhaseReview(BaseModel):
    phase: MarketPhase
    headline: str
    key_signal: str
    yesterday_today_compare: list[str] = Field(default_factory=list)


class PredictionVerificationItem(BaseModel):
    claim: str
    verdict: ReviewVerdict
    actual_result: str
    evidence: list[str] = Field(default_factory=list)
    bias_reason: str = ""


class SectorDeepDive(BaseModel):
    sector: str
    stage: SectorStage
    rating: SustainabilityRating
    catalysts: list[str] = Field(default_factory=list)
    core_stocks: list[str] = Field(default_factory=list)
    capital_evidence: list[str] = Field(default_factory=list)
    team_structure: str = ""
    conclusion: str
    watch_signals: list[str] = Field(default_factory=list)
    avoid_signals: list[str] = Field(default_factory=list)


class CapitalRotationReviewV2(BaseModel):
    path: list[str] = Field(default_factory=list)
    rotation_type: str
    key_finding: str
    next_watch: list[str] = Field(default_factory=list)


class NextSessionStrategy(BaseModel):
    focus: list[str] = Field(default_factory=list)
    observe: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
```

Add these fields to `StructuredReviewDTO`:

```python
    market_phase: MarketPhaseReview | None = None
    prediction_verifications: list[PredictionVerificationItem] = Field(default_factory=list)
    sector_deep_dives: list[SectorDeepDive] = Field(default_factory=list)
    capital_rotation_v2: CapitalRotationReviewV2 | None = None
    next_session_strategy: NextSessionStrategy | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py::test_structured_review_serializes_v2_review_modules -v
```

Expected: PASS.

- [ ] **Step 5: Run schema-adjacent tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py::test_structured_review_serializes_core_modules tests/test_structured_review.py::test_build_structured_review_derives_core_modules_from_report -v
```

Expected: PASS.

---

### Task 2: Derive Market Phase and Prediction Verification

**Files:**
- Modify: `apps/api/app/services/structured_review_builder.py`
- Test: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Write failing tests for phase and verification**

Add these tests to `apps/api/tests/test_structured_review.py`:

```python
def test_build_structured_review_adds_market_phase_with_specific_signal() -> None:
    report = _fake_report()
    report.breadth = MarketBreadth(up_count=3200, down_count=1800, limit_up_count=86, limit_down_count=8)
    report.market_state_tags = ["放量", "普涨"]
    report.sectors[0] = report.sectors[0].model_copy(update={"name": "机器人", "score": 82, "pct_change": 5.88})
    report.sectors[1] = report.sectors[1].model_copy(update={"name": "PCB", "score": 76, "pct_change": 3.60})

    review = build_structured_review(report)

    assert review.market_phase is not None
    assert review.market_phase.phase in {"repair", "structural_rebound", "mainline_expansion"}
    assert "机器人" in review.market_phase.headline
    assert "涨停86" in review.market_phase.key_signal
    assert review.market_phase.yesterday_today_compare


def test_build_structured_review_adds_itemized_prediction_verification() -> None:
    report = _fake_report()
    report.previous_strong_themes = [
        HistoricalThemeReview(
            theme="先进封装",
            previous_status="昨日强势前排",
            current_status="今日跌出前排",
            judgement="进入分歧",
            evidence=["长电科技走弱", "存储芯片资金流出"],
        )
    ]

    review = build_structured_review(report)

    assert review.prediction_verifications
    first = review.prediction_verifications[0]
    assert first.claim
    assert first.verdict in {"正确", "部分正确", "错误", "证据不足"}
    assert first.actual_result
    assert first.evidence
```

Update imports if needed.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py::test_build_structured_review_adds_market_phase_with_specific_signal tests/test_structured_review.py::test_build_structured_review_adds_itemized_prediction_verification -v
```

Expected: FAIL because builder does not populate v2 fields.

- [ ] **Step 3: Add helper imports and fill fields in builder**

Update imports in `apps/api/app/services/structured_review_builder.py` to include:

```python
    CapitalRotationReviewV2,
    MarketPhaseReview,
    NextSessionStrategy,
    PredictionVerificationItem,
    SectorDeepDive,
```

In `build_structured_review`, add these keyword arguments to the returned `StructuredReviewDTO`:

```python
        market_phase=_build_market_phase(report, leader, runner_up),
        prediction_verifications=_build_prediction_verifications(report, leader, runner_up, next_session),
```

- [ ] **Step 4: Add minimal helper functions**

Add these helper functions near the existing private helpers in `structured_review_builder.py`:

```python
def _build_market_phase(
    report: ReportDTO,
    leader: SectorCandidate | None,
    runner_up: SectorCandidate | None,
) -> MarketPhaseReview:
    up_count = report.breadth.up_count
    down_count = report.breadth.down_count
    limit_up = report.breadth.limit_up_count
    limit_down = report.breadth.limit_down_count
    leader_name = leader.name if leader else "暂无主线"
    runner_up_name = runner_up.name if runner_up else "暂无轮动方向"
    market_tags = "、".join(report.market_state_tags) or "结构不明"

    if limit_down >= 20 or down_count > up_count * 1.4:
        phase = "panic_decline"
        headline = f"{leader_name}承压，市场处于退潮/风险释放阶段"
    elif leader and runner_up and leader.score >= 75 and runner_up.score >= 65:
        phase = "mainline_expansion"
        headline = f"{leader_name}领涨，{runner_up_name}扩散，主线从集中走向扩散"
    elif up_count > down_count and limit_up >= 60:
        phase = "structural_rebound"
        headline = f"{leader_name}带动结构性修复，短线情绪回暖"
    elif up_count > down_count:
        phase = "repair"
        headline = f"{leader_name}修复，但资金仍需继续确认"
    else:
        phase = "mixed_divergence"
        headline = f"{leader_name}相对靠前，但市场仍是分化震荡"

    compare = _market_compare_points(report, leader, runner_up)
    return MarketPhaseReview(
        phase=phase,
        headline=headline,
        key_signal=f"涨停{limit_up}家、跌停{limit_down}家，上涨{up_count}只、下跌{down_count}只，市场标签：{market_tags}。",
        yesterday_today_compare=compare,
    )


def _market_compare_points(
    report: ReportDTO,
    leader: SectorCandidate | None,
    runner_up: SectorCandidate | None,
) -> list[str]:
    points: list[str] = []
    if report.previous_strong_themes:
        previous_names = "、".join(item.theme for item in report.previous_strong_themes[:3])
        points.append(f"昨日/历史强势方向：{previous_names}")
    if leader:
        points.append(f"今日最强方向：{leader.name}，强度{leader.score:.1f}，涨幅{leader.pct_change:+.2f}%")
    if runner_up:
        points.append(f"轮动扩散方向：{runner_up.name}，强度{runner_up.score:.1f}")
    if not points:
        points.append("缺少历史方向对比，仅保留今日结构观察。")
    return points


def _build_prediction_verifications(
    report: ReportDTO,
    leader: SectorCandidate | None,
    runner_up: SectorCandidate | None,
    next_session: str,
) -> list[PredictionVerificationItem]:
    items: list[PredictionVerificationItem] = []
    if report.previous_strong_themes:
        current_names = {sector.name for sector in report.sectors}
        for theme in report.previous_strong_themes[:4]:
            matched = theme.theme in current_names or any(theme.theme in name or name in theme.theme for name in current_names)
            verdict = "正确" if matched else "部分正确" if theme.current_stock_checks else "错误"
            evidence = [*theme.evidence[:2], *theme.current_stock_checks[:2]]
            if not evidence:
                evidence = [theme.current_status]
            items.append(
                PredictionVerificationItem(
                    claim=f"昨日/历史关注{theme.theme}延续性",
                    verdict=verdict,
                    actual_result=theme.current_status,
                    evidence=evidence,
                    bias_reason="历史强势方向需要用今日前排和资金重新确认，不能机械延续。" if not matched else "方向延续得到今日盘面确认。",
                )
            )
    if leader is not None:
        evidence = [f"{leader.name}今日排名第{leader.rank}，强度{leader.score:.1f}，涨幅{leader.pct_change:+.2f}%"]
        items.insert(
            0,
            PredictionVerificationItem(
                claim=f"{next_session}重点观察主线是否延续",
                verdict="正确" if leader.score >= 70 else "部分正确",
                actual_result=f"{leader.name}成为今日最强方向。",
                evidence=evidence,
                bias_reason="需要继续用前排承接和资金强度验证持续性。",
            ),
        )
    if not items:
        items.append(
            PredictionVerificationItem(
                claim="昨日预判验证",
                verdict="证据不足",
                actual_result="缺少上一日报告或历史预判快照。",
                evidence=["当前仅能基于今日盘面生成复盘。"],
                bias_reason="未读取到可验证的昨日判断，不做机械归因。",
            )
        )
    return items[:5]
```

- [ ] **Step 5: Run tests to verify pass**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py::test_build_structured_review_adds_market_phase_with_specific_signal tests/test_structured_review.py::test_build_structured_review_adds_itemized_prediction_verification -v
```

Expected: PASS.

---

### Task 3: Derive Sector Deep Dives, Capital Rotation V2, and Strategy

**Files:**
- Modify: `apps/api/app/services/structured_review_builder.py`
- Test: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Write failing tests for deep dives and strategy**

Add these tests to `apps/api/tests/test_structured_review.py`:

```python
def test_build_structured_review_adds_sector_deep_dives_with_real_stocks() -> None:
    report = _fake_report()
    report.sectors[0] = report.sectors[0].model_copy(
        update={
            "name": "CPO/光模块",
            "score": 86,
            "pct_change": 5.4,
            "top_stocks": [
                StockCandidate(code="300394.SZ", name="联特科技", pct_change=20.0, turnover_cny=2_100_000_000, turnover_rate=18.2, tags=["TickFlow前排"]),
                StockCandidate(code="300308.SZ", name="中际旭创", pct_change=7.79, turnover_cny=9_500_000_000, turnover_rate=6.5, tags=["TickFlow前排"]),
            ],
            "news_summaries": ["海外光互连需求上调，带动CPO方向走强。"],
            "review_notes": ["同花顺复盘确认CPO为科技扩散方向。"],
        }
    )

    review = build_structured_review(report)

    assert review.sector_deep_dives
    cpo = review.sector_deep_dives[0]
    assert cpo.sector == "CPO/光模块"
    assert cpo.stage in {"leader", "new_leader", "branch_expansion"}
    assert "联特科技" in cpo.core_stocks
    assert cpo.capital_evidence
    assert cpo.conclusion
    assert cpo.watch_signals


def test_build_structured_review_adds_v2_capital_rotation_and_strategy() -> None:
    report = _fake_report()
    report.sectors[0] = report.sectors[0].model_copy(update={"name": "CPO/光模块", "score": 86})
    report.sectors[1] = report.sectors[1].model_copy(update={"name": "MLCC/被动元件", "score": 74})
    report.previous_strong_themes = [
        HistoricalThemeReview(
            theme="半导体封测/存储",
            previous_status="昨日强势",
            current_status="今日跌出前排",
            judgement="进入分歧",
            evidence=["长电科技走弱"],
        )
    ]

    review = build_structured_review(report)

    assert review.capital_rotation_v2 is not None
    assert review.capital_rotation_v2.path[0].startswith("半导体封测/存储")
    assert "CPO/光模块" in " → ".join(review.capital_rotation_v2.path)
    assert review.next_session_strategy is not None
    assert any("CPO/光模块" in item for item in review.next_session_strategy.focus)
    assert review.next_session_strategy.avoid
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py::test_build_structured_review_adds_sector_deep_dives_with_real_stocks tests/test_structured_review.py::test_build_structured_review_adds_v2_capital_rotation_and_strategy -v
```

Expected: FAIL because the new fields are not populated.

- [ ] **Step 3: Wire new builders into `build_structured_review`**

In `build_structured_review`, add these keyword args to `StructuredReviewDTO`:

```python
        sector_deep_dives=_build_sector_deep_dives(report),
        capital_rotation_v2=_build_capital_rotation_v2(report, leader, runner_up),
        next_session_strategy=_build_next_session_strategy(report, leader, runner_up, next_session),
```

- [ ] **Step 4: Add helper functions**

Add these helpers in `structured_review_builder.py`:

```python
def _build_sector_deep_dives(report: ReportDTO) -> list[SectorDeepDive]:
    return [_build_sector_deep_dive(sector, index) for index, sector in enumerate(report.sectors[:6])]


def _build_sector_deep_dive(sector: SectorCandidate, index: int) -> SectorDeepDive:
    stock_names = [stock.name for stock in sector.top_stocks if stock.name][:5]
    catalysts = _distinct_compact([*sector.news_summaries[:3], *sector.review_notes[:3]])
    capital_notes = _sector_capital_notes(sector)
    stage = _sector_stage(sector, index)
    rating = _rating_for_sector(sector)
    team_structure = _team_structure_text(sector)
    if not stock_names:
        stock_names = ["证据不足：缺少明确前排标的"]
    if not catalysts:
        catalysts = ["证据不足：未读取到明确催化，需等待复盘源或新闻确认。"]
    return SectorDeepDive(
        sector=sector.name,
        stage=stage,
        rating=rating,
        catalysts=catalysts,
        core_stocks=stock_names,
        capital_evidence=capital_notes,
        team_structure=team_structure,
        conclusion=_sector_deep_conclusion(sector, stage, rating),
        watch_signals=_sector_watch_signals(sector),
        avoid_signals=_sector_avoid_signals(sector),
    )


def _distinct_compact(values: list[str], max_items: int = 4) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = " ".join(str(value).split())
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
        if len(output) >= max_items:
            break
    return output


def _sector_capital_notes(sector: SectorCandidate) -> list[str]:
    notes: list[str] = []
    if sector.capital_evidence is not None:
        notes.append(f"{sector.capital_evidence.summary}，资金强度{sector.capital_evidence.strength}")
    for stock in sector.top_stocks[:3]:
        parts = [stock.name]
        if stock.turnover_cny:
            parts.append(f"成交{stock.turnover_cny / 100_000_000:.2f}亿")
        if stock.turnover_rate is not None:
            parts.append(f"换手{stock.turnover_rate:.2f}%")
        if len(parts) > 1:
            notes.append("、".join(parts))
    return notes or ["证据不足：缺少成交额/换手率数据，资金强度不做夸大判断。"]


def _sector_stage(sector: SectorCandidate, index: int) -> str:
    if sector.score >= 80 and index == 0:
        return "leader"
    if sector.score >= 75:
        return "new_leader"
    if sector.score >= 65 and len(sector.top_stocks) >= 2:
        return "branch_expansion"
    if sector.score >= 60:
        return "repair_only"
    if sector.pct_change <= 0:
        return "weakening"
    return "repair_only"


def _team_structure_text(sector: SectorCandidate) -> str:
    limit_like = [stock for stock in sector.top_stocks if stock.pct_change >= 9.5]
    twenty_cm = [stock for stock in sector.top_stocks if stock.pct_change >= 19]
    if twenty_cm and len(sector.top_stocks) >= 2:
        return f"{len(twenty_cm)}只高弹性前排 + {len(sector.top_stocks)}只跟随，具备扩散队形。"
    if limit_like:
        return f"{len(limit_like)}只涨停/接近涨停前排，观察梯队是否补强。"
    if sector.top_stocks:
        return f"{len(sector.top_stocks)}只前排跟踪标的，尚未形成完整涨停梯队。"
    return "缺少明确前排，不能判断梯队完整度。"


def _sector_deep_conclusion(sector: SectorCandidate, stage: str, rating: str) -> str:
    stage_text = {
        "leader": "当前主线核心",
        "new_leader": "可能接棒的新核心",
        "branch_expansion": "主线扩散分支",
        "independent_theme": "独立逻辑方向",
        "repair_only": "修复观察方向",
        "weakening": "走弱/失血方向",
        "one_day": "一日游风险方向",
        "avoid": "规避方向",
    }.get(stage, "观察方向")
    return f"{sector.name}属于{stage_text}，持续性评级{rating}；后续只看前排承接和资金是否继续确认。"


def _sector_watch_signals(sector: SectorCandidate) -> list[str]:
    stocks = [stock.name for stock in sector.top_stocks if stock.name][:3]
    if stocks:
        return [f"观察{'、'.join(stocks)}是否继续强于板块平均。", "观察分歧后是否有资金回流。"]
    return [f"需要先确认{sector.name}是否出现明确前排股。"]


def _sector_avoid_signals(sector: SectorCandidate) -> list[str]:
    return ["一致加速后不追高。", "后排无量补涨不作为主线依据。"]


def _build_capital_rotation_v2(
    report: ReportDTO,
    leader: SectorCandidate | None,
    runner_up: SectorCandidate | None,
) -> CapitalRotationReviewV2:
    path: list[str] = []
    for theme in report.previous_strong_themes[:2]:
        status = "延续" if theme.judgement == "延续确认" else "分歧/流出"
        path.append(f"{theme.theme}{status}")
    if leader:
        path.append(f"{leader.name}承接")
    if runner_up:
        path.append(f"{runner_up.name}扩散")
    if not path:
        path = ["缺少历史路径", "今日等待主线确认"]
    rotation_type = "主线内部扩散" if leader and runner_up and leader.score >= 75 and runner_up.score >= 65 else "结构性轮动"
    return CapitalRotationReviewV2(
        path=path,
        rotation_type=rotation_type,
        key_finding=_capital_rotation_finding(leader, runner_up, leader.name if leader else "暂无主线", runner_up.name if runner_up else "暂无轮动", _next_session(report)),
        next_watch=[f"观察{leader.name}前排承接" if leader else "等待主线确认", f"观察{runner_up.name}能否补强梯队" if runner_up else "观察轮动方向是否出现"],
    )


def _build_next_session_strategy(
    report: ReportDTO,
    leader: SectorCandidate | None,
    runner_up: SectorCandidate | None,
    next_session: str,
) -> NextSessionStrategy:
    focus = _strategy_focus_items(leader)
    observe = _strategy_observe_items(runner_up)
    avoid = _strategy_avoid_items(report)
    return NextSessionStrategy(
        focus=focus,
        observe=observe,
        avoid=avoid,
        trigger_conditions=[f"{next_session}指数不出现放量下杀", "前排股分歧后仍有主动承接", "成交额维持活跃区间"],
        invalidation_conditions=["主线前排集体低开低走", "后排冲高回落且无资金回流", "跌停/大面数量明显增加"],
    )


def _strategy_focus_items(leader: SectorCandidate | None) -> list[str]:
    if leader is None:
        return ["缺少明确主线，先观察不预设机会。"]
    stocks = [stock.name for stock in leader.top_stocks if stock.name][:3]
    suffix = f"，重点看{'、'.join(stocks)}" if stocks else "，但缺少明确前排标的"
    return [f"{leader.name}{suffix}的分歧承接。"]


def _strategy_observe_items(runner_up: SectorCandidate | None) -> list[str]:
    if runner_up is None:
        return ["观察是否出现新的轮动方向。"]
    return [f"{runner_up.name}能否从轮动补涨转为持续方向。"]


def _strategy_avoid_items(report: ReportDTO) -> list[str]:
    weak = [sector.name for sector in report.sectors if sector.score < 55 or sector.pct_change <= 0][:2]
    items = [f"{name}证据不足或走弱，不做主线预设。" for name in weak]
    items.append("一日游后排和无量补涨不追。")
    return items
```

- [ ] **Step 5: Run tests to verify pass**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py::test_build_structured_review_adds_sector_deep_dives_with_real_stocks tests/test_structured_review.py::test_build_structured_review_adds_v2_capital_rotation_and_strategy -v
```

Expected: PASS.

- [ ] **Step 6: Run full structured review tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py -v
```

Expected: PASS.

---

### Task 4: Render Reference-Style HTML Order

**Files:**
- Modify: `apps/api/app/renderers/templates/mobile_report.html.j2`
- Test: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Write failing HTML order/content test**

Add this test to `apps/api/tests/test_report_api.py` near the mobile renderer tests:

```python
def test_mobile_report_renderer_uses_review_analysis_v2_article_order(tmp_path: Path) -> None:
    generator = _fake_generator(tmp_path)
    result = generator.generate_close_report("2026-05-26")
    html = render_mobile_report_html(result.report)

    expected_order = [
        "核心结论",
        "指数与市场情绪",
        "昨日预判验证",
        "板块详细分析",
        "资金轮动路径",
        "板块持续性排序",
        "明日操作思路",
    ]
    positions = [html.index(text) for text in expected_order]

    assert positions == sorted(positions)
    assert "市场阶段" in html
    assert "逐条验证" in html
    assert "重点关注" in html
    assert "谨慎观察" in html
    assert "规避方向" in html
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd apps/api && uv run pytest tests/test_report_api.py::test_mobile_report_renderer_uses_review_analysis_v2_article_order -v
```

Expected: FAIL because the template does not yet expose the v2 order/labels.

- [ ] **Step 3: Replace the overview and prediction blocks**

In `mobile_report.html.j2`, locate the block that starts with:

```jinja2
    <span class="section-num">TWO</span>
    <h2 class="section-title">盘面总览</h2>
```

and ends immediately before:

```jinja2
    <span class="section-num">THREE</span>
    <h2 class="section-title">各板块详细分析</h2>
```

Replace that full range with this markup:

```jinja2
    <span class="section-num">ONE</span>
    <h2 class="section-title">核心结论</h2>
    {% if structured.market_phase %}
      <div class="key-insight">
        <div class="ki-title">市场阶段 · {{ structured.market_phase.phase }}</div>
        <p>{{ structured.market_phase.headline }}</p>
        <p style="margin-top:10px;"><strong>最关键的信号：</strong>{{ structured.market_phase.key_signal }}</p>
        {% if structured.market_phase.yesterday_today_compare %}
          <ul class="point-list" style="margin-top:10px;">
            {% for item in structured.market_phase.yesterday_today_compare %}
              <li>{{ item }}</li>
            {% endfor %}
          </ul>
        {% endif %}
      </div>
    {% else %}
      <p>{{ report.narrative.conclusion }}</p>
    {% endif %}

    <hr class="divider">

    <span class="section-num">TWO</span>
    <h2 class="section-title">指数与市场情绪</h2>

    <div class="metric-grid">
      {% for row in structured.market_overview.emotion_rows %}
        <div class="metric-card">
          <div class="metric-label">{{ row.label }}</div>
          <div class="metric-value">{{ row.value }}</div>
        </div>
      {% endfor %}
    </div>

    <h3 class="section-subtitle">指数数据</h3>
    <div class="table-wrap">
      <table>
        <thead><tr><th>指数</th><th>收盘</th><th>涨跌幅</th></tr></thead>
        <tbody>
          {% for row in structured.market_overview.index_rows %}
            <tr>
              <td>{{ row.name }}</td>
              <td>{{ row.close }}</td>
              <td><span class="{{ 'bearish' if row.change.startswith('-') else 'bullish' }}">{{ row.change }}</span></td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <h3 class="section-subtitle">市场情绪</h3>
    <div class="table-wrap">
      <table>
        <thead><tr><th>指标</th><th>数值</th></tr></thead>
        <tbody>
          {% for row in structured.market_overview.emotion_rows %}
            <tr><td>{{ row.label }}</td><td>{{ row.value }}</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <div class="key-insight">
      <div class="ki-title">情绪阶段判断</div>
      <p>{{ structured.market_overview.capital_flow_summary }}</p>
      {% if structured.market_overview.structure_features %}
        <p style="margin-top:10px;">
          {% for feature in structured.market_overview.structure_features %}
            <span class="tag tag-navy">{{ feature }}</span>
          {% endfor %}
        </p>
      {% endif %}
      {% if structured.market_overview.structure_notes %}
        <ul class="point-list" style="margin-top:10px;">
          {% for item in structured.market_overview.structure_notes %}
            <li>{{ item }}</li>
          {% endfor %}
        </ul>
      {% endif %}
    </div>

    <hr class="divider">

    <span class="section-num">THREE</span>
    <h2 class="section-title">昨日预判验证</h2>
    <p class="muted">逐条验证昨日判断，避免被单日情绪带偏。</p>
    <div class="table-wrap">
      <table aria-label="逐条验证">
        <thead><tr><th>昨日判断</th><th>结论</th><th>实际结果</th><th>证据 / 偏差</th></tr></thead>
        <tbody>
          {% for item in structured.prediction_verifications %}
            <tr>
              <td>{{ item.claim }}</td>
              <td>{{ item.verdict }}</td>
              <td>{{ item.actual_result }}</td>
              <td style="text-align:left;">
                {% for evidence in item.evidence[:2] %}<div>{{ evidence }}</div>{% endfor %}
                {% if item.bias_reason %}<div class="muted">{{ item.bias_reason }}</div>{% endif %}
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
```

Delete the old `盘面总览` heading and old non-table prediction-review block in this replacement range. The rendered HTML should contain the text `指数与市场情绪` and `昨日预判验证` exactly once.

- [ ] **Step 4: Replace sector, rotation, ranking, and strategy blocks**

In `mobile_report.html.j2`, replace the block that starts with:

```jinja2
    <span class="section-num">THREE</span>
    <h2 class="section-title">各板块详细分析</h2>
```

and ends immediately before:

```jinja2
    {% set watch = report.watchlist_observation %}
```

with this markup:

```jinja2
    <span class="section-num">FOUR</span>
    <h2 class="section-title">板块详细分析</h2>
    {% for sector in structured.sector_deep_dives %}
      <article class="sector-block">
        <h3 class="section-subtitle">{{ loop.index }}. {{ sector.sector }} <span class="tag tag-gold">{{ sector.rating }}</span></h3>
        <div class="sector-meta">
          <span><strong>阶段：</strong>{{ sector.stage }}</span>
          <span><strong>梯队：</strong>{{ sector.team_structure }}</span>
        </div>
        <div class="sector-grid">
          <div class="insight-card">
            <div class="insight-label">催化与逻辑</div>
            <ul class="compact-list">{% for item in sector.catalysts %}<li>{{ item }}</li>{% endfor %}</ul>
          </div>
          <div class="insight-card">
            <div class="insight-label">核心标的</div>
            <ul class="compact-list">{% for item in sector.core_stocks %}<li>{{ item }}</li>{% endfor %}</ul>
          </div>
          <div class="insight-card">
            <div class="insight-label">资金证据</div>
            <ul class="compact-list">{% for item in sector.capital_evidence %}<li>{{ item }}</li>{% endfor %}</ul>
          </div>
          <div class="insight-card">
            <div class="insight-label">结论与条件</div>
            <p>{{ sector.conclusion }}</p>
            <p><strong>观察：</strong>{{ sector.watch_signals|join("；") }}</p>
            <p><strong>规避：</strong>{{ sector.avoid_signals|join("；") }}</p>
          </div>
        </div>
      </article>
    {% endfor %}

    <hr class="divider">

    <span class="section-num">FIVE</span>
    <h2 class="section-title">资金轮动路径</h2>
    {% if structured.capital_rotation_v2 %}
      <div class="path-flow">
        {% for item in structured.capital_rotation_v2.path %}
          <span class="path-node">{{ item }}</span>{% if not loop.last %}<span class="path-arrow">→</span>{% endif %}
        {% endfor %}
      </div>
      <div class="key-insight">
        <div class="ki-title">{{ structured.capital_rotation_v2.rotation_type }}</div>
        <p>{{ structured.capital_rotation_v2.key_finding }}</p>
      </div>
      <ul class="point-list">
        {% for item in structured.capital_rotation_v2.next_watch %}
          <li>{{ item }}</li>
        {% endfor %}
      </ul>
    {% endif %}

    <hr class="divider">

    <span class="section-num">SIX</span>
    <h2 class="section-title">板块持续性排序</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>排序</th><th>方向</th><th>评级</th><th>核心理由</th></tr></thead>
        <tbody>
          {% for item in structured.sustainability_ranking %}
            <tr>
              <td>{{ item.rank }}</td>
              <td>{{ item.sector }}</td>
              <td>
                {% if item.rating == "high" %}
                  <span class="tag tag-bull">高</span>
                {% elif item.rating == "medium" %}
                  <span class="tag tag-navy">中</span>
                {% else %}
                  <span class="tag tag-bear">低</span>
                {% endif %}
              </td>
              <td style="text-align:left;">{{ item.reason }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <hr class="divider">

    <span class="section-num">SEVEN</span>
    <h2 class="section-title">明日操作思路</h2>
    <div class="sector-grid">
      <div class="insight-card"><div class="insight-label">重点关注</div><ul>{% for item in structured.next_session_strategy.focus %}<li>{{ item }}</li>{% endfor %}</ul></div>
      <div class="insight-card"><div class="insight-label">谨慎观察</div><ul>{% for item in structured.next_session_strategy.observe %}<li>{{ item }}</li>{% endfor %}</ul></div>
      <div class="insight-card"><div class="insight-label">规避方向</div><ul>{% for item in structured.next_session_strategy.avoid %}<li>{{ item }}</li>{% endfor %}</ul></div>
    </div>
    <div class="card">
      <h4 class="section-sub-subtitle">触发条件</h4>
      <ul class="point-list">{% for item in structured.next_session_strategy.trigger_conditions %}<li>{{ item }}</li>{% endfor %}</ul>
      <h4 class="section-sub-subtitle">失效条件</h4>
      <ul class="point-list">{% for item in structured.next_session_strategy.invalidation_conditions %}<li class="bear">{{ item }}</li>{% endfor %}</ul>
    </div>
```

Move the existing after-hours news block (`{{ news_section_title }}` plus 美股映射/国内催化/风险提示) so it appears after `明日操作思路` and before the watchlist block. Do not add large visual redesigns in this task.

- [ ] **Step 5: Run HTML order test**

Run:

```bash
cd apps/api && uv run pytest tests/test_report_api.py::test_mobile_report_renderer_uses_review_analysis_v2_article_order -v
```

Expected: PASS.

- [ ] **Step 6: Run renderer tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_report_api.py -k "mobile_report_renderer or mobile_report_html" -v
```

Expected: PASS. If old tests assert old order, update only assertions that conflict with the approved v2 order.

---

### Task 5: Persist and Validate V2 Report Outputs

**Files:**
- Modify: `apps/api/tests/test_report_api.py`
- Modify: `apps/api/app/services/report_generator.py`

- [ ] **Step 1: Write failing snapshot persistence test**

Add this test near `test_report_generator_writes_structured_review_to_report_and_snapshot`:

```python
def test_report_generator_persists_review_analysis_v2_fields(tmp_path: Path) -> None:
    generator = _fake_generator(tmp_path)

    result = generator.generate_close_report("2026-05-26")

    assert result.report.structured_review is not None
    assert result.report.structured_review.market_phase is not None
    assert result.report.structured_review.prediction_verifications
    assert result.report.structured_review.sector_deep_dives
    snapshot = _read_json(result.assets.snapshot)
    structured = snapshot["report"]["structured_review"]
    assert structured["market_phase"]["headline"]
    assert structured["prediction_verifications"][0]["claim"]
    assert structured["sector_deep_dives"][0]["core_stocks"]
```

- [ ] **Step 2: Run test**

Run:

```bash
cd apps/api && uv run pytest tests/test_report_api.py::test_report_generator_persists_review_analysis_v2_fields -v
```

Expected: PASS because `ReportDTO.model_dump(mode="json")` includes `structured_review` fields automatically. If it fails, patch only the serialization call that omits `structured_review`.

- [ ] **Step 3: Verify no production fake content is introduced**

Add this assertion to the same test:

```python
    html = result.assets.report_html.read_text(encoding="utf-8")
    assert "伪造" not in html
    assert "TODO" not in html
```

Run the same test again. Expected: PASS.

---

### Task 6: Final Verification and Local Preview

**Files:**
- All touched files

- [ ] **Step 1: Run lint**

Run:

```bash
cd apps/api && uv run ruff check app tests
```

Expected: `All checks passed!`

- [ ] **Step 2: Run targeted tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py tests/test_report_api.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Generate one local report preview**

Run:

```bash
cd apps/api && uv run python -m app.cli.generate_report --trade-date 2026-05-26 --kind close
```

Expected: command prints paths for HTML and PNG. The current baseline accepts historical report dates, so do not change date logic in this task.

- [ ] **Step 4: Inspect generated HTML for v2 sections**

Open the generated `report.html` or inspect text:

```bash
rg -n "核心结论|指数与市场情绪|昨日预判验证|板块详细分析|资金轮动路径|板块持续性排序|明日操作思路" reports/2026-05-26/close -g 'report.html'
```

Expected: all labels appear once in the approved order.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas/structured_review.py apps/api/app/services/structured_review_builder.py apps/api/app/renderers/templates/mobile_report.html.j2 apps/api/tests/test_structured_review.py apps/api/tests/test_report_api.py docs/superpowers/specs/2026-05-28-review-analysis-v2-design.md docs/superpowers/plans/2026-05-28-review-analysis-v2-implementation.md
git commit -m "feat: add review analysis v2 framework"
```

Expected: commit succeeds. Do not push or deploy until the user approves the preview.
