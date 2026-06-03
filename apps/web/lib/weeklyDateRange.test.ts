import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("weekly report explains end date and derived week range", () => {
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(pageSource, /getWeeklyRange/);
  assert.match(pageSource, /周报结束日/);
  assert.match(pageSource, /将生成：/);
  assert.match(pageSource, /生成 \$\{weeklyRange\.startDate\} 至 \$\{weeklyRange\.endDate\} 周报复盘/);
});
