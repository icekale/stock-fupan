# No-Fake Market Data and Watchlist Toggle v0.3e Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent production reports from using fake data and make the `自选股观察` module disabled by default behind an explicit switch.

**Architecture:** Add settings that distinguish explicit local fake mode from production-grade generation. Thread `report_watchlist_enabled` into report generation so disabled watchlists do not call the watchlist service or TickFlow and do not render in HTML. Keep existing fake providers for tests and local demos, but reject fake provider/fake fallback in production unless explicitly allowed.

**Tech Stack:** FastAPI backend, Pydantic settings, provider factory, pytest, Jinja2 report template, Ruff.

---

## File Structure

- Modify `apps/api/app/config.py`: add `report_watchlist_enabled` and `production_allow_fake_providers` settings.
- Modify `apps/api/app/providers/factory.py`: reject fake providers and fake fallback chains in production by default.
- Modify `apps/api/app/services/report_generator.py`: add `watchlist_enabled` constructor argument and skip watchlist/TickFlow work when disabled.
- Modify `apps/api/app/main.py`: pass `settings.report_watchlist_enabled` into `ReportGenerator`.
- Modify `apps/api/app/renderers/templates/mobile_report.html.j2`: hide `自选股观察` when no observation exists and keep section numbering coherent.
- Modify `.env.example` and `README.md`: document defaults and production no-fake behavior.
- Modify tests in `apps/api/tests/test_real_providers.py` and `apps/api/tests/test_report_api.py`.

## Task 1: Add settings and production provider guard

- [ ] Write failing tests in `apps/api/tests/test_real_providers.py`:
  - `test_settings_defaults_disable_watchlist_and_production_fake_allowance`
  - `test_provider_factory_rejects_fake_market_provider_in_production`
  - `test_provider_factory_rejects_fake_fallback_in_production`
- [ ] Run `cd apps/api && uv run pytest tests/test_real_providers.py::test_settings_defaults_disable_watchlist_and_production_fake_allowance tests/test_real_providers.py::test_provider_factory_rejects_fake_market_provider_in_production tests/test_real_providers.py::test_provider_factory_rejects_fake_fallback_in_production -q` and verify failure.
- [ ] Add settings to `apps/api/app/config.py`.
- [ ] Add provider guard helpers to `apps/api/app/providers/factory.py`.
- [ ] Run the same tests and verify pass.
- [ ] Commit `feat: guard production fake providers`.

## Task 2: Add watchlist report switch

- [ ] Write failing tests in `apps/api/tests/test_report_api.py`:
  - default generator with watchlist/tickflow dependencies does not call either and status reason is `自选股模块未开启`.
  - default structured HTML omits `自选股观察`.
  - enabling watchlist keeps existing TickFlow/watchlist rendering behavior.
- [ ] Run targeted tests and verify failure.
- [ ] Add `watchlist_enabled` to `ReportGenerator` defaulting to `False`.
- [ ] Pass `settings.report_watchlist_enabled` from `apps/api/app/main.py`.
- [ ] Update template to render watchlist section only when `report.watchlist_observation` exists. Use a Jinja namespace counter so visible section numbers remain contiguous.
- [ ] Run targeted tests and verify pass.
- [ ] Commit `feat: add watchlist report toggle`.

## Task 3: Document configuration

- [ ] Update `.env.example` with `REPORT_WATCHLIST_ENABLED=false` and `PRODUCTION_ALLOW_FAKE_PROVIDERS=false`.
- [ ] Update `README.md` with no-fake production guidance and watchlist toggle instructions.
- [ ] Run `git diff --check`.
- [ ] Commit `docs: document production data controls`.

## Task 4: Verification and merge

- [ ] Run `cd apps/api && uv run pytest -q`.
- [ ] Run `cd apps/api && uv run ruff check .`.
- [ ] Run `corepack pnpm --filter @stock-review/web test`.
- [ ] Run `corepack pnpm --filter @stock-review/web lint`.
- [ ] Run tracked secret scan: `git grep -I -E -l '(tk_|sk-)[A-Za-z0-9]{20,}' -- .` should return no matches.
- [ ] Merge back to main locally.
- [ ] Re-run backend tests and secret scan on main.
- [ ] Remove worktree and delete branch.

## Plan Self-Review

- Covers both user requirements: no fake production data and watchlist toggle default off.
- No placeholders remain.
- Keeps fake providers only as explicit local/test tools.
- Does not add unverified external market providers in this pass.
