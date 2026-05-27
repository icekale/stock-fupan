# TickFlow Frontline Stocks Design

## Goal

Make every strong TickFlow-ranked sector carry real front-row stock evidence into the generated HTML report, snapshot, API response, and `make report` output.

## Architecture

The feature belongs in the core report pipeline, not in the CLI. `TickFlowMarketDataProvider` will enrich its market snapshot with a small in-memory mapping from sector name to ranked `WatchlistQuote` front-row stocks. `ReportGenerator` will read that mapping when present and merge TickFlow stocks into each `SectorCandidate.top_stocks` before curated review-source stocks.

## Data Flow

1. TickFlow fetches full A-share quotes through `CN_Equity_A`.
2. TickFlow fetches industry universes and their symbols when available.
3. Strong sectors are ranked from industry-member groups first; keyword-theme grouping remains the fallback.
4. The provider stores the top stocks for each produced sector, sorted by percentage change then turnover.
5. `ReportGenerator` converts those quotes into `StockCandidate` records tagged `TickFlow前排`.
6. Existing HTML templates render `top_stocks` without needing a new report command.

## Scope

This iteration does not add a new UI, a separate endpoint, or a new command. It also does not try to parse every possible external source for stock reasons; curated review sources still provide narrative confirmation, while TickFlow provides structured front-row stock evidence.

## Success Criteria

- TickFlow sector snapshots can expose front-row stocks for ranked sectors.
- Reports generated from such snapshots include those stocks in `SectorCandidate.top_stocks` and `snapshot.json`.
- Review-source stocks are still merged and deduplicated.
- `make report DATE=2026-05-26` uses the new capability automatically.
