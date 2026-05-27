# TickFlow Frontline Stocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real TickFlow front-row stocks to strong sectors in generated reports.

**Architecture:** `TickFlowMarketDataProvider` computes and stores sector-to-stock mappings while building the market snapshot. `ReportGenerator` reads the optional mapping through a small provider method and merges those stocks into `SectorCandidate.top_stocks`.

**Tech Stack:** Python 3.12, pytest, existing TickFlow HTTP provider, existing ReportDTO schema.

---

### Task 1: TickFlow Provider Frontline Stocks

**Files:**
- Modify: `apps/api/app/providers/tickflow.py`
- Test: `apps/api/tests/test_tickflow_provider.py`

- [ ] Write a failing test showing `TickFlowMarketDataProvider.get_sector_frontline_stocks("PCB")` returns 生益电子 and 沪电股份 after `get_close_snapshot()` groups strong stocks.
- [ ] Run `cd apps/api && PYTHONPATH=. .venv/bin/python -m pytest tests/test_tickflow_provider.py::test_tickflow_market_provider_exposes_frontline_stocks_for_ranked_sectors -q` and confirm failure.
- [ ] Add a private `self._sector_frontline_stocks` mapping and populate it from sector groups.
- [ ] Add public method `get_sector_frontline_stocks(sector_name: str) -> list[WatchlistQuote]`.
- [ ] Run the focused test and confirm it passes.

### Task 2: Report Generator Integration

**Files:**
- Modify: `apps/api/app/services/report_generator.py`
- Test: `apps/api/tests/test_report_api.py`

- [ ] Write a failing test using a fake market provider with `get_sector_frontline_stocks()` so the generated report includes TickFlow front-row stocks.
- [ ] Run the focused test and confirm failure.
- [ ] Pass TickFlow stocks into `_build_sector_candidate()` and merge them before review-source stocks.
- [ ] Add helper `_tickflow_quote_to_candidate()` with tag `TickFlow前排`.
- [ ] Run the focused test and confirm it passes.

### Task 3: Validation and Smoke

**Files:**
- No new production files.

- [ ] Run `cd apps/api && PYTHONPATH=. .venv/bin/python -m pytest -q`.
- [ ] Run `cd apps/api && PYTHONPATH=. .venv/bin/python -m ruff check app tests`.
- [ ] Run `make report DATE=2026-05-26` with real TickFlow env and inspect the generated snapshot for front-row stocks.
