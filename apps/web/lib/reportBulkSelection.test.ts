import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("reports list supports bulk selection and deletion controls", () => {
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(pageSource, /selectedReportIds/);
  assert.match(pageSource, /toggleReportSelection/);
  assert.match(pageSource, /handleBulkDeleteReports/);
  assert.match(pageSource, /全选当前列表/);
  assert.match(pageSource, /批量删除/);
  assert.match(pageSource, /aria-label={`选择报告/);
});
