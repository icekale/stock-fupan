# Daily Report Evidence Redesign

Date: 2026-06-01
Status: Approved design

## Goal

Rebuild the daily report generation around verified evidence and explicit judgment rules, using the provided WeChat daily report as the output standard. The redesign should reproduce the report's analytical dimensions without relying on unsupported LLM inference.

The first implementation phase prioritizes quality, traceability, and maintainability over full source automation.

## Decisions

- Use the reference report as an analytical model, not as a brittle template copy.
- Core conclusions, sector ratings, and next-day strategy must be backed by evidence ids.
- Anspire is an evidence candidate search provider, not an authoritative structured data provider.
- The backend supports batch paste plus parse preview for manual and semi-automatic evidence intake.
- The rule layer determines ratings, rankings, and strategy; the LLM only organizes and polishes approved structured content.
- Sector scoring is fixed and internal. The rendered report shows labels and reasons, not raw scores.

## Report Contract

The daily report uses fixed sections aligned with the reference report:

1. `ZERO 今日核心结论`
   - One-sentence summary.
   - Four key signals.
   - Each signal must include `evidence_ids`; otherwise it is downgraded to pending confirmation.

2. `ONE 指数与市场情绪`
   - Index table.
   - Market emotion table.
   - Previous-session comparison.
   - Uses market data providers, not Anspire.

3. `TWO 昨日/周报预判验证`
   - Previous claim.
   - Actual result.
   - Performance.
   - Bias or correction.

4. `THREE 板块深度分析`
   - Catalysts.
   - Capital flow.
   - Limit-up or strength signal.
   - Sustainability.
   - Risks.
   - Rating.
   - Evidence references.

5. `FOUR 资金轮动全景`
   - Industry inflow/outflow.
   - Main directions.
   - Rotation signal.
   - Precise numbers require structured data or verified evidence.

6. `FIVE 板块持续性排序`
   - Ordered by internal score.
   - Rendered as focus, observe, cautious, or avoid.
   - Shows reasons, not raw scores.

7. `SIX 明日操作思路`
   - Focus directions.
   - Observe directions.
   - Avoid directions.
   - Confirmation signals for the next session.
   - Must be derived from evidence-backed ratings and rotation signals.

8. `SEVEN 中期研判`
   - Trend-level analysis only.
   - No unsupported strong prediction.

9. `主要信息来源`
   - Summarizes sources.
   - Does not replace evidence references in the body.

## Architecture

The design adds four layers around the existing report generator:

### Evidence Intake

The backend accepts batch-pasted evidence. Supported first-phase formats:

- JSON array.
- Table-like text that can be parsed into rows.

The intake flow is:

`paste input -> parse preview -> validate -> save as draft/candidate/verified`

Only validated evidence can become `verified`.

### Evidence Candidate Search

Anspire is used to search for candidate evidence. It should support preset tasks such as:

- `证券时报 行业资金`
- `金融界 连续净流出`
- `搜狐财经 英伟达 N1X AI PC 芯片`
- `36氪 黄仁勋 重新发明PC Agent原生电脑`
- `新浪财经 宇树科技 科创板 IPO 过会`
- `快科技 COMPUTEX 2026 全民AI素养 华为徐直军`

Anspire results start as `candidate`. They cannot directly support core conclusions until validated.

### Judgment Engine

The judgment engine reads:

- Market data.
- Review source data.
- Limit-up and strength data.
- Verified evidence.

It outputs:

- Sector ratings.
- Sustainability ranking.
- Capital rotation signals.
- Next-session focus, observe, and avoid lists.

The LLM must not invent or override these decisions.

### Report Contract And Renderer

The generator creates a structured report matching the contract above. The renderer outputs the mobile HTML report with:

- Fixed section order.
- Evidence references on strong claims.
- Evidence-insufficient states.
- Source summary footer.

## Evidence Model

Minimum evidence item:

```json
{
  "id": "ev_20260601_001",
  "trade_date": "2026-06-01",
  "source": "证券时报",
  "title": "煤炭行业今日净流入资金26.55亿元...",
  "url": "https://example.com/article",
  "published_at": "2026-06-01T15:30:00+08:00",
  "category": "capital_flow",
  "claim": "煤炭行业今日净流入资金26.55亿元。",
  "numbers": {
    "industry": "煤炭",
    "net_inflow_yi": 26.55
  },
  "related_sectors": ["煤炭"],
  "confidence": "high",
  "status": "verified"
}
```

Required fields:

- `source`
- `title`
- `url`
- `published_at`
- `category`
- `claim`
- `confidence`

Supported `category` values:

- `capital_flow`
- `catalyst`
- `market_sentiment`
- `limit_up`
- `risk`
- `policy`
- `earnings`

Supported `confidence` values:

- `high`
- `medium`
- `low`

Supported `status` values:

- `candidate`
- `draft`
- `verified`

## Evidence Validation

Validation rules:

- `high` evidence requires a URL, date match to the trade date or previous natural day, and a trusted source or manual confirmation.
- `capital_flow` evidence needs structured numbers to be `high`.
- `capital_flow` evidence without parseable numbers can be at most `medium`.
- Anspire results default to `candidate`.
- Strong report claims require at least one `high` evidence item or multiple `medium` evidence items.
- Low-confidence evidence can only appear as pending confirmation or observation.
- Missing evidence results in an explicit evidence-insufficient state.

## Scoring And Judgment Rules

Sector score is internal and uses five 0-20 point dimensions:

1. Capital flow.
2. Catalyst strength.
3. Market strength.
4. Sustainability.
5. Risk deduction.

Output mapping:

- `80+`: focus.
- `65-79`: observe.
- `50-64`: cautious observe or low-position trial.
- `<50`: avoid or record only.

Hard rules:

- A sector without `high` evidence cannot rank above observe.
- Continuous capital outflow or core-stock divergence must appear in the risk section.
- Next-session strategy must be derived from top-rated sectors and rotation signals.
- If verified capital-flow data is missing, the capital rotation section states the gap instead of fabricating numbers.

## Backend And API

First-phase backend UI:

- Add a `日报证据` entry near the existing report/data-source administration area.
- Provide batch paste.
- Provide parse preview.
- Show validation errors before save.
- Save valid records as `verified`; invalid records remain `draft` or `candidate`.
- Show daily evidence count and missing critical categories.

Proposed API:

- `POST /api/evidence/parse-preview`
- `GET /api/evidence?trade_date=YYYY-MM-DD`
- `POST /api/evidence`
- `POST /api/evidence/anspire-candidates`
- Existing report generation continues through the current report endpoint, but reads verified evidence by `trade_date`.

## Error Handling

- Anspire timeout, API failure, or empty result only affects candidate search.
- Manual evidence remains usable if Anspire is unavailable.
- Invalid evidence stops at preview and cannot become `verified`.
- Failed number extraction downgrades `capital_flow` confidence unless manually corrected.
- Date mismatch downgrades confidence unless manually confirmed.
- LLM output outside the structured judgment contract is rejected or replaced with conservative text.

## Testing

Required tests:

- Evidence parser handles JSON arrays, table-like text, missing fields, and malformed input.
- Evidence validator enforces required fields, category enum, confidence enum, date rules, and capital-flow number rules.
- Judgment engine tests sector scoring, downgrade rules, continuous outflow risk, and missing evidence behavior.
- Report contract tests require evidence ids for core conclusions and strong strategy claims.
- API tests cover parse preview, save, query, and Anspire candidate fallback.
- Snapshot or structural tests verify report section order and key reference-report dimensions.

## Out Of Scope For Phase One

- Full crawler/data warehouse implementation.
- Fully automatic source verification for every Anspire result.
- Complex CMS workflows.
- Raw score display in the report.
- Replacing existing market data providers.

## Success Criteria

- A daily report can be generated with the reference report's major sections.
- Strong claims are traceable to evidence ids.
- Missing evidence produces explicit conservative states.
- Anspire can seed candidate evidence but cannot bypass validation.
- The rule layer controls ratings and strategy.
- The LLM cannot introduce unsupported sector recommendations.
