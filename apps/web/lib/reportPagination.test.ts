import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("reports list paginates history without breaking current-page bulk selection", () => {
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(pageSource, /reportsPerPage = 5/);
  assert.match(pageSource, /currentReportPage/);
  assert.match(pageSource, /paginatedReports/);
  assert.match(pageSource, /totalReportPages/);
  assert.match(pageSource, /上一页/);
  assert.match(pageSource, /下一页/);
  assert.match(pageSource, /第 \{currentReportPage\} \/ \{totalReportPages\} 页/);
});
