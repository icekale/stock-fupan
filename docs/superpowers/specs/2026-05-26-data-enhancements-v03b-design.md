# v0.3b Data Enhancements Design

## 1. Context

v0.3a has a stable local report pipeline: AkShare market data, Anspire news, LLM/rule structured review generation, local assets, and a long-form HTML report. The next phase should improve the report's practical value without destabilizing the core HTML output.

This phase adds two data enhancements:

1. Import watchlists exported from TongHuaShun or copied from user text.
2. Use TickFlow to enrich watchlist stocks with real-time quotes and instrument metadata.

OCR remains out of scope for this phase. It should be designed later as a separate ingestion source that produces the same watchlist import payload.

## 2. Goals

- Import watchlist stocks from common local formats: `.blk`, `.csv`, `.txt`, and pasted raw text.
- Normalize stock codes into a single internal A-share symbol format: `600000.SH`, `000001.SZ`, `688001.SH`, `300001.SZ`, `430001.BJ`.
- Persist structured watchlist data in SQLite and save import source snapshots under the local reports/data directory.
- Add a TickFlow provider for batch quote and instrument metadata lookup on watchlist stocks.
- Add a watchlist observation block to generated reports and the HTML template.
- Mark sector reviews when imported watchlist stocks are relevant to that sector.
- Preserve offline-first behavior: no key or provider failure must not block report generation.
- Add provider diagnostics for TickFlow, without writing API keys into generated assets or docs.

## 3. Non-Goals

- Do not replace AkShare as the broad market and sector source.
- Do not build a full watchlist editing UI in this phase.
- Do not implement OCR recognition in this phase.
- Do not store real API keys in source, tests, docs, snapshots, or generated assets.
- Do not infer sector membership from TickFlow if the API response does not provide it. Sector tagging remains best-effort from existing report sectors and imported stock names/codes.

## 4. Architecture

The phase introduces a small watchlist subsystem beside the existing provider/report pipeline.

```text
apps/api/app/watchlist/
  parser.py       # Parse .blk/.csv/.txt/raw text into normalized stock symbols
  storage.py      # SQLite persistence helpers and file snapshot writing
  service.py      # Import orchestration and latest watchlist retrieval

apps/api/app/providers/tickflow.py
  TickFlowProvider        # HTTP adapter for /v1/quotes and /v1/instruments
  FakeTickFlowProvider    # Deterministic offline data for tests/dev
  FallbackTickFlowProvider

apps/api/app/services/report_generator.py
  loads latest watchlist
  enriches watchlist through TickFlow provider
  attaches WatchlistObservation to ReportDTO
```

The existing API endpoint still returns a generated report. The frontend keeps its current flow, but the report payload gains an optional `watchlist_observation` object and `provider_status.tickflow` diagnostics.

## 5. Watchlist Parsing

### Input formats

The parser accepts:

- `.blk`: TongHuaShun style lines, commonly containing plain six-digit stock codes or prefixed variants.
- `.csv`: UTF-8/GBK text with columns such as `code`, `代码`, `symbol`, `名称`, `name`.
- `.txt`: any text containing A-share stock codes.
- raw pasted text: same extraction behavior as `.txt`.

### Normalization rules

- Six-digit codes beginning with `6` or `688` map to `.SH`.
- Six-digit codes beginning with `0` or `3` map to `.SZ`.
- Six-digit codes beginning with `4` or `8` map to `.BJ`.
- Existing suffixes `.SH`, `.SZ`, `.BJ`, `SH`, `SZ`, `BJ`, `sh`, `sz`, `bj` are accepted and normalized uppercase.
- Duplicates are removed while preserving first-seen order.
- Invalid tokens are returned as parse warnings, not exceptions, unless no valid stocks are found.

### Parser output

```python
class WatchlistItem(BaseModel):
    symbol: str
    code: str
    exchange: Literal["SH", "SZ", "BJ"]
    name: str | None = None
    source: str = "import"

class WatchlistParseResult(BaseModel):
    items: list[WatchlistItem]
    warnings: list[str] = []
```

## 6. Persistence

SQLite gets two tables:

- `watchlist_imports`: import id, source type, source filename, snapshot path, created time, item count.
- `watchlist_items`: import id, symbol, code, exchange, name, display order.

Only the latest import is used by report generation in v0.3b.

Source snapshots are saved under:

```text
data/watchlists/imports/<timestamp>-<safe-filename>
data/watchlists/imports/<timestamp>-parsed.json
```

The app should create these directories when needed. If snapshot writing fails, the import should fail before database rows are committed, so the DB and files stay consistent.

## 7. API Surface

Add two endpoints:

```text
POST /api/watchlists/import-text
POST /api/watchlists/import-file
GET  /api/watchlists/latest
```

`import-text` accepts JSON:

```json
{
  "content": "600000\n000001\n300750",
  "source_name": "manual.txt"
}
```

`import-file` accepts multipart upload with a local file. It parses by filename extension and content.

Both import endpoints return:

```json
{
  "import_id": 1,
  "item_count": 3,
  "items": [
    {"symbol": "600000.SH", "code": "600000", "exchange": "SH", "name": null, "source": "import"}
  ],
  "warnings": []
}
```

`latest` returns the latest import with its items. If no import exists, it returns `items=[]` and `import_id=null`.

## 8. TickFlow Provider

TickFlow docs show:

- Base URL: `https://api.tickflow.org`
- Auth header: `x-api-key`
- Real-time quote endpoint: `/v1/quotes`
- Instrument metadata endpoint: `/v1/instruments`
- Free base URL `https://free-api.tickflow.org` does not include real-time quotes.

Add settings:

```dotenv
TICKFLOW_API_KEY=
TICKFLOW_BASE_URL=https://api.tickflow.org
TICKFLOW_PROVIDER=tickflow
WATCHLIST_PROVIDER=local
WATCHLIST_SNAPSHOT_ROOT=./data/watchlists
```

Provider behavior:

- `FakeTickFlowProvider` returns deterministic quote/metadata for known test symbols.
- `TickFlowProvider` uses injected `httpx.Client` for tests and owned client for runtime.
- Missing key raises a provider fallback error with reason `TICKFLOW_API_KEY 未配置`.
- Request errors, non-2xx responses, empty results, and malformed payloads are sanitized and never include the key.
- `FallbackTickFlowProvider` returns fake quotes when fallback is enabled; otherwise it raises.

The provider does not need to support the entire TickFlow response surface. It maps only fields needed by the report:

```python
class WatchlistQuote(BaseModel):
    symbol: str
    name: str | None = None
    last_price: float | None = None
    pct_change: float | None = None
    turnover_cny: float | None = None
    volume: float | None = None
    quote_time: str | None = None
```

## 9. ReportDTO Additions

Add optional watchlist observation models:

```python
class WatchlistMatch(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    pct_change: float | None = None
    reason: str

class WatchlistObservation(BaseModel):
    import_id: int | None = None
    total_count: int = 0
    quote_count: int = 0
    strongest: list[WatchlistMatch] = []
    weakest: list[WatchlistMatch] = []
    sector_matches: list[WatchlistMatch] = []
    notes: list[str] = []
```

`ReportDTO.watchlist_observation` is optional. Existing reports and tests remain compatible.

## 10. Report Generation Flow

`ReportGenerator.generate_close_report()` gains two optional dependencies:

- `watchlist_service`
- `tickflow_provider`

Flow:

1. Generate market/news/narrative/structured review exactly as v0.3a does.
2. Load the latest local watchlist.
3. If the watchlist is empty, attach `watchlist_observation` with `total_count=0` and note `未导入自选股`.
4. If stocks exist, call TickFlow provider for batch quotes and metadata.
5. Build strongest/weakest lists by `pct_change` when available.
6. Build sector matches by comparing watchlist stock names/codes against existing sector top stocks and available names. If no reliable match exists, leave `sector_matches=[]` and add a note.
7. Add `provider_status.tickflow` and write it to `snapshot.json`.
8. Render the HTML with a new “自选股观察” section.

## 11. HTML Requirements

The HTML report is the core product output. v0.3b must keep all existing long-form structured sections and add one new section after “盘面总览” or before “板块详细分析”:

- Title: `自选股观察`
- Show import count and quote count.
- Show strongest watchlist stocks with symbol, name, pct change, and one-line reason.
- Show weakest/risk watchlist stocks.
- Show matched sectors if available.
- If no watchlist is imported, show a quiet placeholder instead of hiding the section.
- If TickFlow falls back or fails, show diagnostic text in data-source diagnostics, not inside the main prose unless useful.

The rendered HTML must remain mobile-first and screenshot-friendly.

## 12. Frontend Requirements

Add a small watchlist import panel to the current web app:

- Textarea import for pasted codes.
- File upload for `.blk`, `.csv`, `.txt`.
- Latest watchlist preview with normalized symbols.
- Report generation should not require a watchlist.

No advanced editing, deletion, or manual rename UI in this phase.

## 13. Testing Strategy

Backend tests:

- Parser normalizes SH/SZ/BJ codes from `.blk`, `.csv`, `.txt`, raw text.
- Parser preserves order and removes duplicates.
- Parser reports invalid tokens as warnings.
- Watchlist import writes SQLite rows and snapshot files.
- API import endpoints return parsed items.
- TickFlow provider maps injected fake HTTP responses to `WatchlistQuote`.
- TickFlow provider missing key and request errors are sanitized.
- Fallback provider returns fake data and status.
- Report generator writes `watchlist_observation` and `provider_status.tickflow` to `snapshot.json`.
- HTML contains `自选股观察`.

Frontend tests:

- Type definitions include watchlist fields and tickflow provider status.
- Watchlist import panel submits text import and displays normalized symbols.
- Report preview renders watchlist observation when present.

Smoke checks:

- No `TICKFLOW_API_KEY` still generates a report with fallback status.
- Imported text watchlist appears in generated HTML.
- Full backend and frontend checks pass.

## 14. Security and Secret Handling

- `TICKFLOW_API_KEY` is read only from environment variables.
- API keys are not written to snapshots, `llm_calls.json`, logs, tests, docs, or generated HTML.
- Error messages include provider name and error class/reason only, not request headers or full URLs with secrets.
- Uploaded watchlist files are stored as local user data and are not sent to LLM prompts by default.

## 15. Rollout Plan

Implement in small commits:

1. Watchlist parser and tests.
2. Watchlist DB/storage/API import endpoints.
3. TickFlow provider and fallback tests.
4. ReportDTO/watchlist observation builder.
5. Report generator + HTML integration.
6. Frontend import panel and preview rendering.
7. Docs, `.env.example`, full verification, and local merge.

## 16. Open Decisions Resolved

- User selected v0.3b scope: TongHuaShun watchlist import plus TickFlow enhancement.
- User selected broad compatibility for TongHuaShun input format.
- TickFlow docs URL is `https://docs.tickflow.org/zh-Hans`; the implementation will use documented base URL and endpoints but tests will rely on injected clients, not live keys.
- OCR is deferred.
