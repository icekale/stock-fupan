# THS Concept Sector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current industry-index based sector grouping with 同花顺概念/主题指数-based sector grouping.

**Architecture:** Keep the existing TickFlow-driven market snapshot and strong-stock selection. Swap the sector refinement layer so it uses AKShare's 同花顺概念板块 APIs for concept list, board info, and daily index data, then feed those board stats into the existing scoring pipeline. Preserve the current report shape and frontend layout.

**Tech Stack:** Python 3.12, FastAPI, TickFlow, AKShare, pytest.

---

### Task 1: Add THS concept board access

**Files:**
- Modify: `apps/api/pyproject.toml`
- Create: `apps/api/app/providers/ths_concepts.py`
- Modify: `apps/api/app/providers/tickflow.py`
- Test: `apps/api/tests/test_tickflow_provider.py`

- [ ] **Step 1: Write the failing test**

```python
def test_tickflow_market_provider_uses_ths_concept_board_stats():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/api/tests/test_tickflow_provider.py::test_tickflow_market_provider_uses_ths_concept_board_stats -v`

- [ ] **Step 3: Write minimal implementation**

Use `ak.stock_board_concept_name_ths()`, `ak.stock_board_concept_info_ths()`, and `ak.stock_board_concept_index_ths()` behind a small provider wrapper, then wire the market provider to call it.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/api/tests/test_tickflow_provider.py::test_tickflow_market_provider_uses_ths_concept_board_stats -v`


### Task 2: Remove industry-based refinement

**Files:**
- Modify: `apps/api/app/providers/tickflow.py`
- Test: `apps/api/tests/test_tickflow_provider.py`

- [ ] **Step 1: Write the failing test**

```python
def test_tickflow_market_provider_does_not_use_industry_universes_for_sector_grouping():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/api/tests/test_tickflow_provider.py::test_tickflow_market_provider_does_not_use_industry_universes_for_sector_grouping -v`

- [ ] **Step 3: Write minimal implementation**

Delete the SW3 industry matching path and keep only concept/theme grouping plus THS board stats.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/api/tests/test_tickflow_provider.py::test_tickflow_market_provider_does_not_use_industry_universes_for_sector_grouping -v`


### Task 3: Refresh report checks

**Files:**
- Modify: `apps/api/tests/test_report_api.py`
- Modify: `apps/api/tests/test_structured_review.py` if wording shifts
- Modify: `apps/api/app/renderers/templates/mobile_report.html.j2` only if any sector labels need text cleanup

- [ ] **Step 1: Write the failing test**

```python
def test_report_html_keeps_concept_sector_cards_scannable():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/api/tests/test_report_api.py -k concept -v`

- [ ] **Step 3: Write minimal implementation**

Adjust any assertions that still assume industry-based grouping or wording.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/api/tests/test_report_api.py -k concept -v`


### Task 4: Full verification

**Files:**
- All touched files

- [ ] **Step 1: Run targeted backend tests**

Run: `pytest apps/api/tests/test_tickflow_provider.py apps/api/tests/test_report_api.py -v`

- [ ] **Step 2: Run formatting if needed**

Run: `ruff check apps/api --fix`

- [ ] **Step 3: Redeploy locally if tests pass**

Run: `docker compose up -d --build api`
