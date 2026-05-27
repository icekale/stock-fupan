# Admin Dashboard Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local admin dashboard home with sidebar navigation, report generation, report history, HTML/PNG links, and read-only data source status.

**Architecture:** Add a small API status endpoint that exposes sanitized config state, then refactor the Next.js home page into a shell plus focused panels. Keep existing report generation and report preview APIs unchanged.

**Tech Stack:** FastAPI, Pydantic response dictionaries, Next.js client components, TypeScript, Tailwind CSS, existing pytest and TypeScript checks.

---

### Task 1: Backend Config Status API

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Write failing API test**

Add a test that sets provider env vars and calls `/api/config/status`. Assert it includes TickFlow, Anspire, 同花顺, 东方财富, 自选股, OCR and does not include secret key values.

- [ ] **Step 2: Run targeted test to verify failure**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_report_api.py::test_config_status_api_returns_sanitized_provider_state -q`
Expected: FAIL because endpoint does not exist.

- [ ] **Step 3: Implement endpoint**

Add `@app.get("/api/config/status")` in `apps/api/app/main.py`. Build status items from `get_settings()` without returning key values.

- [ ] **Step 4: Run targeted test to verify pass**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_report_api.py::test_config_status_api_returns_sanitized_provider_state -q`
Expected: PASS.

### Task 2: Frontend API Types

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`

- [ ] **Step 1: Add TypeScript response types**

Define `ConfigStatusState`, `ConfigStatusItem`, and `ConfigStatusResponse`.

- [ ] **Step 2: Add API client**

Add `getConfigStatus()` that fetches `/api/config/status` and throws readable errors on non-200 responses.

- [ ] **Step 3: Run type check**

Run: `corepack pnpm --filter @stock-review/web test`
Expected: PASS.

### Task 3: Dashboard Components

**Files:**
- Create: `apps/web/components/AdminShell.tsx`
- Create: `apps/web/components/DataSourceStatusPanel.tsx`

- [ ] **Step 1: Create `AdminShell`**

Implement a full-width layout with left nav and content slot. Use plain props and Tailwind classes only.

- [ ] **Step 2: Create `DataSourceStatusPanel`**

Render status cards with name, role, detail, and a quiet colored status dot. Do not expose secrets.

- [ ] **Step 3: Run type check**

Run: `corepack pnpm --filter @stock-review/web test`
Expected: PASS.

### Task 4: Refactor Home Page

**Files:**
- Modify: `apps/web/app/page.tsx`

- [ ] **Step 1: Load config status**

Add state for config status and fetch it on mount alongside report history.

- [ ] **Step 2: Recompose page**

Use `AdminShell`; put report generation, history, data source status, watchlist import, and preview into clear dashboard sections.

- [ ] **Step 3: Preserve existing behavior**

Ensure report generation still calls `createReport(tradeDate, reportKind)`, refreshes history, and displays preview.

- [ ] **Step 4: Run type check**

Run: `corepack pnpm --filter @stock-review/web test`
Expected: PASS.

### Task 5: Full Validation and Browser Check

**Files:**
- No production code unless validation reveals a defect.

- [ ] **Step 1: Run backend validation**

Run: `cd apps/api && .venv/bin/python -m ruff check app tests && .venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 2: Run frontend validation**

Run: `corepack pnpm --filter @stock-review/web test`
Expected: PASS.

- [ ] **Step 3: Browser verify dashboard**

Start API and web if needed. Open the web app and verify visible text includes `A 股复盘后台`, `报告生成`, `历史报告`, and `数据源状态`.
