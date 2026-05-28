import assert from "node:assert/strict";
import test from "node:test";
import { getLatestTradeDate } from "./tradeDate.ts";

test("uses Shanghai weekday when container timezone is UTC", () => {
  assert.equal(getLatestTradeDate(new Date("2026-05-23T01:00:00Z")), "2026-05-22");
  assert.equal(getLatestTradeDate(new Date("2026-05-24T01:00:00Z")), "2026-05-22");
  assert.equal(getLatestTradeDate(new Date("2026-05-25T01:00:00Z")), "2026-05-25");
});
