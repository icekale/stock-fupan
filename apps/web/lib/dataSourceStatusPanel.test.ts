import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("data source panel supports experimental provider status", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
  const panelSource = readFileSync(new URL("../components/DataSourceStatusPanel.tsx", import.meta.url), "utf8");

  assert.match(typesSource, /"experimental"/);
  assert.match(typesSource, /DataSourceOptionsResponse/);
  assert.match(typesSource, /DataSourceOptionsUpdate/);
  assert.match(apiSource, /getDataSourceOptions/);
  assert.match(apiSource, /updateDataSourceOptions/);
  assert.match(panelSource, /experimental:/);
  assert.match(panelSource, /fallback_enabled/);
  assert.match(panelSource, /review_sources/);
  assert.match(panelSource, /onSave/);
  assert.match(panelSource, /role="switch"/);
  assert.match(panelSource, /aria-checked=\{draft\.fallback_enabled\}/);
  assert.match(panelSource, /保存数据源选项中/);
  assert.match(panelSource, /border-l-4/);
  assert.match(panelSource, /key=\{`\$\{item\.name\}-\$\{item\.role\}`\}/);
  assert.doesNotMatch(panelSource, /key=\{item\.name\}/);
});
