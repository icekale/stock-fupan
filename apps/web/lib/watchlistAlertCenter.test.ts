import assert from "node:assert/strict";
import test from "node:test";
import type { WatchlistAlertEvent } from "./types";

test("watchlist alert event type supports risk payload", () => {
  const event: WatchlistAlertEvent = {
    id: 1,
    symbol: "600519.SH",
    name: "贵州茅台",
    event_type: "risk",
    severity: "high",
    status: "active",
    trigger_reason: "跌破MA5",
    ai_comment: "跌破MA5，先处理风险",
    source_status: { tickflow: "ready" },
    market_snapshot: { pct_change: -5.1 },
    rule_snapshot: { rule_id: "ma_break" },
    notification_status: { sent: false },
    first_seen_at: "2026-06-15T02:00:00Z",
    last_seen_at: "2026-06-15T02:00:00Z",
  };

  assert.equal(event.severity, "high");
});
