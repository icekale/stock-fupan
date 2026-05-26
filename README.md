# A 股收盘复盘 v0.1

A 股收盘复盘是一个本地优先的每日复盘工作流。v0.1 使用确定性的假数据提供方生成收盘复盘报告，并提供 FastAPI 后端与 Next.js 前端用于本地查看和验证报告生成链路。

## Backend Dev Startup

```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Backend API runs at `http://localhost:8000`.

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
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 corepack pnpm dev:web
```

Open `http://localhost:3000` after both dev servers are running.

## Docker Compose

The local compose stack builds the API image from `apps/api/Dockerfile` and runs the web app with Node:

```bash
cp .env.example .env
docker compose up --build
```

Then open `http://localhost:3000`.

## v0.1 Scope

- Generate a close-market review through `POST /api/reports/close`.
- Use deterministic fake market, news, and LLM providers.
- Persist report metadata and generated report assets locally.
- Render a mobile-friendly HTML report and expose it through the frontend.
- Support local browser-to-API calls from `http://localhost:3000`.

## Future v0.2/v0.3 Items

- Live market/news data providers.
- Scheduled report generation.
- OCR and image-based evidence ingestion.
- Watchlist import.
- Markdown/PDF export.
- Authentication and multi-user workflows.
