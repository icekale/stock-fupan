import assert from "node:assert/strict";
import test from "node:test";
import { orderWatchlistAlerts, resolveAlertSession } from "./watchlistAlertQueue.ts";
import type { WatchlistAlertEvent } from "./types.ts";

const alerts: WatchlistAlertEvent[] = [
  createAlert({ id: 1, event_type: "plan", severity: "medium" }),
  createAlert({ id: 2, event_type: "opportunity", severity: "medium" }),
  createAlert({ id: 3, event_type: "stale_review", severity: "low" }),
  createAlert({ id: 4, event_type: "risk", severity: "high" }),
];

test("automatic alert session follows Shanghai trading windows", () => {
  assert.equal(resolveAlertSession(new Date("2026-07-10T01:30:00Z")), "morning");
  assert.equal(resolveAlertSession(new Date("2026-07-10T06:30:00Z")), "afternoon");
  assert.equal(resolveAlertSession(new Date("2026-07-10T08:00:00Z")), "close");
});

test("session ordering changes the decision queue while preserving high risk first", () => {
  assert.deepEqual(orderWatchlistAlerts(alerts, "morning").map((item) => item.id), [4, 2, 1, 3]);
  assert.deepEqual(orderWatchlistAlerts(alerts, "close").map((item) => item.id), [4, 3, 1, 2]);
});

function createAlert(
  overrides: Pick<WatchlistAlertEvent, "id" | "event_type" | "severity">,
): WatchlistAlertEvent {
  return {
    id: overrides.id,
    stock_id: 1,
    symbol: `60000${overrides.id}.SH`,
    name: "测试股票",
    event_type: overrides.event_type,
    severity: overrides.severity,
    status: "active",
    trigger_reason: "测试触发",
    ai_comment: null,
    source_status: {},
    market_snapshot: {},
    rule_snapshot: {},
    notification_status: {},
    first_seen_at: "2026-07-10T01:00:00Z",
    last_seen_at: "2026-07-10T01:00:00Z",
  };
}
