# Weekly Report MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real-data weekly report path that produces HTML/PNG/PDF assets and appears in the admin report flow.

**Architecture:** Extend the existing report kind and asset pipeline with `weekly`, add a focused weekly generator that uses TickFlow historical K-line APIs, and render a compact HTML report with explicit data coverage. Keep fake fallback disabled for weekly analysis and label missing source limitations in the report.

**Tech Stack:** FastAPI, Pydantic, pytest, Next.js admin UI, TickFlow HTTP API.

---

### Task 1: Report Kind and Naming

**Files:**
- Modify: `apps/api/app/schemas/report.py`
- Modify: `apps/api/app/db/models.py`
- Modify: `apps/api/app/services/assets.py`
- Modify: `apps/web/lib/types.ts`
- Test: `apps/api/tests/test_assets.py`

- [ ] Add failing tests that `weekly` maps to `周报复盘` and named copies use the label.
- [ ] Run `cd apps/api && uv run pytest tests/test_assets.py -q` and verify failure.
- [ ] Add `weekly` to enum/model/types and `report_kind_label`.
- [ ] Re-run asset tests.

### Task 2: Weekly Data Fetcher and HTML Renderer

**Files:**
- Create: `apps/api/app/services/weekly_report_generator.py`
- Test: `apps/api/tests/test_weekly_report_generator.py`

- [ ] Add tests with fake TickFlow/News clients for weekly summary, no fake provider content, and generated HTML sections.
- [ ] Run test and verify failure.
- [ ] Implement a small weekly generator with dependency-injected clients.
- [ ] Re-run weekly tests.

### Task 3: API and CLI Integration

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/cli/generate_report.py`
- Test: `apps/api/tests/test_report_api.py`
- Test: `apps/api/tests/test_generate_report_cli.py`

- [ ] Add tests for `/api/reports/weekly` and CLI `--kind weekly`.
- [ ] Run targeted tests and verify failure.
- [ ] Wire weekly generator into API/CLI metadata persistence.
- [ ] Re-run targeted tests.

### Task 4: Admin UI Integration

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/app/page.tsx`

- [ ] Add weekly button and label text.
- [ ] Run existing web tests for report kind / hydration if available.

### Task 5: Generate Sample Report

**Files:**
- Output under configured `reports_root`.

- [ ] Run weekly generation for `2026-05-25` to `2026-05-29`.
- [ ] Verify `report.html`, `report.png`, `report.pdf`, and named copies exist.
- [ ] Open or serve sample report URL for review.
