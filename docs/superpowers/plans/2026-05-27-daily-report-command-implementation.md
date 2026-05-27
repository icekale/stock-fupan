# Daily Report Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `make report DATE=YYYY-MM-DD` for one-command local daily report generation.

**Architecture:** A thin Python CLI reuses `Settings`, `create_provider_bundle`, and `ReportGenerator`; a root `Makefile` delegates to the CLI from `apps/api`.

**Tech Stack:** Python 3.12, argparse, pytest, Make, existing FastAPI backend services.

---

### Task 1: CLI Behavior Tests

**Files:**
- Create: `apps/api/tests/test_generate_report_cli.py`

- [ ] Write a failing test for `generate_report.main(["--date", "2026-05-26", "--reports-root", tmp])` that expects exit code `0`, generated HTML/snapshot paths in stdout, and no API key output.
- [ ] Write a failing test where validation is invalid and expects exit code `1` with validation errors in stdout.
- [ ] Run `cd apps/api && PYTHONPATH=. .venv/bin/python -m pytest tests/test_generate_report_cli.py -q` and confirm failure because the CLI module does not exist.

### Task 2: CLI Implementation

**Files:**
- Create: `apps/api/app/cli/__init__.py`
- Create: `apps/api/app/cli/generate_report.py`

- [ ] Implement `argparse` for `--date` and `--reports-root`.
- [ ] Load settings through `get_settings()` and override only the local `reports_root` variable when `--reports-root` is passed.
- [ ] Build providers with `create_provider_bundle(settings)` and run `ReportGenerator` with the same provider wiring as `app.main.create_close_report()`.
- [ ] Print report path, snapshot path, validation status, provider statuses, and structured review status.
- [ ] Return `1` if validation fails; return `0` otherwise.
- [ ] Run the focused CLI tests and make them pass.

### Task 3: Makefile and Docs

**Files:**
- Create: `Makefile`
- Modify: `README.md`

- [ ] Add `report` target requiring `DATE` and calling `cd apps/api && PYTHONPATH=. .venv/bin/python -m app.cli.generate_report --date $(DATE)`.
- [ ] Add a README section showing `make report DATE=2026-05-26` and where to find `report.html`.
- [ ] Run focused CLI tests, full backend tests, and ruff.
