import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("evidence panel is wired to API helpers and homepage", () => {
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
  const panelSource = readFileSync(new URL("../components/EvidencePanel.tsx", import.meta.url), "utf8");
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(typesSource, /EvidenceItem/);
  assert.match(typesSource, /EvidenceParsePreview/);
  assert.match(apiSource, /parseEvidencePreview/);
  assert.match(apiSource, /saveEvidenceItems/);
  assert.match(apiSource, /searchEvidenceCandidates/);
  assert.match(panelSource, /日报证据/);
  assert.match(panelSource, /解析预览/);
  assert.match(panelSource, /Anspire 候选/);
  assert.match(pageSource, /EvidencePanel/);
});
