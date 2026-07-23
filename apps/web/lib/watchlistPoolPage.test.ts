import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("admin shell exposes route aware watchlist navigation", () => {
  const shellSource = readFileSync(new URL("../components/AdminShell.tsx", import.meta.url), "utf8");

  assert.match(shellSource, /usePathname/);
  assert.match(shellSource, /href: "\/"/);
  assert.match(shellSource, /href: "\/watchlist"/);
  assert.match(shellSource, /href: "\/watchlist-alerts"/);
  assert.match(shellSource, /href: "\/settings"/);
  assert.match(shellSource, /首页/);
  assert.match(shellSource, /自选股/);
  assert.match(shellSource, /提醒中心/);
  assert.match(shellSource, /设置/);
});

test("home page links into independent watchlist system", () => {
  const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(pageSource, /独立选股与自选股管理/);
  assert.match(pageSource, /href="\/watchlist"/);
  assert.match(pageSource, /href="\/watchlist-alerts"/);
  assert.match(pageSource, /href="\/settings"/);
});

test("watchlist page supports groups stocks and observation plans", () => {
  const pageSource = readFileSync(new URL("../app/watchlist/page.tsx", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
  const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");

  assert.match(pageSource, /自选股池/);
  assert.match(pageSource, /新增分组/);
  assert.match(pageSource, /删除分组/);
  assert.match(pageSource, /加入理由/);
  assert.match(pageSource, /计划买点/);
  assert.match(pageSource, /失效条件/);
  assert.match(pageSource, /所属题材/);
  assert.match(pageSource, /上次复盘结论/);
  assert.match(pageSource, /今天风险提示/);
  assert.match(pageSource, /多分组/);
  assert.match(pageSource, /getWatchlistPool/);
  assert.match(apiSource, /createWatchlistStock/);
  assert.match(apiSource, /updateWatchlistStock/);
  assert.match(apiSource, /deleteWatchlistGroup/);
  assert.match(typesSource, /WatchlistPoolStock/);
  assert.match(typesSource, /WatchlistPoolGroup/);
});
