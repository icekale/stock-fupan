# A 股收盘复盘 v0.3e

A 股收盘复盘是一个本地优先的每日复盘工作流。v0.3e 优先使用 TickFlow 行情、Anspire 新闻搜索和 TickFlow 自选股行情；生产报告默认不允许使用 fake 数据。

## Backend Dev Startup

```bash
cd apps/api
uv sync
uv run playwright install chromium
uv run uvicorn app.main:app --reload --port 8000
```

Backend API runs at `http://localhost:8000`. Playwright Chromium is required for `report.png` export.

## Daily Report Command

Generate a local close-market report from the repository root:

```bash
make report DATE=2026-05-26
```

The command reads the same local `.env` provider settings as the API, writes assets under `REPORTS_ROOT`, and prints the generated `report.html` and `snapshot.json` paths. It does not print API keys. If report validation fails, the command exits non-zero and prints the validation errors.

For a production-grade local run, load your private provider keys from your local API `.env` and disable fake fallback:

```bash
set -a
source apps/api/.env
set +a
MARKET_PROVIDER=tickflow \
NEWS_PROVIDER=anspire \
TICKFLOW_PROVIDER=tickflow \
PROVIDER_FALLBACK_ENABLED=false \
REVIEW_SOURCES_ENABLED=true \
make report DATE=2026-05-26
```

Preview the latest generated HTML by serving the version directory printed by the command:

```bash
cd reports/2026-05-26/close/<printed-version>
python3 -m http.server 8884 --bind 127.0.0.1
```

Then open `http://127.0.0.1:8884/report.html`. The current production HTML renderer uses the supplied reference-report visual system with a wider desktop layout, top summary board, three-part sector blocks, unified tables/cards, and a card-based source area.

Generated report assets live under `reports/` and are git-ignored. During UI iteration, keep the latest version and remove older same-day versions if they are no longer needed:

```bash
find reports/2026-05-26/close -maxdepth 1 -type d -name 'v*' ! -name '<latest-version>' -exec rm -rf {} +
```

## Real Data Providers

v0.3e defaults to TickFlow-first real data:

```dotenv
MARKET_PROVIDER=tickflow
NEWS_PROVIDER=anspire
TICKFLOW_API_KEY=
ANSPIRE_API_KEY=
```

Behavior:

- TickFlow is the preferred market data source for generated reports.
- AkShare remains available as a real provider path, but production reports should fail visibly rather than emit fake market data.
- Anspire requires `ANSPIRE_API_KEY`; missing key, API errors, timeouts, and empty results are reflected in provider diagnostics.
- Provider diagnostics are returned in `provider_status` and saved in `snapshot.json`.

Production controls:

```dotenv
APP_ENV=production
PRODUCTION_ALLOW_FAKE_PROVIDERS=false
PROVIDER_FALLBACK_ENABLED=false
OCR_FALLBACK_ENABLED=false
```

Set `MARKET_PROVIDER=fake`, `NEWS_PROVIDER=fake`, or `TICKFLOW_PROVIDER=fake` only for local demos/tests, never for production-grade reports.

## LLM Structured Review

v0.3a can use an OpenAI-compatible LLM to generate `structured_review` content for the long-form HTML report:

```dotenv
LLM_PROVIDER=openai
STRUCTURED_REVIEW_PROVIDER=llm
STRUCTURED_REVIEW_FALLBACK_ENABLED=true
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
```

Behavior:

- Default local mode remains `LLM_PROVIDER=fake` and `STRUCTURED_REVIEW_PROVIDER=rule`.
- LLM output is parsed into `StructuredReviewDTO`; invalid JSON or schema failures fall back to the deterministic rule builder when fallback is enabled.
- `snapshot.json` includes `structured_review_status` so the frontend and generated assets can explain whether the review came from rules, LLM, or fallback.
- API keys must be supplied through local environment variables only and are never written to generated assets.

## Watchlist and TickFlow Enrichment

v0.3b imports local watchlists. v0.3e keeps the `自选股观察` report block behind an explicit switch and disables it by default.

Supported import inputs:

- TongHuaShun-style `.blk` files containing six-digit A-share codes.
- `.csv` files with `代码`/`名称` or `code`/`name` columns.
- Plain text pasted codes.

TickFlow settings:

```dotenv
TICKFLOW_API_KEY=
TICKFLOW_BASE_URL=https://api.tickflow.org
TICKFLOW_PROVIDER=tickflow
REPORT_WATCHLIST_ENABLED=false
WATCHLIST_PROVIDER=local
WATCHLIST_SNAPSHOT_ROOT=./data/watchlists
```

Set `REPORT_WATCHLIST_ENABLED=true` to include `自选股观察` and call TickFlow for imported watchlist quotes. When disabled, report generation skips watchlist loading and TickFlow watchlist enrichment.

## OCR Watchlist Import

v0.3c supports screenshot-based watchlist import. Uploading an image creates an OCR preview first; the latest SQLite watchlist is updated only after clicking confirm.

```dotenv
OCR_PROVIDER=fake
OCR_FALLBACK_ENABLED=true
OCR_MODEL=gpt-4.1-mini
```

Behavior:

- Supported image uploads: PNG, JPEG, and WebP.
- `OCR_PROVIDER=fake` returns deterministic local data for offline development and tests.
- `OCR_PROVIDER=openai` uses the existing OpenAI-compatible `OPENAI_API_KEY` and `OPENAI_BASE_URL` settings with `OCR_MODEL`.
- OCR preview artifacts are stored under `WATCHLIST_SNAPSHOT_ROOT/ocr`.
- Confirmed OCR imports reuse the normal watchlist import path and appear in generated HTML reports through `自选股观察`.
- API keys are read only from local environment variables and are not written to snapshots or generated report assets.

## Reference HTML Alignment

v0.3d expands the structured review schema and generated `report.html` toward the supplied long-form reference HTML.

Added report modules:

- `盘后 / 隔夜消息梳理`
- `资金轮动路径分析`
- `明日可介入标的与仓位建议`
- `最实战的结论`
- `上证指数中期走势研判`

The HTML remains the primary artifact. Provider data, watchlists, TickFlow enrichment, and OCR imports all feed the same structured report pipeline; the renderer turns that pipeline into the final mobile-friendly HTML/PNG.

## Frontend Dev Startup

From the repository root:

```bash
corepack enable
pnpm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 pnpm dev:web
```

If the `pnpm` shim is unavailable even after enabling Corepack, run the same commands through Corepack:

```bash
corepack pnpm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 corepack pnpm --filter @stock-review/web dev
```

Open `http://localhost:3000` after both dev servers are running.

## Docker Compose

The local compose stack builds the API image from `apps/api/Dockerfile` and runs the web app with Node:

```bash
cp .env.example .env
docker compose up --build
```

Then open `http://localhost:3000`.

## v0.2 Scope

- Generate a close-market review through `POST /api/reports/close`.
- Use AkShare market data and Anspire news search by default.
- Fall back to deterministic fake market/news providers with visible diagnostics.
- Persist report metadata and generated report assets locally.
- Render a mobile-friendly HTML/PNG report and expose it through the frontend.
- Support local browser-to-API calls from `http://localhost:3000`.

## Future v0.3 Items

- Scheduled report generation.
- Real OCR quality tuning against more broker/watchlist screenshots.
- Watchlist sector/tag grouping.
- Markdown/PDF export.
- Authentication and multi-user workflows.
