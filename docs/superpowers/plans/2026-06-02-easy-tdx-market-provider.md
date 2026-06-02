# Easy TDX Market Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `easy_tdx` as a selectable market data provider for daily report generation.

**Architecture:** Keep the existing `MarketCloseSnapshot` contract. Add a focused `EasyTdxMarketDataProvider` that adapts `easy_tdx.MacClient` quote, index, board ranking, and board member data into the current report seed shape, then register it in runtime config and provider factory.

**Tech Stack:** FastAPI backend, Pydantic settings, pytest, `easy-tdx` Python package.

---

### Task 1: Provider Option and Factory

**Files:**
- Modify: `apps/api/app/providers/runtime_config.py`
- Modify: `apps/api/app/providers/factory.py`
- Test: `apps/api/tests/test_runtime_provider_config.py`
- Test: `apps/api/tests/test_real_providers.py`

- [ ] **Step 1: Write failing tests**

Add assertions that `easy_tdx` is accepted as a market provider, appears in the market provider options payload, and factory creates an `EasyTdxMarketDataProvider`.

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd apps/api && uv run pytest -q tests/test_runtime_provider_config.py tests/test_real_providers.py
```

Expected: fail because `easy_tdx` is unsupported and the provider class is missing.

- [ ] **Step 3: Implement minimal config and factory registration**

Add `easy_tdx` to market provider keys/options, add optional timeout/server settings only if needed, and register provider creation.

- [ ] **Step 4: Run tests to verify they pass**

Run the same pytest command and expect all selected tests to pass.

### Task 2: Easy TDX Provider Adapter

**Files:**
- Create: `apps/api/app/providers/easy_tdx.py`
- Modify: `apps/api/pyproject.toml`
- Test: `apps/api/tests/test_easy_tdx_provider.py`

- [ ] **Step 1: Write failing provider tests**

Use fake client objects and pandas DataFrames. Cover quote mapping, close snapshot generation, sector ranking, and frontline stock extraction.

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd apps/api && uv run pytest -q tests/test_easy_tdx_provider.py
```

Expected: fail because `app.providers.easy_tdx` does not exist.

- [ ] **Step 3: Implement minimal provider**

Map `easy_tdx` rows into existing `WatchlistQuote`, `IndexSnapshot`, `MarketBreadth`, and `RawSectorInput`. Raise `ProviderFallbackError` when required data is missing.

- [ ] **Step 4: Run tests to verify they pass**

Run the provider test file and expect it to pass.

### Task 3: Full Verification and Release

**Files:**
- Any changed backend files
- Any lockfile updated by dependency resolution

- [ ] **Step 1: Run full backend and frontend tests**

Run:
```bash
cd apps/api && uv run pytest -q
cd apps/web && npm test
```

- [ ] **Step 2: Commit and push**

Commit the minimal diff and push the current branch.

- [ ] **Step 3: Deploy to Unraid**

Archive the committed tree, upload to `/mnt/user/appdata/stock-fupan`, preserve `.env`, `reports`, and `apps/api/data`, rebuild with Docker Compose, and verify `/api/health` and `/api/data-sources/options`.
