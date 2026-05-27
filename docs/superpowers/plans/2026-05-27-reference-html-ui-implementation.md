# Reference HTML UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the daily report HTML renderer with the provided reference HTML visual system while preserving dynamic real report data.

**Architecture:** This is a template-only UI rebuild guarded by renderer tests. `ReportDTO` and report generation logic remain unchanged; the Jinja template maps existing structured modules into reference HTML classes and layout.

**Tech Stack:** Python, Jinja2, pytest, ruff, static HTML/CSS.

---

### Task 1: Renderer Contract Test

**Files:**
- Modify: `apps/api/tests/test_report_api.py`

- [ ] Add a test that renders a fake structured report and asserts reference HTML classes exist: `article-wrap`, `article-card`, `header-date`, `header-title`, `preamble`, `table-wrap`, `point-list`, `footer-disclaimer`.
- [ ] Assert old classes are absent: `class="page"`, `class="paper"`, `class="hero"`, `module-card`, `sector-card`.
- [ ] Run the new test and confirm it fails before implementation.

### Task 2: Template Rebuild

**Files:**
- Modify: `apps/api/app/renderers/templates/mobile_report.html.j2`

- [ ] Replace CSS variables and layout with the reference HTML system.
- [ ] Map existing structured modules to reference section numbering and classes.
- [ ] Keep all market text dynamic; do not paste static reference narratives.
- [ ] Preserve optional watchlist and fallback report rendering.

### Task 3: Verification and Report Preview

**Files:**
- Generated: `reports/2026-05-26/close/v*/report.html`

- [ ] Run targeted renderer tests.
- [ ] Run full API test suite.
- [ ] Run ruff.
- [ ] Generate a real report with TickFlow/Anspire env loaded from the local `.env`.
- [ ] Serve the generated report on a local port for user review.
