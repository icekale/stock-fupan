import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("home page does not compute latest trade date during initial render", () => {
  const source = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(source, /useState\(""\)/);
  assert.doesNotMatch(source, /useState\(\(\) => getLatestTradeDate\(\)\)/);
});
