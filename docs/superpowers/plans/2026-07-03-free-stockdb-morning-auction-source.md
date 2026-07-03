# Free StockDB Morning Auction Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `free-stockdb` LAN HTTP support as a historical daily-bar data source for morning-auction cold-start dataset generation.

**Architecture:** Create a focused HTTP adapter that converts `free-stockdb` daily records into the existing `MorningAuctionDataSource` protocol. Keep auction snapshots out of scope and return `None` for historical auction data.

**Tech Stack:** Python 3.12, `httpx`, Pydantic DTOs, pytest, existing morning-auction package.

---

## File Structure

- Create `apps/api/app/services/morning_auction/free_stockdb.py`: HTTP client, date/symbol normalization, and data-source adapter.
- Modify `apps/api/app/services/morning_auction/__init__.py`: export the new source classes if useful.
- Modify `apps/api/app/cli/morning_auction.py`: add `build-dataset` command for date-range JSONL generation.
- Create `apps/api/tests/test_morning_auction_free_stockdb.py`: mocked HTTP and CLI tests.

## Task 1: Free StockDB HTTP Adapter

**Files:**
- Create: `apps/api/app/services/morning_auction/free_stockdb.py`
- Test: `apps/api/tests/test_morning_auction_free_stockdb.py`

- [ ] **Step 1: Write failing tests**

Add tests for daily bar mapping, candidate-universe mapping, invalid lookback rejection, empty auction snapshots, and error handling.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_free_stockdb.py
```

Expected: fail because `app.services.morning_auction.free_stockdb` does not exist.

- [ ] **Step 3: Implement minimal adapter**

Create `FreeStockDbHttpClient`, `FreeStockDbMorningAuctionDataSource`, `FreeStockDbError`, and helper functions for date and symbol normalization.

- [ ] **Step 4: Verify tests pass**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_free_stockdb.py
```

Expected: all tests in the new file pass.

## Task 2: Dataset CLI

**Files:**
- Modify: `apps/api/app/cli/morning_auction.py`
- Test: `apps/api/tests/test_morning_auction_free_stockdb.py`

- [ ] **Step 1: Write failing CLI test**

Add a test for:

```bash
python -m app.cli.morning_auction build-dataset \
  --source free-stockdb \
  --base-url http://192.168.5.221:7899 \
  --start-date 2026-06-25 \
  --end-date 2026-06-25 \
  --output /tmp/samples.jsonl
```

The test should monkeypatch the data source factory and assert JSONL output.

- [ ] **Step 2: Verify test fails**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_free_stockdb.py
```

Expected: fail because `build-dataset` is not defined.

- [ ] **Step 3: Implement CLI command**

Add a `build-dataset` subcommand that loops inclusive calendar dates, builds samples for each date, and writes `sample_to_row()` JSONL rows. The command should support only `--source free-stockdb` in this phase.

- [ ] **Step 4: Verify focused tests pass**

Run:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_morning_auction_free_stockdb.py
```

Expected: all focused tests pass.

## Task 3: Full Verification

**Files:**
- All morning-auction files and tests.

- [ ] **Step 1: Run morning-auction tests**

```bash
cd apps/api
.venv/bin/python -m pytest -q \
  tests/test_morning_auction_labels.py \
  tests/test_morning_auction_features.py \
  tests/test_morning_auction_dataset.py \
  tests/test_morning_auction_training_backtest.py \
  tests/test_morning_auction_cli_api.py \
  tests/test_morning_auction_free_stockdb.py
```

- [ ] **Step 2: Run ruff**

```bash
cd apps/api
.venv/bin/python -m ruff check \
  app/services/morning_auction \
  app/cli/morning_auction.py \
  tests/test_morning_auction_labels.py \
  tests/test_morning_auction_features.py \
  tests/test_morning_auction_dataset.py \
  tests/test_morning_auction_training_backtest.py \
  tests/test_morning_auction_cli_api.py \
  tests/test_morning_auction_free_stockdb.py
```

- [ ] **Step 3: Optional LAN smoke test**

Run a one-day build against:

```bash
cd apps/api
.venv/bin/python -m app.cli.morning_auction build-dataset \
  --source free-stockdb \
  --base-url http://192.168.5.221:7899 \
  --start-date 2026-06-25 \
  --end-date 2026-06-25 \
  --output /tmp/morning-auction-free-stockdb-smoke.jsonl
```

Expected: command exits 0 and writes non-empty JSONL if the LAN service is reachable.
