# Reference HTML Alignment v0.3d Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand structured review data and refactor the generated mobile `report.html` so the final HTML artifact more closely matches the user's reference long-form A-share review.

**Architecture:** Keep the backend report pipeline stable: providers produce existing `ReportDTO`, the deterministic structured-review builder expands it into richer sections, and `mobile_report.html.j2` renders those sections. LLM structured-review mode validates against the same expanded Pydantic schema and falls back to the rule builder on invalid output.

**Tech Stack:** FastAPI backend, Pydantic DTOs, Jinja2 HTML templates, deterministic fake providers, OpenAI-compatible JSON parsing tests, pytest, Ruff, Next/TypeScript checks.

---

## File Structure

- Modify `apps/api/app/schemas/structured_review.py`: add five new structured review section models and fields on `StructuredReviewDTO`.
- Modify `apps/api/app/services/structured_review_builder.py`: derive complete new sections from existing `ReportDTO` facts.
- Modify `apps/api/app/providers/llm.py`: update structured-review system prompt to require the expanded report sections.
- Modify `apps/api/app/renderers/templates/mobile_report.html.j2`: medium restructure of the mobile report and render all 12 reference-aligned sections.
- Modify `apps/api/tests/test_structured_review.py`: add schema and builder assertions for new fields.
- Modify `apps/api/tests/test_llm_provider.py`: update valid JSON fixture and prompt assertion.
- Modify `apps/api/tests/test_report_api.py`: assert expanded fields persist and HTML contains all target section titles.
- Modify `README.md`: document v0.3d reference HTML alignment.

---

### Task 1: Expand Structured Review Schema

**Files:**
- Modify: `apps/api/app/schemas/structured_review.py`
- Modify: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Write failing schema test**

Modify imports in `apps/api/tests/test_structured_review.py` to include the new classes:

```python
from app.schemas.structured_review import (
    ActionDiscipline,
    AfterHoursNewsSummary,
    CapitalRotationPath,
    IndexMidTermOutlook,
    MarketOverviewTable,
    NextDayOpportunityPlan,
    PracticalConclusion,
    PredictionReview,
    StructuredReviewDTO,
    StructuredSectorReview,
    SustainabilityRank,
    TomorrowJudgement,
)
```

In `test_structured_review_serializes_core_modules`, add these arguments to `StructuredReviewDTO(...)` after `market_overview=...`:

```python
        after_hours_news=AfterHoursNewsSummary(
            us_market_mapping=["英伟达链条映射仍需观察"],
            domestic_catalysts=["机器人产业催化延续"],
            risk_notes=["盘后消息只作为次日观察线索"],
        ),
```

Add these arguments after `sustainability_ranking=...` and before `action_discipline=...`:

```python
        capital_rotation=CapitalRotationPath(
            actual_path=["机器人承接", "PCB轮动", "防御补位"],
            key_finding="科技内部仍是资金轮动主场。",
            next_path_watch=["观察机器人分歧后是否回流", "观察PCB是否继续扩散"],
        ),
        next_day_opportunity=NextDayOpportunityPlan(
            focus_candidates=["机器人核心股承接", "PCB前排分歧转强"],
            position_discipline=["只观察确认后的承接，不追一致加速"],
            trigger_conditions=["指数不明显放量下杀", "主线前排分歧温和"],
            avoid_conditions=["缩量冲高回落", "无催化后排补涨"],
        ),
        practical_conclusion=PracticalConclusion(
            headline="明日重点是科技内部去弱留强。",
            bullet_points=["先看机器人承接", "再看PCB轮动强度", "弱分支不追高"],
        ),
        index_mid_term_outlook=IndexMidTermOutlook(
            year_review=["指数处于结构性修复阶段"],
            current_position="当前位置更适合观察量能和主线扩散，而不是预设单边趋势。",
            scenario_table=[
                {"scenario": "强势", "condition": "放量上行", "response": "观察主线扩散"},
                {"scenario": "震荡", "condition": "量能持平", "response": "控制节奏"},
            ],
        ),
```

Add these assertions after existing payload assertions:

```python
    assert payload["after_hours_news"]["domestic_catalysts"] == ["机器人产业催化延续"]
    assert payload["capital_rotation"]["actual_path"][0] == "机器人承接"
    assert payload["next_day_opportunity"]["focus_candidates"][0] == "机器人核心股承接"
    assert payload["practical_conclusion"]["headline"] == "明日重点是科技内部去弱留强。"
    assert payload["index_mid_term_outlook"]["scenario_table"][0]["scenario"] == "强势"
```

- [ ] **Step 2: Run schema test to verify failure**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py::test_structured_review_serializes_core_modules -q
```

Expected: FAIL with `ImportError` for `AfterHoursNewsSummary` or `NameError` for the new classes.

- [ ] **Step 3: Implement schema models**

Modify `apps/api/app/schemas/structured_review.py`. Add these classes after `MarketOverviewTable`:

```python
class AfterHoursNewsSummary(BaseModel):
    us_market_mapping: list[str] = Field(default_factory=list)
    domestic_catalysts: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class CapitalRotationPath(BaseModel):
    actual_path: list[str] = Field(default_factory=list)
    key_finding: str
    next_path_watch: list[str] = Field(default_factory=list)


class NextDayOpportunityPlan(BaseModel):
    focus_candidates: list[str] = Field(default_factory=list)
    position_discipline: list[str] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    avoid_conditions: list[str] = Field(default_factory=list)


class PracticalConclusion(BaseModel):
    headline: str
    bullet_points: list[str] = Field(default_factory=list)


class IndexMidTermOutlook(BaseModel):
    year_review: list[str] = Field(default_factory=list)
    current_position: str
    scenario_table: list[dict[str, str]] = Field(default_factory=list)
```

Modify `StructuredReviewDTO` to include these fields:

```python
    after_hours_news: AfterHoursNewsSummary
    capital_rotation: CapitalRotationPath
    next_day_opportunity: NextDayOpportunityPlan
    practical_conclusion: PracticalConclusion
    index_mid_term_outlook: IndexMidTermOutlook
```

Place `after_hours_news` after `market_overview`, and the other four after `sustainability_ranking` and before `action_discipline`.

- [ ] **Step 4: Run schema test to verify pass**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py::test_structured_review_serializes_core_modules -q
```

Expected: PASS.

- [ ] **Step 5: Commit schema expansion**

```bash
git add apps/api/app/schemas/structured_review.py apps/api/tests/test_structured_review.py
git commit -m "feat: expand structured review schema"
```

---

### Task 2: Populate Expanded Sections in Builder and LLM Fixture

**Files:**
- Modify: `apps/api/app/services/structured_review_builder.py`
- Modify: `apps/api/app/providers/llm.py`
- Modify: `apps/api/tests/test_structured_review.py`
- Modify: `apps/api/tests/test_llm_provider.py`

- [ ] **Step 1: Write failing builder assertions**

In `apps/api/tests/test_structured_review.py::test_build_structured_review_derives_core_modules_from_report`, add these assertions at the end:

```python
    assert review.after_hours_news.domestic_catalysts
    assert review.after_hours_news.risk_notes == ["盘后消息只作为次日观察线索，不作为单独决策依据。"]
    assert review.capital_rotation.actual_path[0] == "机器人承接"
    assert "机器人" in review.capital_rotation.key_finding
    assert review.next_day_opportunity.focus_candidates[0] == "机器人核心股承接确认"
    assert "不追一致加速" in review.next_day_opportunity.position_discipline[0]
    assert review.practical_conclusion.headline.startswith("明日最实战")
    assert review.index_mid_term_outlook.scenario_table[0]["scenario"] == "强势延续"
```

- [ ] **Step 2: Run builder test to verify failure**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py::test_build_structured_review_derives_core_modules_from_report -q
```

Expected: FAIL because `StructuredReviewDTO` construction in the builder is missing required new fields.

- [ ] **Step 3: Implement builder imports and fields**

Modify imports in `apps/api/app/services/structured_review_builder.py`:

```python
from app.schemas.structured_review import (
    ActionDiscipline,
    AfterHoursNewsSummary,
    CapitalRotationPath,
    IndexMidTermOutlook,
    MarketOverviewTable,
    NextDayOpportunityPlan,
    PracticalConclusion,
    PredictionReview,
    StructuredReviewDTO,
    StructuredSectorReview,
    SustainabilityRank,
    SustainabilityRating,
    TomorrowJudgement,
)
```

In `build_structured_review`, add `after_hours_news` after `market_overview`:

```python
        after_hours_news=_build_after_hours_news(report),
```

Add these fields after `sustainability_ranking=...` and before `action_discipline=...`:

```python
        capital_rotation=_build_capital_rotation(report, leader, runner_up),
        next_day_opportunity=_build_next_day_opportunity(report, leader),
        practical_conclusion=_build_practical_conclusion(leader_name, runner_up_name),
        index_mid_term_outlook=_build_index_mid_term_outlook(report),
```

- [ ] **Step 4: Implement builder helpers**

Add these helper functions after `_build_market_overview`:

```python
def _build_after_hours_news(report: ReportDTO) -> AfterHoursNewsSummary:
    domestic = [item.title for item in report.news[:4] if item.title]
    if not domestic:
        domestic = [f"{sector.name}方向消息确认度仍需结合次日竞价观察" for sector in report.sectors[:2]]
    us_mapping = [f"海外映射重点观察{report.sectors[0].name}产业链反馈"] if report.sectors else ["海外映射暂未形成明确方向"]
    return AfterHoursNewsSummary(
        us_market_mapping=us_mapping,
        domestic_catalysts=domestic[:4],
        risk_notes=["盘后消息只作为次日观察线索，不作为单独决策依据。"],
    )


def _build_capital_rotation(
    report: ReportDTO,
    leader: SectorCandidate | None,
    runner_up: SectorCandidate | None,
) -> CapitalRotationPath:
    sector_names = [sector.name for sector in report.sectors[:4]]
    actual_path = [f"{name}承接" if index == 0 else f"{name}轮动" for index, name in enumerate(sector_names)]
    if not actual_path:
        actual_path = ["等待主线确认"]
    leader_name = leader.name if leader else "暂无主线"
    runner_up_name = runner_up.name if runner_up else "暂无轮动方向"
    return CapitalRotationPath(
        actual_path=actual_path,
        key_finding=f"资金仍围绕{leader_name}展开，但{runner_up_name}的轮动强度决定次日扩散质量。",
        next_path_watch=[
            f"观察{leader_name}分歧后的回流强度",
            f"观察{runner_up_name}是否从轮动转为持续",
            "观察防御方向是否只是一日避险",
        ],
    )


def _build_next_day_opportunity(report: ReportDTO, leader: SectorCandidate | None) -> NextDayOpportunityPlan:
    leader_name = leader.name if leader else "主线"
    focus = [f"{leader_name}核心股承接确认"]
    focus.extend(f"{sector.name}前排分歧转强" for sector in report.sectors[1:3])
    return NextDayOpportunityPlan(
        focus_candidates=focus,
        position_discipline=["只观察确认后的承接，不追一致加速。", "弱分支只看修复，不做主线预设。"],
        trigger_conditions=["指数不出现明显放量下杀", "主线前排分歧温和", "成交额维持活跃区间"],
        avoid_conditions=["缩量冲高回落", "无催化后排补涨", "高位一致加速后的被动追高"],
    )


def _build_practical_conclusion(leader_name: str, runner_up_name: str) -> PracticalConclusion:
    return PracticalConclusion(
        headline=f"明日最实战的观察，是围绕{leader_name}去弱留强，同时确认{runner_up_name}是否具备持续性。",
        bullet_points=[
            f"先看{leader_name}核心股承接，而不是后排补涨。",
            f"再看{runner_up_name}能否从轮动变成持续。",
            "如果指数放量下杀，优先降低节奏预期。",
        ],
    )


def _build_index_mid_term_outlook(report: ReportDTO) -> IndexMidTermOutlook:
    index_name = report.indices[0].name if report.indices else "上证指数"
    index_change = report.indices[0].pct_change if report.indices else 0
    position = "偏强修复" if index_change >= 0 else "震荡承压"
    return IndexMidTermOutlook(
        year_review=[
            f"{index_name}当前更像结构行情载体，指数方向需要结合成交额和主线扩散判断。",
            "年度级别判断暂不预设单边趋势，优先跟踪量能与赚钱效应。",
        ],
        current_position=f"{report.trade_date}收盘后，指数处于{position}状态，短线重点看强势板块是否带动赚钱效应扩散。",
        scenario_table=[
            {"scenario": "强势延续", "condition": "指数放量上行且主线扩散", "response": "观察核心方向承接与轮动扩散"},
            {"scenario": "震荡分化", "condition": "指数量能持平且板块轮动", "response": "控制节奏，优先去弱留强"},
            {"scenario": "转弱防守", "condition": "指数放量下杀且高位退潮", "response": "降低预期，回避后排补涨"},
        ],
    )
```

- [ ] **Step 5: Update valid LLM JSON fixture**

In `apps/api/tests/test_llm_provider.py::_valid_structured_payload`, add `after_hours_news` after `market_overview`:

```python
        "after_hours_news": {
            "us_market_mapping": ["海外科技链条反馈仍需观察"],
            "domestic_catalysts": ["机器人产业催化延续"],
            "risk_notes": ["盘后消息只作为次日观察线索"],
        },
```

Add these fields after `sustainability_ranking` and before `action_discipline`:

```python
        "capital_rotation": {
            "actual_path": ["机器人承接", "PCB轮动"],
            "key_finding": "资金仍在科技内部切换。",
            "next_path_watch": ["观察机器人分歧后回流", "观察PCB扩散质量"],
        },
        "next_day_opportunity": {
            "focus_candidates": ["机器人核心股承接确认"],
            "position_discipline": ["不追一致加速"],
            "trigger_conditions": ["指数不放量下杀"],
            "avoid_conditions": ["缩量冲高回落"],
        },
        "practical_conclusion": {
            "headline": "明日围绕机器人去弱留强。",
            "bullet_points": ["先看承接", "再看轮动"],
        },
        "index_mid_term_outlook": {
            "year_review": ["指数仍是结构行情载体"],
            "current_position": "当前位置观察量能和主线扩散。",
            "scenario_table": [
                {"scenario": "强势延续", "condition": "放量上行", "response": "观察扩散"}
            ],
        },
```

Add assertion in `test_openai_llm_provider_maps_json_to_structured_review`:

```python
    assert review.capital_rotation.actual_path == ["机器人承接", "PCB轮动"]
```

- [ ] **Step 6: Update LLM system prompt**

Modify `STRUCTURED_REVIEW_SYSTEM_PROMPT` in `apps/api/app/providers/llm.py` to include:

```python
STRUCTURED_REVIEW_SYSTEM_PROMPT = """你是A股盘后复盘助手。只基于用户提供的结构化事实生成 JSON。
不得编造未提供的数字、板块、个股、新闻来源。
没有前一日报告时 prediction_review.source 必须为 manual_placeholder。
必须输出完整 StructuredReviewDTO 字段，包括 after_hours_news、capital_rotation、next_day_opportunity、practical_conclusion、index_mid_term_outlook。
所有买卖建议必须改写为观察条件、风险分层、仓位纪律、回避清单。
不要使用确定性荐股语气，不要承诺收益。
输出必须是合法 JSON，且字段匹配 StructuredReviewDTO。"""
```

- [ ] **Step 7: Run structured and LLM tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_structured_review.py tests/test_llm_provider.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit builder and LLM updates**

```bash
git add apps/api/app/services/structured_review_builder.py apps/api/app/providers/llm.py apps/api/tests/test_structured_review.py apps/api/tests/test_llm_provider.py
git commit -m "feat: populate reference html review sections"
```

---

### Task 3: Render Reference-Aligned HTML Sections

**Files:**
- Modify: `apps/api/app/renderers/templates/mobile_report.html.j2`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Write failing renderer assertions**

In `apps/api/tests/test_report_api.py::test_mobile_report_renderer_contains_core_sections`, replace the section-title assertions with this list-driven check:

```python
    expected_titles = [
        "昨日预判验证",
        "先给结论",
        "盘面总览",
        "各板块详细分析",
        "盘后 / 隔夜消息梳理",
        "板块持续性排序",
        "资金轮动路径分析",
        "明日可介入标的与仓位建议",
        "自选股观察",
        "去弱留强排序",
        "最实战的结论",
        "上证指数中期走势研判",
    ]
    for title in expected_titles:
        assert title in html
```

Also keep these assertions:

```python
    assert "科技内部" in html
    assert "非投资建议" in html
```

- [ ] **Step 2: Add persistence assertions**

In `test_report_generator_writes_structured_review_to_report_and_snapshot`, add:

```python
    assert result.report.structured_review.after_hours_news.domestic_catalysts
    assert result.report.structured_review.capital_rotation.actual_path
    assert report_dto["structured_review"]["practical_conclusion"]["headline"].startswith("明日最实战")
    assert snapshot["report"]["structured_review"]["index_mid_term_outlook"]["scenario_table"][0]["scenario"] == "强势延续"
```

- [ ] **Step 3: Run renderer test to verify failure**

Run:

```bash
cd apps/api && uv run pytest tests/test_report_api.py::test_mobile_report_renderer_contains_core_sections -q
```

Expected: FAIL because the current template does not contain the five new section titles.

- [ ] **Step 4: Replace structured branch in template**

Modify only the `{% if structured %}` branch in `apps/api/app/renderers/templates/mobile_report.html.j2`. Preserve the legacy `{% else %}` branch.

Use this section order and ensure every title is literal text in the template:

```jinja2
          <section>
            <div class="section-title"><span class="section-num">01</span><h2>昨日预判验证</h2></div>
            ... existing prediction review content ...
          </section>

          <section>
            <div class="section-title"><span class="section-num">02</span><h2>先给结论</h2></div>
            ... tomorrow_judgement table ...
          </section>

          <section>
            <div class="section-title"><span class="section-num">03</span><h2>盘面总览</h2></div>
            ... market_overview tables ...
          </section>

          <section>
            <div class="section-title"><span class="section-num">04</span><h2>各板块详细分析</h2></div>
            ... sector_reviews cards ...
          </section>

          <section>
            <div class="section-title"><span class="section-num">05</span><h2>盘后 / 隔夜消息梳理</h2></div>
            <div class="grid-2">
              <div class="info-card"><div class="mini-title">美股映射</div><ul>{% for item in structured.after_hours_news.us_market_mapping %}<li>{{ item }}</li>{% endfor %}</ul></div>
              <div class="info-card"><div class="mini-title">国内催化</div><ul>{% for item in structured.after_hours_news.domestic_catalysts %}<li>{{ item }}</li>{% endfor %}</ul></div>
            </div>
            <div class="note-card"><ul>{% for item in structured.after_hours_news.risk_notes %}<li>{{ item }}</li>{% endfor %}</ul></div>
          </section>

          <section>
            <div class="section-title"><span class="section-num">06</span><h2>板块持续性排序</h2></div>
            ... sustainability_ranking table ...
          </section>

          <section>
            <div class="section-title"><span class="section-num">07</span><h2>资金轮动路径分析</h2></div>
            <div class="conclusion-box"><p>{{ structured.capital_rotation.key_finding }}</p></div>
            <div class="pill-row">{% for item in structured.capital_rotation.actual_path %}<span class="pill">{{ item }}</span>{% endfor %}</div>
            <div class="mini-title">次日路径观察</div><ul>{% for item in structured.capital_rotation.next_path_watch %}<li>{{ item }}</li>{% endfor %}</ul>
          </section>

          <section>
            <div class="section-title"><span class="section-num">08</span><h2>明日可介入标的与仓位建议</h2></div>
            <div class="grid-2">
              <div class="info-card"><div class="mini-title">观察候选</div><ul>{% for item in structured.next_day_opportunity.focus_candidates %}<li>{{ item }}</li>{% endfor %}</ul></div>
              <div class="info-card"><div class="mini-title">仓位纪律</div><ul>{% for item in structured.next_day_opportunity.position_discipline %}<li>{{ item }}</li>{% endfor %}</ul></div>
            </div>
            <table><tr><th>触发条件</th><th>回避条件</th></tr><tr><td><ul>{% for item in structured.next_day_opportunity.trigger_conditions %}<li>{{ item }}</li>{% endfor %}</ul></td><td><ul>{% for item in structured.next_day_opportunity.avoid_conditions %}<li>{{ item }}</li>{% endfor %}</ul></td></tr></table>
          </section>

          <section>
            <div class="section-title"><span class="section-num">09</span><h2>自选股观察</h2></div>
            ... existing watchlist content ...
          </section>

          <section>
            <div class="section-title"><span class="section-num">10</span><h2>去弱留强排序</h2></div>
            ... action_discipline focus and avoid ...
          </section>

          <section>
            <div class="section-title"><span class="section-num">11</span><h2>最实战的结论</h2></div>
            <div class="conclusion-box"><p>{{ structured.practical_conclusion.headline }}</p></div>
            <ul>{% for item in structured.practical_conclusion.bullet_points %}<li>{{ item }}</li>{% endfor %}</ul>
          </section>

          <section>
            <div class="section-title"><span class="section-num">12</span><h2>上证指数中期走势研判</h2></div>
            <div class="note-card"><ul>{% for item in structured.index_mid_term_outlook.year_review %}<li>{{ item }}</li>{% endfor %}</ul></div>
            <p>{{ structured.index_mid_term_outlook.current_position }}</p>
            <table><tr><th>情景</th><th>条件</th><th>应对</th></tr>{% for row in structured.index_mid_term_outlook.scenario_table %}<tr><td>{{ row.scenario }}</td><td>{{ row.condition }}</td><td>{{ row.response }}</td></tr>{% endfor %}</table>
          </section>
```

While editing CSS in the same template, add these reusable classes:

```css
    .info-card { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 12px; }
    .note-card { background: #f8f4ea; border: 1px solid var(--line); border-radius: 14px; padding: 12px; margin-top: 10px; }
    .lead { color: var(--navy-soft); font-weight: 700; }
```

- [ ] **Step 5: Run renderer and report tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_report_api.py::test_mobile_report_renderer_contains_core_sections tests/test_report_api.py::test_report_generator_writes_structured_review_to_report_and_snapshot -q
```

Expected: PASS.

- [ ] **Step 6: Commit HTML renderer update**

```bash
git add apps/api/app/renderers/templates/mobile_report.html.j2 apps/api/tests/test_report_api.py
git commit -m "feat: render reference aligned html report"
```

---

### Task 4: Document v0.3d Reference HTML Alignment

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Add after the `OCR Watchlist Import` section:

```markdown
## Reference HTML Alignment

v0.3d expands the structured review schema and generated `report.html` toward the supplied long-form reference HTML.

Added report modules:

- `盘后 / 隔夜消息梳理`
- `资金轮动路径分析`
- `明日可介入标的与仓位建议`
- `最实战的结论`
- `上证指数中期走势研判`

The HTML remains the primary artifact. Provider data, watchlists, TickFlow enrichment, and OCR imports all feed the same structured report pipeline; the renderer turns that pipeline into the final mobile-friendly HTML/PNG.
```

Also update `Future v0.3 Items` by removing or rewording `Reference HTML aligned structured long-report template` because it is now implemented.

- [ ] **Step 2: Run markdown diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Commit docs**

```bash
git add README.md
git commit -m "docs: document reference html alignment"
```

---

### Task 5: Full Verification and Local Merge

**Files:**
- No new files expected unless fixes are required.

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd apps/api && uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run backend lint**

Run:

```bash
cd apps/api && uv run ruff check .
```

Expected: PASS.

- [ ] **Step 3: Run frontend type checks**

Run:

```bash
corepack pnpm --filter @stock-review/web test
corepack pnpm --filter @stock-review/web lint
```

Expected: PASS.

- [ ] **Step 4: Run HTML smoke**

Run:

```bash
cd apps/api && uv run python - <<'PY'
from pathlib import Path
from app.providers.llm import FakeLLMProvider
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.renderers.html_renderer import render_mobile_report_html
from app.services.report_generator import ReportGenerator

generator = ReportGenerator(
    reports_root=Path('/tmp/stock-review-v03d-smoke'),
    market_provider=FakeMarketDataProvider(),
    news_provider=FakeNewsProvider(),
    llm_provider=FakeLLMProvider(),
)
result = generator.generate_close_report('2026-05-26')
html = render_mobile_report_html(result.report)
for title in [
    '盘后 / 隔夜消息梳理',
    '资金轮动路径分析',
    '明日可介入标的与仓位建议',
    '最实战的结论',
    '上证指数中期走势研判',
]:
    assert title in html, title
assert result.assets.report_html.exists()
print(result.assets.report_html)
PY
```

Expected: prints a `report.html` path and exits 0.

- [ ] **Step 5: Secret-like scan**

Run:

```bash
python3 - <<'PY'
import subprocess, sys
pattern = r'(tk_|sk-)[A-Za-z0-9]{20,}'
result = subprocess.run(['git', 'grep', '-I', '-E', '-l', pattern, '--', '.'], text=True, stdout=subprocess.PIPE)
if result.returncode == 0:
    print('SECRET_LIKE_PATTERN_FOUND')
    print(result.stdout)
    sys.exit(1)
if result.returncode == 1:
    print('working tree secret-like scan clean')
    sys.exit(0)
sys.exit(result.returncode)
PY
```

Expected: `working tree secret-like scan clean`.

- [ ] **Step 6: Merge back to main locally**

Run from original main worktree:

```bash
cd "/Users/kale/Documents/stock fupan"
git status --short
git merge --no-ff codex/reference-html-v03d -m "merge: reference html alignment v0.3d"
```

Then rerun the same backend, frontend, and secret-like checks on `main`.

- [ ] **Step 7: Clean up worktree and branch after merged verification**

Run:

```bash
git worktree remove "/Users/kale/.config/superpowers/worktrees/stock fupan/codex/reference-html-v03d"
git branch -d codex/reference-html-v03d
git status --short --branch
```

Expected: only `main` worktree remains and status is clean.

---

## Plan Self-Review

- Spec coverage: expanded schema, builder, LLM prompt/fixture, HTML section order, docs, tests, smoke, merge, and secret hygiene are covered.
- Placeholder scan: no `TBD`, `TODO`, `implement later`, or vague test-only instructions remain.
- Type consistency: schema fields use `after_hours_news`, `capital_rotation`, `next_day_opportunity`, `practical_conclusion`, and `index_mid_term_outlook` consistently across builder, tests, template, and LLM fixture.
- Scope check: no new providers, scheduler, PDF/Markdown export, manual editor, or pixel-perfect clone work is included.
