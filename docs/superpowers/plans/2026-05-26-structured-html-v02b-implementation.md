# v0.2b Structured HTML Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a structured-review vertical slice that generates reference-HTML-aligned A-share review reports while preserving existing API and frontend compatibility.

**Architecture:** Add focused Pydantic models for structured review content, a deterministic builder that derives the new structure from existing `ReportDTO`, and update the generator to attach it before rendering and snapshot writes. Rewrite the mobile HTML template to render structured long-form sections when `structured_review` exists, with a fallback path for legacy reports.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, Jinja2, pytest, ruff, Next.js, TypeScript, Tailwind, pnpm, uv.

---

## File Structure

Create or modify these files:

```text
apps/api/app/schemas/structured_review.py       # new structured review DTOs
apps/api/app/schemas/report.py                  # add optional structured_review to ReportDTO
apps/api/app/services/structured_review_builder.py # deterministic builder from ReportDTO
apps/api/app/services/report_generator.py       # attach structured_review before validation/render/snapshot
apps/api/app/renderers/templates/mobile_report.html.j2 # structured long-form HTML
apps/api/tests/test_structured_review.py        # schema and builder tests
apps/api/tests/test_report_api.py               # generator/snapshot/renderer assertions
apps/web/lib/types.ts                           # optional structured_review API types
```

---

### Task 1: Add Structured Review Schema

**Files:**
- Create: `apps/api/app/schemas/structured_review.py`
- Modify: `apps/api/app/schemas/report.py`
- Create: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Write failing schema serialization test**

Create `apps/api/tests/test_structured_review.py`:

```python
from app.schemas.structured_review import (
    ActionDiscipline,
    MarketOverviewTable,
    PredictionReview,
    StructuredReviewDTO,
    StructuredSectorReview,
    SustainabilityRank,
    TomorrowJudgement,
)


def test_structured_review_serializes_core_modules() -> None:
    review = StructuredReviewDTO(
        topic="科技内部淘汰赛 · 主线换挡日",
        prediction_review=PredictionReview(
            previous_prediction="昨日预判机器人方向分歧后仍有承接。",
            actual_result="机器人方向继续领涨，PCB轮动增强。",
            correct_items=["机器人方向延续强势"],
            missed_items=["PCB强度高于预期"],
            revision="明日观察机器人与PCB之间的资金切换。",
            source="manual_placeholder",
        ),
        tomorrow_judgement=TomorrowJudgement(
            most_likely_to_continue="机器人",
            most_likely_to_diverge="PCB",
            rotation_candidates=["PCB"],
            defensive_candidates=["高股息"],
            core_view="主线仍在科技内部轮动，去弱留强。",
        ),
        market_overview=MarketOverviewTable(
            index_rows=[{"name": "上证指数", "close": "3100.50", "change": "+1.20%"}],
            emotion_rows=[{"label": "涨停 / 跌停", "value": "86 / 8"}],
            structure_features=["放量", "分化"],
            capital_flow_summary="资金集中在科技方向内部轮动。",
        ),
        sector_reviews=[
            StructuredSectorReview(
                sector="机器人",
                headline="机器人：主线承接仍强",
                stage="主升延续",
                strengths=["涨幅居前", "新闻催化明确"],
                weaknesses=["高位分歧可能加大"],
                logic="产业消息与短线强度共振。",
                sustainability="high",
                next_day_view="观察分歧后的核心股承接。",
                watch_items=["核心股回踩不破均线"],
                avoid_items=["缩量冲高回落"],
            )
        ],
        sustainability_ranking=[
            SustainabilityRank(rank=1, sector="机器人", rating="high", reason="强度和催化同时领先")
        ],
        action_discipline=ActionDiscipline(
            focus=["保留机器人核心方向观察"],
            avoid=["回避无催化的跟风补涨"],
            final_view="明日重点是科技内部去弱留强。",
        ),
    )

    payload = review.model_dump(mode="json")

    assert payload["topic"] == "科技内部淘汰赛 · 主线换挡日"
    assert payload["prediction_review"]["source"] == "manual_placeholder"
    assert payload["sector_reviews"][0]["sustainability"] == "high"
    assert payload["action_discipline"]["avoid"] == ["回避无催化的跟风补涨"]
```

- [ ] **Step 2: Run schema test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py::test_structured_review_serializes_core_modules -v
```

Expected: FAIL because `app.schemas.structured_review` does not exist.

- [ ] **Step 3: Implement structured review models**

Create `apps/api/app/schemas/structured_review.py`:

```python
from typing import Literal

from pydantic import BaseModel, Field


PredictionSource = Literal["manual_placeholder", "previous_report"]
SustainabilityRating = Literal["high", "medium", "low"]


class PredictionReview(BaseModel):
    previous_prediction: str
    actual_result: str
    correct_items: list[str] = Field(default_factory=list)
    missed_items: list[str] = Field(default_factory=list)
    revision: str
    source: PredictionSource = "manual_placeholder"


class TomorrowJudgement(BaseModel):
    most_likely_to_continue: str
    most_likely_to_diverge: str
    rotation_candidates: list[str] = Field(default_factory=list)
    defensive_candidates: list[str] = Field(default_factory=list)
    core_view: str


class MarketOverviewTable(BaseModel):
    index_rows: list[dict[str, str]] = Field(default_factory=list)
    emotion_rows: list[dict[str, str]] = Field(default_factory=list)
    structure_features: list[str] = Field(default_factory=list)
    capital_flow_summary: str


class StructuredSectorReview(BaseModel):
    sector: str
    headline: str
    stage: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    logic: str
    sustainability: SustainabilityRating
    next_day_view: str
    watch_items: list[str] = Field(default_factory=list)
    avoid_items: list[str] = Field(default_factory=list)


class SustainabilityRank(BaseModel):
    rank: int
    sector: str
    rating: SustainabilityRating
    reason: str


class ActionDiscipline(BaseModel):
    focus: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    final_view: str


class StructuredReviewDTO(BaseModel):
    topic: str
    prediction_review: PredictionReview
    tomorrow_judgement: TomorrowJudgement
    market_overview: MarketOverviewTable
    sector_reviews: list[StructuredSectorReview] = Field(default_factory=list)
    sustainability_ranking: list[SustainabilityRank] = Field(default_factory=list)
    action_discipline: ActionDiscipline
```

Modify `apps/api/app/schemas/report.py` imports:

```python
from app.schemas.structured_review import StructuredReviewDTO
```

Add to `ReportDTO` after `news`:

```python
    structured_review: StructuredReviewDTO | None = None
```

- [ ] **Step 4: Run schema test**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py::test_structured_review_serializes_core_modules -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas/structured_review.py apps/api/app/schemas/report.py apps/api/tests/test_structured_review.py
git commit -m "feat: add structured review schema"
```

---

### Task 2: Build Structured Review From Existing Report

**Files:**
- Create: `apps/api/app/services/structured_review_builder.py`
- Modify: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Append deterministic builder test**

Append to `apps/api/tests/test_structured_review.py`:

```python
from app.providers.llm import FakeLLMProvider
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.rules.scoring import score_sectors
from app.schemas.report import ReportDTO, ReportKind, SectorCandidate
from app.services.structured_review_builder import build_structured_review


def _fake_report() -> ReportDTO:
    market = FakeMarketDataProvider()
    news = FakeNewsProvider()
    llm = FakeLLMProvider()
    snapshot = market.get_close_snapshot("2026-05-26")
    news_items = []
    for raw_sector in snapshot.raw_sectors:
        news_items.extend(news.search_sector_news(raw_sector.name, snapshot.trade_date))
    scored = score_sectors(snapshot.raw_sectors, top_n=5)
    return ReportDTO(
        trade_date=snapshot.trade_date,
        kind=ReportKind.CLOSE,
        title="2026-05-26 A股复盘",
        indices=snapshot.indices,
        breadth=snapshot.breadth,
        turnover_cny=snapshot.turnover_cny,
        market_state_tags=snapshot.market_state_tags,
        sectors=[
            SectorCandidate(
                name=sector.name,
                score=sector.score,
                rank=sector.rank,
                pct_change=sector.pct_change,
                reason="综合评分靠前",
                news_summaries=[item.summary for item in news_items if item.matched_sector == sector.name],
                factor_scores=sector.factor_scores,
            )
            for sector in scored
        ],
        narrative=llm.generate_narrative(snapshot.to_report_seed(news_items)),
        news=news_items,
    )


def test_build_structured_review_derives_core_modules_from_report() -> None:
    report = _fake_report()

    review = build_structured_review(report)

    assert review.topic == "放量分化 · 机器人领涨 · PCB轮动"
    assert review.prediction_review.source == "manual_placeholder"
    assert review.tomorrow_judgement.most_likely_to_continue == "机器人"
    assert review.tomorrow_judgement.most_likely_to_diverge == "PCB"
    assert review.market_overview.emotion_rows == [
        {"label": "上涨 / 下跌", "value": "3200 / 1800"},
        {"label": "涨停 / 跌停", "value": "86 / 8"},
        {"label": "成交额", "value": "12345.67 亿"},
    ]
    assert review.sector_reviews[0].sector == "机器人"
    assert review.sector_reviews[0].sustainability == "high"
    assert review.sustainability_ranking[0].sector == "机器人"
    assert "机器人" in review.action_discipline.final_view
```

- [ ] **Step 2: Run builder test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py::test_build_structured_review_derives_core_modules_from_report -v
```

Expected: FAIL because `app.services.structured_review_builder` does not exist.

- [ ] **Step 3: Implement deterministic builder**

Create `apps/api/app/services/structured_review_builder.py`:

```python
from app.schemas.report import ReportDTO, SectorCandidate
from app.schemas.structured_review import (
    ActionDiscipline,
    MarketOverviewTable,
    PredictionReview,
    StructuredReviewDTO,
    StructuredSectorReview,
    SustainabilityRank,
    SustainabilityRating,
    TomorrowJudgement,
)


def build_structured_review(report: ReportDTO) -> StructuredReviewDTO:
    leader = report.sectors[0] if report.sectors else None
    runner_up = report.sectors[1] if len(report.sectors) > 1 else None
    leader_name = leader.name if leader else "暂无主线"
    runner_up_name = runner_up.name if runner_up else "暂无轮动方向"

    return StructuredReviewDTO(
        topic=_build_topic(report, leader, runner_up),
        prediction_review=PredictionReview(
            previous_prediction="昨日预判暂未接入自动回放，本阶段保留为结构化手动输入位。",
            actual_result=_build_actual_result(report, leader, runner_up),
            correct_items=[f"{leader_name}方向保持相对强势"] if leader else [],
            missed_items=["自动对比前一日报告尚未启用"],
            revision=f"后续预判重点观察{leader_name}与{runner_up_name}之间的资金切换。",
            source="manual_placeholder",
        ),
        tomorrow_judgement=TomorrowJudgement(
            most_likely_to_continue=leader_name,
            most_likely_to_diverge=runner_up_name,
            rotation_candidates=[sector.name for sector in report.sectors[1:4]],
            defensive_candidates=["高股息", "低位防御"],
            core_view=f"明日重点不是追高扩散，而是观察{leader_name}分歧后的承接与{runner_up_name}轮动强度。",
        ),
        market_overview=_build_market_overview(report),
        sector_reviews=[_build_sector_review(sector) for sector in report.sectors],
        sustainability_ranking=[
            SustainabilityRank(
                rank=index + 1,
                sector=sector.name,
                rating=_rating_for_sector(sector),
                reason=_sustainability_reason(sector),
            )
            for index, sector in enumerate(report.sectors)
        ],
        action_discipline=ActionDiscipline(
            focus=[f"优先观察{leader_name}核心标的承接"] if leader else ["等待新主线确认"],
            avoid=["回避无新闻催化的跟风补涨", "回避缩量冲高后回落的弱转强失败"],
            final_view=f"最实战的动作是围绕{leader_name}去弱留强，同时警惕高位一致后的分歧。",
        ),
    )


def _build_topic(report: ReportDTO, leader: SectorCandidate | None, runner_up: SectorCandidate | None) -> str:
    tag_text = "".join(report.market_state_tags) or "结构行情"
    leader_name = leader.name if leader else "暂无主线"
    if runner_up is None:
        return f"{tag_text} · {leader_name}领涨"
    return f"{tag_text} · {leader_name}领涨 · {runner_up.name}轮动"


def _build_actual_result(report: ReportDTO, leader: SectorCandidate | None, runner_up: SectorCandidate | None) -> str:
    sector_text = "、".join(sector.name for sector in report.sectors[:2]) or "暂无强势板块"
    return f"{report.trade_date}市场呈现{'、'.join(report.market_state_tags) or '结构性'}特征，{sector_text}相对靠前。"


def _build_market_overview(report: ReportDTO) -> MarketOverviewTable:
    return MarketOverviewTable(
        index_rows=[
            {
                "name": index.name,
                "close": f"{index.close:.2f}",
                "change": f"{index.pct_change:+.2f}%",
            }
            for index in report.indices
        ],
        emotion_rows=[
            {"label": "上涨 / 下跌", "value": f"{report.breadth.up_count} / {report.breadth.down_count}"},
            {"label": "涨停 / 跌停", "value": f"{report.breadth.limit_up_count} / {report.breadth.limit_down_count}"},
            {"label": "成交额", "value": f"{report.turnover_cny:.2f} 亿"},
        ],
        structure_features=report.market_state_tags,
        capital_flow_summary="资金不是简单流入流出，而是在强势板块之间做结构切换。",
    )


def _build_sector_review(sector: SectorCandidate) -> StructuredSectorReview:
    rating = _rating_for_sector(sector)
    return StructuredSectorReview(
        sector=sector.name,
        headline=f"{sector.name}：{_headline_suffix(rating)}",
        stage=_stage_for_rating(rating),
        strengths=[
            f"涨跌幅{sector.pct_change:+.2f}%",
            f"综合评分{sector.score:.1f}",
            *(sector.news_summaries[:1] or [sector.reason]),
        ],
        weaknesses=["短线一致后可能出现分歧", "后排跟风股承接要求更高"],
        logic="短线强度、板块广度与消息催化共同决定当前排序。",
        sustainability=rating,
        next_day_view=f"观察{sector.name}方向分歧后的核心股承接，而不是简单追逐后排补涨。",
        watch_items=[f"{sector.name}核心股回踩承接", "板块内强弱切换是否温和"],
        avoid_items=["缩量冲高回落", "无催化的低位跟风"],
    )


def _rating_for_sector(sector: SectorCandidate) -> SustainabilityRating:
    if sector.score >= 70 and sector.news_summaries:
        return "high"
    if sector.score >= 45:
        return "medium"
    return "low"


def _headline_suffix(rating: SustainabilityRating) -> str:
    return {
        "high": "主线承接仍强",
        "medium": "轮动强度待确认",
        "low": "持续性偏弱",
    }[rating]


def _stage_for_rating(rating: SustainabilityRating) -> str:
    return {
        "high": "主升延续",
        "medium": "轮动观察",
        "low": "弱修复",
    }[rating]


def _sustainability_reason(sector: SectorCandidate) -> str:
    if sector.news_summaries:
        return f"评分{sector.score:.1f}，且具备消息催化。"
    return f"评分{sector.score:.1f}，消息确认度仍需观察。"
```

- [ ] **Step 4: Run structured review tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/structured_review_builder.py apps/api/tests/test_structured_review.py
git commit -m "feat: build structured review from report"
```

---

### Task 3: Thread Structured Review Through Generator and API Assets

**Files:**
- Modify: `apps/api/app/services/report_generator.py`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add generator and snapshot assertions**

Append to `apps/api/tests/test_report_api.py`:

```python

def test_report_generator_writes_structured_review_to_report_and_snapshot(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    assert result.report.structured_review is not None
    assert result.report.structured_review.topic == "放量分化 · 机器人领涨 · PCB轮动"
    assert result.report.structured_review.prediction_review.source == "manual_placeholder"

    report_dto = json.loads(result.assets.report_dto.read_text(encoding="utf-8"))
    snapshot = json.loads(result.assets.snapshot.read_text(encoding="utf-8"))
    assert report_dto["structured_review"]["tomorrow_judgement"]["most_likely_to_continue"] == "机器人"
    assert snapshot["report"]["structured_review"] == report_dto["structured_review"]
```

- [ ] **Step 2: Run generator structured test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_report_generator_writes_structured_review_to_report_and_snapshot -v
```

Expected: FAIL because `structured_review` is not attached by `ReportGenerator`.

- [ ] **Step 3: Attach structured review in generator**

Modify `apps/api/app/services/report_generator.py` imports:

```python
from app.services.structured_review_builder import build_structured_review
```

After creating `report = ReportDTO(...)` and before validation:

```python
        report.structured_review = build_structured_review(report)
```

Keep `validate_narrative_facts(report)` after this assignment. The existing validation only reads existing narrative/facts and should continue to pass.

- [ ] **Step 4: Run report API tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/report_generator.py apps/api/tests/test_report_api.py
git commit -m "feat: attach structured review to generated reports"
```

---

### Task 4: Render Reference-Aligned Structured HTML

**Files:**
- Modify: `apps/api/app/renderers/templates/mobile_report.html.j2`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Replace renderer test assertions with structured sections**

Modify `test_mobile_report_renderer_contains_core_sections` in `apps/api/tests/test_report_api.py` so its assertions are:

```python
    assert "2026-05-26 A股复盘" in html
    assert "昨日预判验证" in html
    assert "明日核心判断" in html
    assert "盘面总览" in html
    assert "板块详细分析" in html
    assert "持续性排序" in html
    assert "去弱留强" in html
    assert "回避清单" in html
    assert "科技内部" in html
    assert "非投资建议" in html
```

- [ ] **Step 2: Run renderer test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_mobile_report_renderer_contains_core_sections -v
```

Expected: FAIL because current template does not contain the new structured sections.

- [ ] **Step 3: Rewrite mobile report template with structured branch and legacy fallback**

Replace `apps/api/app/renderers/templates/mobile_report.html.j2` with:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ report.title }}</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #ece7dc;
      --paper: #fffdf8;
      --panel: #ffffff;
      --navy: #17233b;
      --navy-soft: #243653;
      --gold: #c9a34e;
      --gold-soft: #fff5d8;
      --green-soft: #edf7ee;
      --green-line: #8fb99a;
      --ink: #1d2433;
      --muted: #6f6a60;
      --line: #e2d7c3;
      --red: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      line-height: 1.72;
    }
    .page { max-width: 640px; margin: 0 auto; padding: 24px 16px 36px; }
    .paper { background: var(--paper); border: 1px solid var(--line); box-shadow: 0 20px 50px rgba(23, 35, 59, .14); }
    .hero { background: linear-gradient(135deg, var(--navy), #0f1a2d); color: white; padding: 28px 24px; text-align: center; border-bottom: 4px solid var(--gold); }
    .brand { color: var(--gold); font-size: 12px; font-weight: 800; letter-spacing: .22em; text-transform: uppercase; }
    h1 { margin: 8px 0 0; font-size: 30px; line-height: 1.2; letter-spacing: -.04em; }
    .topic { margin-top: 10px; color: #f6dd92; font-size: 14px; font-weight: 700; }
    .body { padding: 18px; }
    section { padding: 18px 0; border-bottom: 1px dashed var(--line); }
    section:last-child { border-bottom: 0; }
    .section-title { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
    .section-num { background: var(--navy); color: var(--gold); border-radius: 8px; min-width: 34px; padding: 4px 7px; text-align: center; font-weight: 900; font-size: 13px; }
    h2 { margin: 0; color: var(--navy); font-size: 20px; letter-spacing: -.02em; }
    p { margin: 0; }
    ul { margin: 0; padding-left: 19px; }
    li + li { margin-top: 6px; }
    table { width: 100%; border-collapse: collapse; background: var(--panel); margin-top: 10px; font-size: 13px; }
    th { background: var(--navy); color: white; font-weight: 800; }
    th, td { border: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; }
    .conclusion-box { background: var(--gold-soft); border: 1px solid var(--gold); border-left: 5px solid var(--gold); border-radius: 14px; padding: 12px; }
    .avoid-box { background: var(--green-soft); border: 1px solid var(--green-line); border-radius: 14px; padding: 12px; }
    .muted { color: var(--muted); }
    .pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .pill { border: 1px solid var(--line); background: var(--panel); border-radius: 999px; padding: 4px 10px; color: var(--navy); font-size: 12px; font-weight: 700; }
    .sector-card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 14px; margin-top: 12px; }
    .sector-head { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; border-bottom: 1px solid var(--line); padding-bottom: 8px; margin-bottom: 10px; }
    .sector-head strong { color: var(--navy); }
    .rating { color: var(--red); font-weight: 900; white-space: nowrap; }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .mini-title { color: var(--navy); font-size: 13px; font-weight: 900; margin: 10px 0 4px; }
    .footer, .disclaimer { color: var(--muted); text-align: center; font-size: 12px; margin-top: 14px; }
    @media (max-width: 520px) { .grid-2 { grid-template-columns: 1fr; } h1 { font-size: 25px; } .body { padding: 14px; } }
  </style>
</head>
<body>
  <main class="page">
    <article class="paper">
      {% set structured = report.structured_review %}
      <header class="hero">
        <div class="brand">{{ brand_name or "A-Share Review" }}</div>
        <h1>{{ report.title }}</h1>
        <div class="topic">{{ structured.topic if structured else "结构复盘 · 风险分层 · 非投资建议" }}</div>
      </header>

      <div class="body">
        {% if structured %}
          <section>
            <div class="section-title"><span class="section-num">01</span><h2>昨日预判验证</h2></div>
            <div class="conclusion-box">
              <p><strong>昨日预判：</strong>{{ structured.prediction_review.previous_prediction }}</p>
              <p><strong>今日验证：</strong>{{ structured.prediction_review.actual_result }}</p>
              <p><strong>修正判断：</strong>{{ structured.prediction_review.revision }}</p>
            </div>
            <div class="grid-2">
              <div>
                <div class="mini-title">验证正确项</div>
                <ul>{% for item in structured.prediction_review.correct_items %}<li>{{ item }}</li>{% endfor %}</ul>
              </div>
              <div>
                <div class="mini-title">偏差 / 保守项</div>
                <ul>{% for item in structured.prediction_review.missed_items %}<li>{{ item }}</li>{% endfor %}</ul>
              </div>
            </div>
          </section>

          <section>
            <div class="section-title"><span class="section-num">02</span><h2>先给结论 · 明日核心判断</h2></div>
            <div class="conclusion-box"><p>{{ structured.tomorrow_judgement.core_view }}</p></div>
            <table aria-label="明日核心判断">
              <tr><th>最容易继续</th><td>{{ structured.tomorrow_judgement.most_likely_to_continue }}</td></tr>
              <tr><th>最容易分化</th><td>{{ structured.tomorrow_judgement.most_likely_to_diverge }}</td></tr>
              <tr><th>轮动方向</th><td>{{ structured.tomorrow_judgement.rotation_candidates|join("、") }}</td></tr>
              <tr><th>防御方向</th><td>{{ structured.tomorrow_judgement.defensive_candidates|join("、") }}</td></tr>
            </table>
          </section>

          <section>
            <div class="section-title"><span class="section-num">03</span><h2>盘面总览</h2></div>
            <table>
              <tr><th>指数</th><th>收盘</th><th>涨跌幅</th></tr>
              {% for row in structured.market_overview.index_rows %}
                <tr><td>{{ row.name }}</td><td>{{ row.close }}</td><td>{{ row.change }}</td></tr>
              {% endfor %}
            </table>
            <table>
              {% for row in structured.market_overview.emotion_rows %}
                <tr><th>{{ row.label }}</th><td>{{ row.value }}</td></tr>
              {% endfor %}
            </table>
            <div class="pill-row">{% for feature in structured.market_overview.structure_features %}<span class="pill">{{ feature }}</span>{% endfor %}</div>
            <p class="muted">{{ structured.market_overview.capital_flow_summary }}</p>
          </section>

          <section>
            <div class="section-title"><span class="section-num">04</span><h2>板块详细分析</h2></div>
            {% for sector in structured.sector_reviews %}
              <article class="sector-card">
                <div class="sector-head"><strong>{{ sector.headline }}</strong><span class="rating">{{ sector.sustainability|upper }}</span></div>
                <p><strong>当前阶段：</strong>{{ sector.stage }}</p>
                <p><strong>板块逻辑：</strong>{{ sector.logic }}</p>
                <div class="grid-2">
                  <div><div class="mini-title">强势证据</div><ul>{% for item in sector.strengths %}<li>{{ item }}</li>{% endfor %}</ul></div>
                  <div><div class="mini-title">弱势 / 分歧</div><ul>{% for item in sector.weaknesses %}<li>{{ item }}</li>{% endfor %}</ul></div>
                </div>
                <p><strong>下个交易日看法：</strong>{{ sector.next_day_view }}</p>
              </article>
            {% endfor %}
          </section>

          <section>
            <div class="section-title"><span class="section-num">05</span><h2>板块持续性排序</h2></div>
            <table>
              <tr><th>排序</th><th>板块</th><th>持续性</th><th>理由</th></tr>
              {% for item in structured.sustainability_ranking %}
                <tr><td>{{ item.rank }}</td><td>{{ item.sector }}</td><td>{{ item.rating|upper }}</td><td>{{ item.reason }}</td></tr>
              {% endfor %}
            </table>
          </section>

          <section>
            <div class="section-title"><span class="section-num">06</span><h2>去弱留强 / 回避清单</h2></div>
            <div class="avoid-box">
              <div class="mini-title">去弱留强</div>
              <ul>{% for item in structured.action_discipline.focus %}<li>{{ item }}</li>{% endfor %}</ul>
              <div class="mini-title">回避清单</div>
              <ul>{% for item in structured.action_discipline.avoid %}<li>{{ item }}</li>{% endfor %}</ul>
              <p><strong>最终判断：</strong>{{ structured.action_discipline.final_view }}</p>
            </div>
          </section>
        {% else %}
          <section><div class="section-title"><span class="section-num">01</span><h2>先给结论</h2></div><p>{{ report.narrative.conclusion }}</p></section>
          <section><div class="section-title"><span class="section-num">02</span><h2>盘面总览</h2></div><p>{{ report.narrative.overview }}</p></section>
          <section><div class="section-title"><span class="section-num">03</span><h2>强势板块</h2></div>{% for sector in report.sectors %}<p>{{ sector.rank }}. {{ sector.name }} {{ "%+.2f"|format(sector.pct_change) }}%</p>{% endfor %}</section>
        {% endif %}

        {% if brand_footer %}<div class="footer">{{ brand_footer }}</div>{% endif %}
        {% if disclaimer_enabled %}<div class="disclaimer">非投资建议，仅用于复盘研究与信息整理。</div>{% endif %}
      </div>
    </article>
  </main>
</body>
</html>
```

- [ ] **Step 4: Run renderer test**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_mobile_report_renderer_contains_core_sections -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/renderers/templates/mobile_report.html.j2 apps/api/tests/test_report_api.py
git commit -m "feat: render structured review html"
```

---

### Task 5: Add Frontend Types for Structured Review

**Files:**
- Modify: `apps/web/lib/types.ts`

- [ ] **Step 1: Add optional structured review types**

Modify `apps/web/lib/types.ts` before `ReportDTO`:

```ts
export type PredictionReview = {
  previous_prediction: string;
  actual_result: string;
  correct_items: string[];
  missed_items: string[];
  revision: string;
  source: "manual_placeholder" | "previous_report";
};

export type TomorrowJudgement = {
  most_likely_to_continue: string;
  most_likely_to_diverge: string;
  rotation_candidates: string[];
  defensive_candidates: string[];
  core_view: string;
};

export type MarketOverviewTable = {
  index_rows: Array<Record<string, string>>;
  emotion_rows: Array<Record<string, string>>;
  structure_features: string[];
  capital_flow_summary: string;
};

export type StructuredSectorReview = {
  sector: string;
  headline: string;
  stage: string;
  strengths: string[];
  weaknesses: string[];
  logic: string;
  sustainability: "high" | "medium" | "low";
  next_day_view: string;
  watch_items: string[];
  avoid_items: string[];
};

export type SustainabilityRank = {
  rank: number;
  sector: string;
  rating: "high" | "medium" | "low";
  reason: string;
};

export type ActionDiscipline = {
  focus: string[];
  avoid: string[];
  final_view: string;
};

export type StructuredReviewDTO = {
  topic: string;
  prediction_review: PredictionReview;
  tomorrow_judgement: TomorrowJudgement;
  market_overview: MarketOverviewTable;
  sector_reviews: StructuredSectorReview[];
  sustainability_ranking: SustainabilityRank[];
  action_discipline: ActionDiscipline;
};
```

Add to `ReportDTO` after `news`:

```ts
  structured_review?: StructuredReviewDTO | null;
```

- [ ] **Step 2: Run frontend typecheck**

Run:

```bash
corepack pnpm --filter @stock-review/web test
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/web/lib/types.ts
git commit -m "feat: add structured review frontend types"
```

---

### Task 6: Full Verification and HTML Smoke

**Files:**
- No production file changes expected.

- [ ] **Step 1: Run backend checks**

Run:

```bash
cd apps/api
uv run pytest -v
uv run ruff check .
```

Expected: PASS.

- [ ] **Step 2: Run frontend checks**

Run:

```bash
corepack pnpm --filter @stock-review/web test
corepack pnpm --filter @stock-review/web lint
```

Expected: PASS.

- [ ] **Step 3: Generate fake-provider report smoke**

Run:

```bash
cd apps/api
MARKET_PROVIDER=fake NEWS_PROVIDER=fake REPORTS_ROOT=/tmp/stock-review-v02b-smoke uv run python - <<'PY'
from fastapi.testclient import TestClient
from app.config import get_settings
from app.main import app

get_settings.cache_clear()
with TestClient(app) as client:
    response = client.post('/api/reports/close', json={'trade_date': '2026-05-26'})
response.raise_for_status()
payload = response.json()
structured = payload['report']['structured_review']
print(payload['assets']['html'])
print(structured['topic'])
assert structured['prediction_review']['source'] == 'manual_placeholder'
assert structured['tomorrow_judgement']['most_likely_to_continue'] == '机器人'
PY
```

Expected: prints generated HTML path and topic, assertions pass.

- [ ] **Step 4: Inspect generated HTML content**

Run:

```bash
HTML_PATH=$(find /tmp/stock-review-v02b-smoke -name report.html | sort | tail -1)
rg "昨日预判验证|明日核心判断|板块详细分析|持续性排序|去弱留强|回避清单" "$HTML_PATH"
```

Expected: all section names are found.

- [ ] **Step 5: Commit if verification creates no tracked changes**

Run:

```bash
git status --short
```

Expected: no tracked changes. Do not commit generated smoke files.

---

## Self-Review

Spec coverage:

- Six required core modules are represented by `StructuredReviewDTO` and rendered in Task 4.
- `昨日预判验证` uses `manual_placeholder` source in Tasks 1-3.
- HTML visual language moves to 640px, navy/gold, conclusion boxes, avoid boxes, and tables in Task 4.
- Existing API endpoint is preserved; `structured_review` is added inside `report` in Task 3.
- Frontend remains compatible via optional TypeScript types in Task 5.
- Provider diagnostics remain outside `report` and untouched.

Placeholder scan:

- The word `manual_placeholder` is intentional enum data, not an implementation placeholder.
- No `TBD`, `TODO`, or vague “add tests” steps remain.
- Each code-changing task includes concrete code and commands.

Type consistency:

- Backend `StructuredReviewDTO` maps to frontend `StructuredReviewDTO` with snake_case API field names.
- `sustainability` / `rating` values consistently use `high | medium | low`.
- `ReportDTO.structured_review` is optional in frontend and nullable in backend serialization.
