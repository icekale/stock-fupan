import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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

test("settings page exposes tickflow health schedule and notification status", () => {
  const pageSource = readFileSync(new URL("../app/settings/page.tsx", import.meta.url), "utf8");

  assert.match(pageSource, /TickFlow 健康检查/);
  assert.match(pageSource, /实时行情/);
  assert.match(pageSource, /日 K/);
  assert.match(pageSource, /分钟线/);
  assert.match(pageSource, /10:00/);
  assert.match(pageSource, /14:30/);
  assert.match(pageSource, /19:30/);
  assert.match(pageSource, /每日提醒上限/);
  assert.match(pageSource, /过期复看周期/);
  assert.match(pageSource, /企业微信/);
  assert.match(pageSource, /飞书/);
  assert.match(pageSource, /Telegram/);
  assert.match(pageSource, /邮件/);
  assert.match(pageSource, /getTickFlowHealth/);
  assert.match(pageSource, /getWatchlistAlertSchedule/);
});
