import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { WatchlistAlertEvent } from "./types";

test("watchlist alert event type supports risk payload", () => {
  const event: WatchlistAlertEvent = {
    id: 1,
    stock_id: 1,
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

test("alert center page exposes filters and event actions", () => {
  const pageSource = readFileSync(new URL("../app/watchlist-alerts/page.tsx", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");

  assert.match(pageSource, /提醒中心/);
  assert.match(pageSource, /全部/);
  assert.match(pageSource, /高危/);
  assert.match(pageSource, /已处理/);
  assert.match(pageSource, /机会/);
  assert.match(pageSource, /计划/);
  assert.match(pageSource, /到期复看/);
  assert.match(pageSource, /暂不提醒/);
  assert.match(pageSource, /加入复盘结论/);
  assert.match(pageSource, /自动时段/);
  assert.match(pageSource, /收盘复盘优先/);
  assert.match(pageSource, /listReports/);
  assert.match(pageSource, /orderWatchlistAlerts/);
  assert.match(apiSource, /acknowledgeWatchlistAlert/);
  assert.match(apiSource, /muteWatchlistAlert/);
});
