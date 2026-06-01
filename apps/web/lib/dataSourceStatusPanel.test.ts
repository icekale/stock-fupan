import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("data source panel supports runtime provider options", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
  const panelSource = readFileSync(new URL("../components/DataSourceStatusPanel.tsx", import.meta.url), "utf8");

  assert.match(typesSource, /DataSourceOptionsResponse/);
  assert.match(typesSource, /DataSourceOptionsUpdate/);
  assert.match(apiSource, /getDataSourceOptions/);
  assert.match(apiSource, /updateDataSourceOptions/);
  assert.match(panelSource, /fallback_enabled/);
  assert.match(panelSource, /review_sources/);
  assert.match(panelSource, /onSave/);
  assert.match(panelSource, /key=\{`\$\{item\.name\}-\$\{item\.role\}`\}/);
  assert.match(panelSource, /key=\{`\$\{category\.key\}-\$\{option\.key\}`\}/);
  assert.doesNotMatch(panelSource, /key=\{item\.name\}/);
  assert.doesNotMatch(panelSource, /key=\{option\.label\}/);
});
