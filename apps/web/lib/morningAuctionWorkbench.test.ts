import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("admin shell exposes morning auction workbench navigation", () => {
  const shellSource = readFileSync(new URL("../components/AdminShell.tsx", import.meta.url), "utf8");

  assert.match(shellSource, /href: "\/morning-auction"/);
  assert.match(shellSource, /早盘模型/);
});

test("morning auction page connects predictions and trial log APIs", () => {
  const pageSource = readFileSync(new URL("../app/morning-auction/page.tsx", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");

  assert.match(pageSource, /早盘竞价模型/);
  assert.match(pageSource, /实盘试运行/);
  assert.match(pageSource, /10:00/);
  assert.match(pageSource, /predictMorningAuction/);
  assert.match(pageSource, /listMorningAuctionTrials/);
  assert.match(pageSource, /saveMorningAuctionTrial/);
  assert.match(apiSource, /predictMorningAuction/);
  assert.match(apiSource, /listMorningAuctionTrials/);
  assert.match(apiSource, /saveMorningAuctionTrial/);
  assert.match(typesSource, /MorningAuctionRun/);
  assert.match(typesSource, /MorningAuctionTrialEntry/);
});
