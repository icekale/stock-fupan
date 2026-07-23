# Free StockDB Morning Auction Source Design

## Goal

Add a local-network `free-stockdb` HTTP data source for the morning-auction cold-start pipeline so historical daily bars and candidate universes can be read from `http://192.168.5.221:7899/` quickly and reproducibly.

## Context

The existing morning-auction package already depends on a small `MorningAuctionDataSource` protocol. Training and dataset construction do not need to know where bars come from. `free-stockdb` exposes a simple HTTP query API:

```text
/?cmd=vals&t=日k&k1=key:600633&k2=fwd:20260620,20260626
/?cmd=vals&t=日k&k1=all:&k2=key:20260625
```

The deployed LAN service was verified from this machine on `2026-07-03`:

- `192.168.5.221:7899` accepts TCP connections.
- Single-symbol daily bars return the expected fields.
- Single-day full-market daily bars return 7521 records for `20260625`.
- Minute bars are available, but this phase only uses daily bars.

## Scope

This phase adds daily-bar cold-start support only:

- A small synchronous HTTP client for `free-stockdb`.
- A `FreeStockDbMorningAuctionDataSource` implementation of the existing protocol.
- Unit tests with mocked HTTP responses.
- A CLI `build-dataset` command that can produce JSONL samples for a date range.

This phase does not add historical auction reconstruction, minute-line features, live 9:15-9:25 collectors, or production API configuration. `auction_snapshot()` returns `None` until self-collected auction snapshots exist.

## Data Mapping

`free-stockdb` daily records map to `DailyBar` as follows:

| free-stockdb field | Model field |
| --- | --- |
| `date` | `trade_date` as `YYYY-MM-DD` |
| `open` | `open` |
| `high` | `high` |
| `low` | `low` |
| `close` | `close` |
| `volume` | `volume` |
| `amount` | `amount` |
| `turnover` | `turnover_rate` |

Candidate universe records come from `cmd=vals&t=日k&k1=all:&k2=key:<YYYYMMDD>`. Each record maps to:

- `symbol`: normalized to `600633.SH`, `000001.SZ`, or `920992.BJ`.
- `name`: `name`.
- `is_st`: `is_st`.
- `market_cap_float`: `float_mv`.
- `listed_days`: default `9999` because the service does not expose listing date in this endpoint.
- `is_suspended`: `False` for rows returned with positive trading data; invalid current bars are already skipped by dataset construction.

## Error Handling

HTTP failures, non-JSON responses, or non-list payloads raise a focused `FreeStockDbError`. Empty responses are treated as empty data, not as exceptions. Non-dict rows are ignored.

## Testing

Tests mock the HTTP client transport and verify:

- URL parameters use `cmd=vals`, `t=日k`, `k1`, and `k2` correctly.
- Date normalization accepts both `YYYY-MM-DD` and `YYYYMMDD`.
- Daily rows map to `DailyBar`.
- Full-market records map to candidate dictionaries with normalized A-share suffixes.
- Dataset construction works against the new data source with no auction snapshot.
- The CLI writes JSONL rows for a requested date range.

## Open Risk

The service is a local Windows-hosted process with no authentication in this LAN deployment. It should stay restricted to the private subnet and should not be exposed to the public internet.
