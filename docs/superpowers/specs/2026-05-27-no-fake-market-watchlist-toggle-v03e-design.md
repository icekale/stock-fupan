# TickFlow-First No-Fake Market Data and Watchlist Toggle v0.3e Design

## Context

The project's primary artifact is the generated `report.html`. Recent real-provider testing showed:

- Anspire real news is working after removing the unsupported `search_type=hybrid` parameter.
- TickFlow real quotes are working after mapping nested `ext` fields.
- AkShare market endpoints can fail with upstream `RemoteDisconnected` errors.
- The user explicitly requires that the production report must not use fake market/news/watchlist content.
- The user wants the `自选股观察` module controlled by a switch and disabled by default.

## Goals

- Production report generation must fail with an explicit provider error when real market data is unavailable instead of silently using fake content.
- Development and tests can still use fake providers by explicitly setting provider values to `fake`.
- Add a report-level watchlist module switch that defaults to off.
- When the watchlist module is off, report generation must not call TickFlow and `report.html` must not render `自选股观察`.
- When the watchlist module is on and a watchlist exists, TickFlow quotes feed the `自选股观察` section.

## Non-Goals

- Do not build a UI settings panel in this pass.
- Do not remove fake providers from the codebase; they remain explicit local/test providers.
- Do not change the 12-section HTML order except omitting the watchlist section when disabled.

## Configuration

Add these settings:

- `REPORT_WATCHLIST_ENABLED=false` by default.
- `PRODUCTION_ALLOW_FAKE_PROVIDERS=false` by default.

Provider behavior:

- Explicit `MARKET_PROVIDER=fake`, `NEWS_PROVIDER=fake`, or `TICKFLOW_PROVIDER=fake` remains available for tests and local demos.
- If `APP_ENV=production` and `PRODUCTION_ALLOW_FAKE_PROVIDERS=false`, provider factory rejects fake providers and rejects fallback chains whose fallback is fake.
- In development, the existing fallback-to-fake behavior can remain for quick local smoke tests, but the generated provider status must make fallback visible.

## Market Data Approach

v0.3e prioritizes TickFlow for market data and correctness over hiding failure:

- Use TickFlow as the primary real market source when `MARKET_PROVIDER=tickflow`.
- In production mode, the preferred chain is TickFlow market data first, then AkShare as a real fallback if explicitly configured by the provider chain; if all real providers fail, report generation fails rather than emitting fake market data.
- Future work can improve sector classification quality, but v0.3e should already use TickFlow for indices, market breadth, turnover, and ranked equity-derived sectors when available.

This avoids shipping plausible-looking but fake market data in the final HTML.

## Watchlist Toggle Behavior

- `ReportGenerator` receives `watchlist_enabled: bool`.
- Default is false from settings.
- When false:
  - Do not call `watchlist_service.get_latest()`.
  - Do not call TickFlow.
  - Leave `report.watchlist_observation` as `None`.
  - Set `provider_status.tickflow` to disabled with reason `自选股模块未开启`.
  - Do not render the `自选股观察` section in the structured HTML branch.
- When true:
  - Existing watchlist and TickFlow behavior applies.
  - The section renders if `report.watchlist_observation` exists.

## HTML Requirements

- With default settings, the generated HTML contains 11 sections and omits `自选股观察`.
- When `REPORT_WATCHLIST_ENABLED=true`, the generated HTML contains `自选股观察` in the existing section position between `明日可介入标的与仓位建议` and `去弱留强排序`.
- Section numbering should remain visually coherent. It is acceptable for v0.3e to keep static numbers only if tests assert no duplicate section numbers; preferred implementation uses a template namespace counter.

## Testing Requirements

- Unit test production provider factory rejects fake market/news/tickflow providers by default.
- Unit test production provider factory rejects fake fallback for AkShare when fallback is disabled by production settings.
- Unit test report generation default does not call watchlist service or TickFlow.
- Unit test HTML default omits `自选股观察`.
- Unit test enabling watchlist includes `自选股观察` and TickFlow status.
- Existing fake-provider tests should continue to pass by explicitly using development settings or explicit fake providers.

## Rollout

- Write `.env.example` defaults with `REPORT_WATCHLIST_ENABLED=false` and `PRODUCTION_ALLOW_FAKE_PROVIDERS=false`.
- Document that local users may set fake providers only for demos/tests, not for production-grade reports.
- Keep current local `apps/api/.env` ignored and under user control.

## Self-Review

- No placeholders remain.
- Scope is focused on no-fake production behavior and watchlist toggle.
- The design avoids pretending fake data is acceptable in final HTML.
- Real backup market provider remains future work because no verified stable alternate A-share source has been integrated yet.
