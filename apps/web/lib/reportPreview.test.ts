import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("report preview uses stable keys for data-driven repeated values", () => {
  const previewSource = readFileSync(new URL("../components/ReportPreview.tsx", import.meta.url), "utf8");

  assert.match(previewSource, /key=\{`\$\{tag\}-\$\{index\}`\}/);
  assert.match(previewSource, /key=\{`\$\{sector\.rank\}-\$\{sector\.name\}`\}/);
  assert.match(previewSource, /key=\{`\$\{error\}-\$\{index\}`\}/);
  assert.match(previewSource, /key=\{`\$\{item\}-\$\{index\}`\}/);
  assert.doesNotMatch(previewSource, /key=\{tag\}/);
  assert.doesNotMatch(previewSource, /key=\{sector\.name\}/);
  assert.doesNotMatch(previewSource, /key=\{error\}/);
  assert.doesNotMatch(previewSource, /key=\{item\}/);
});
