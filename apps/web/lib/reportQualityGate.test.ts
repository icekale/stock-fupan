import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("reports list prioritizes quality gate publish status", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(typesSource, /QualityGateResult/);
  assert.match(typesSource, /PublishStatus/);
  assert.match(typesSource, /quality_score: number \| null/);
  assert.match(typesSource, /publish_status: PublishStatus \| null/);
  assert.match(pageSource, /PublishStatusBadge/);
  assert.match(pageSource, /formatPublishStatus/);
  assert.match(pageSource, /不可发布草稿/);
  assert.match(pageSource, /quality_summary/);
});
