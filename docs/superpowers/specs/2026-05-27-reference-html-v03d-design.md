# Reference HTML Alignment v0.3d Design

## Goal

Upgrade the generated `report.html` from a functional MVP long-form report into a more complete daily review artifact aligned with the user's reference HTML file at `/Users/kale/Downloads/2026-05-26_structured_review.html`.

The HTML is the product's primary output. v0.3d treats the report as a first-class artifact: content structure, visual hierarchy, mobile screenshot stability, and section completeness matter more than adding another data source.

## Current Gap

The current template already renders a structured report with:

- prediction review
- tomorrow judgement
- market overview
- watchlist observation
- sector reviews
- sustainability ranking
- action discipline

The reference HTML contains additional high-value modules and a stronger editorial rhythm:

- `盘后 / 隔夜消息梳理`
- `资金轮动路径分析`
- `明日可介入标的与仓位建议`
- `最实战的结论`
- `上证指数中期走势研判`
- richer card/table density and clearer section pacing

v0.3d should close this gap without requiring live provider changes.

## Scope

### In Scope

- Extend `StructuredReviewDTO` with deterministic, renderable sections for:
  - after-hours / overnight news summary
  - capital rotation path
  - next-day opportunity plan
  - practical final conclusion
  - index mid-term outlook
- Update rule-based structured review builder so fake/local mode always produces complete sections.
- Update LLM structured-review parsing/schema expectations so OpenAI-compatible mode can return the same fields.
- Refactor `mobile_report.html.j2` with a medium restructure:
  - stronger cover/header hierarchy
  - table/card treatments closer to the reference HTML
  - added reference sections
  - stable 640px mobile-long-image layout
  - controlled section numbering and visual rhythm
- Add renderer tests that assert all reference-aligned section titles appear in generated HTML.
- Add smoke validation that generated HTML includes the expanded modules and still renders PNG.
- Update docs to call v0.3d the reference-HTML alignment phase.

### Out of Scope

- Pixel-perfect cloning of the reference HTML.
- New real data providers.
- Scheduler, task queue, auth, multi-user workflow.
- PDF/Markdown export.
- Manual editor for every report section.
- Investment advice wording. Sections must remain framed as observation, risk layering, and review notes.

## Visual Direction

Rewrite level: medium restructure.

Visual thesis: `calm institutional long-form review`.

The output should feel like a serious, exportable market review article rather than a dashboard screenshot. It should use restrained navy/gold accents, decisive section headers, readable tables, and compact evidence cards. Visual quality should come from hierarchy, spacing, and table/card precision—not decorative glow or busy effects.

Design principles:

- Keep `640px` mobile long-image width as the main target.
- Use a strong title block with trade date, report type, and topic.
- Make each section scannable with number, title, and a short lead where useful.
- Prefer tables for comparison-heavy content and cards for interpretive narrative.
- Keep default surfaces quiet; reserve gold highlights for conclusion/priority blocks.
- Use fewer but better container styles.
- Avoid embedding source screenshots or OCR images into the report.

## Data Model Design

Add these schema units under `app/schemas/structured_review.py`:

### AfterHoursNewsSummary

Fields:

- `us_market_mapping: list[str]`
- `domestic_catalysts: list[str]`
- `risk_notes: list[str]`

Purpose: render the reference-style `盘后 / 隔夜消息梳理` section. Rule builder can derive from top news titles and sector names; fake mode can use deterministic placeholders based on existing report facts.

### CapitalRotationPath

Fields:

- `actual_path: list[str]`
- `key_finding: str`
- `next_path_watch: list[str]`

Purpose: render `资金轮动路径分析`. Rule builder derives a simple path from ranked sectors and market state tags.

### NextDayOpportunityPlan

Fields:

- `focus_candidates: list[str]`
- `position_discipline: list[str]`
- `trigger_conditions: list[str]`
- `avoid_conditions: list[str]`

Purpose: render `明日可介入标的与仓位建议` while avoiding direct buy/sell language. Wording should use observation conditions and discipline.

### PracticalConclusion

Fields:

- `headline: str`
- `bullet_points: list[str]`

Purpose: render `最实战的结论` as a compact final action frame.

### IndexMidTermOutlook

Fields:

- `year_review: list[str]`
- `current_position: str`
- `scenario_table: list[dict[str, str]]`

Purpose: render `上证指数中期走势研判`. Rule builder can create conservative, deterministic scenarios from index direction and breadth.

## Builder Design

The deterministic builder should remain the reliable fallback. It will derive the new sections from existing `ReportDTO` facts:

- Top sectors become the capital rotation path and focus candidates.
- Weak or low-sustainability sectors become avoid conditions.
- Existing news titles become after-hours/domestic catalysts when available.
- Index snapshots and breadth become index mid-term outlook scenarios.
- Existing action discipline becomes the practical conclusion.

If input facts are sparse, the builder still returns complete but cautious text. No field should be empty in normal fake/local generation.

## LLM Design

Update the structured review prompt and parser expectations so LLM output must include the new fields. Existing fallback behavior remains unchanged:

- valid LLM JSON -> render expanded report
- invalid JSON/schema -> fall back to deterministic builder when fallback is enabled
- fallback status still goes to `snapshot.json`

The prompt must explicitly forbid invented precise numbers and direct trading advice.

## HTML Design

The expanded report order:

1. 昨日预判验证
2. 先给结论
3. 盘面总览
4. 各板块详细分析
5. 盘后 / 隔夜消息梳理
6. 板块持续性排序
7. 资金轮动路径分析
8. 明日可介入标的与仓位建议
9. 自选股观察
10. 去弱留强排序
11. 最实战的结论
12. 上证指数中期走势研判

`自选股观察` remains important but should move after broader market/plan sections so the report reads like a full market review first, then a personalized watchlist layer.

The template should preserve a legacy fallback branch for reports without `structured_review`, but v0.3d acceptance focuses on structured reports.

## Error Handling

- Missing new fields in LLM output triggers schema validation failure and existing fallback behavior.
- Empty derived lists should be replaced by cautious default observations in the builder.
- HTML should not crash if optional watchlist observation is absent.
- Renderer tests should catch missing section titles.

## Testing Plan

- Schema serialization test covers all new structured review fields.
- Builder test asserts new sections are populated from fake report facts.
- LLM provider test updates valid JSON fixture to include new fields.
- Renderer test asserts generated HTML includes all 12 reference-aligned section titles.
- Report generator test asserts `report_dto.json` and `snapshot.json` include the new fields.
- Smoke test generates a report and asserts `report.html` exists, contains key titles, and PNG export still runs through the existing fake Playwright stub in tests.
- Full backend and frontend checks remain required.

## Acceptance Criteria

- Generated structured `report.html` contains all expanded reference-aligned sections.
- HTML first read feels closer to the supplied reference file: serious long-form report, not dashboard summary.
- Rule fallback produces complete new sections without requiring real providers.
- LLM structured review mode supports the expanded schema and still falls back safely.
- Watchlist/OCR/TickFlow enhancements continue to flow into the report without changing their APIs.
- Existing API response shape remains backward compatible except for added nested structured-review fields.
- Tests and lint pass on `main` after merge.
- No real API keys or secret-like values are written to repo files or generated assets.
