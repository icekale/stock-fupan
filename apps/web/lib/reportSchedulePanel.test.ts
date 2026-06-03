import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("home page exposes scheduled report generation controls", () => {
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const panelSource = readFileSync(new URL("../components/ReportSchedulePanel.tsx", import.meta.url), "utf8");

  assert.match(pageSource, /ReportSchedulePanel/);
  assert.match(pageSource, /refreshReportSchedule/);
  assert.match(pageSource, /handleSaveReportSchedule/);
  assert.match(apiSource, /getReportScheduleStatus/);
  assert.match(apiSource, /updateReportScheduleStatus/);
  assert.match(typesSource, /ReportScheduleStatus/);
  assert.match(typesSource, /ReportScheduleUpdate/);
  assert.match(panelSource, /role="switch"/);
  assert.match(panelSource, /aria-checked=\{enabled\}/);
  assert.match(panelSource, /formatScheduleDateTime/);
  assert.match(panelSource, /读取定时设置/);
});
