import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("report preview exposes daily watchlist risk detection", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const previewSource = readFileSync(new URL("../components/ReportPreview.tsx", import.meta.url), "utf8");

  assert.match(typesSource, /risk_items: WatchlistRiskItem\[\]/);
  assert.match(typesSource, /risk_level: "high" \| "medium" \| "low"/);
  assert.match(previewSource, /自选股风险检测/);
  assert.match(previewSource, /实时行情结构信号/);
  assert.match(previewSource, /risk_items/);
  assert.doesNotMatch(typesSource, /negative_news_status/);
  assert.doesNotMatch(typesSource, /severe_abnormal_warning/);
  assert.doesNotMatch(previewSource, /负面新闻/);
  assert.doesNotMatch(previewSource, /严重异动/);
});
