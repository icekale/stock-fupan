import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("report screens expose generated PDF assets", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const previewSource = readFileSync(new URL("../components/ReportPreview.tsx", import.meta.url), "utf8");
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(typesSource, /pdf_url/);
  assert.match(previewSource, /打开 PDF/);
  assert.match(pageSource, /打开 PDF/);
});
