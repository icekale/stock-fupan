import assert from "node:assert/strict";
import test from "node:test";
import type { WatchlistAlertScheduleStatus } from "./types";

test("watchlist alert schedule status includes intraday and review times", () => {
  const status: WatchlistAlertScheduleStatus = {
    enabled: true,
    morning_time: "10:00",
    afternoon_time: "14:30",
    review_time: "19:30",
    timezone: "Asia/Shanghai",
    last_run_at: null,
    last_result: null,
  };

  assert.equal(status.review_time, "19:30");
});
