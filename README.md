# A 股收盘复盘 v0.2

A 股收盘复盘是一个本地优先的每日复盘工作流。v0.2 默认接入 AkShare 行情与 Anspire 新闻搜索，并在真实数据不可用时自动回退到确定性 fake provider，前端会展示详细数据源诊断。

## Backend Dev Startup

```bash
cd apps/api
uv sync
uv run playwright install chromium
uv run uvicorn app.main:app --reload --port 8000
```

Backend API runs at `http://localhost:8000`. Playwright Chromium is required for `report.png` export.

## Real Data Providers

v0.2 defaults to real providers with fake fallback:

```dotenv
MARKET_PROVIDER=akshare
NEWS_PROVIDER=anspire
PROVIDER_FALLBACK_ENABLED=true
ANSPIRE_API_KEY=
```

Behavior:

- AkShare is used only for the current date/current close snapshot in v0.2.
- Historical dates fall back to fake data and show a provider diagnostic in the frontend.
- Anspire requires `ANSPIRE_API_KEY`; missing key, API errors, timeouts, and empty results fall back to fake news.
- Provider diagnostics are returned in `provider_status` and saved in `snapshot.json`.

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

v0.3b imports local watchlists and adds a `自选股观察` block to generated HTML reports.

Supported import inputs:

- TongHuaShun-style `.blk` files containing six-digit A-share codes.
- `.csv` files with `代码`/`名称` or `code`/`name` columns.
- Plain text pasted codes.

TickFlow settings:

```dotenv
TICKFLOW_API_KEY=
TICKFLOW_BASE_URL=https://api.tickflow.org
TICKFLOW_PROVIDER=tickflow
WATCHLIST_PROVIDER=local
WATCHLIST_SNAPSHOT_ROOT=./data/watchlists
```

No key mode still works: TickFlow falls back to deterministic fake quotes and writes `provider_status.tickflow` to `snapshot.json`.

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
- OCR and image-based evidence ingestion.
- Watchlist import.
- Reference HTML aligned structured long-report template.
- Markdown/PDF export.
- Authentication and multi-user workflows.
