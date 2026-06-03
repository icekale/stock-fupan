import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("report schedule panel is wired to API helpers and homepage", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
  const panelSource = readFileSync(new URL("../components/ReportSchedulePanel.tsx", import.meta.url), "utf8");
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(typesSource, /ReportScheduleStatus/);
  assert.match(typesSource, /ReportScheduleUpdate/);
  assert.match(apiSource, /getReportScheduleStatus/);
  assert.match(apiSource, /updateReportScheduleStatus/);
  assert.match(panelSource, /定时生成/);
  assert.match(panelSource, /enabled/);
  assert.match(panelSource, /19:00/);
  assert.match(pageSource, /ReportSchedulePanel/);
});
