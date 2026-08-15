import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const source = fs.readFileSync(path.resolve(path.dirname(new URL(import.meta.url).pathname.slice(1)), "page.js"), "utf8");

test("Market Set Values come from one Market-domain snapshot, never RIP rankings", () => {
  assert.match(source, /getExploreSetValueMarket/);
  assert.doesNotMatch(source, /getRipStatisticsTargets/);
  assert.doesNotMatch(source, /projectMarketRankingTargets/);
});

test("Market serves two global snapshots in parallel with no per-set request", () => {
  assert.match(source, /Promise\.allSettled/);
  assert.match(source, /getExploreSetValueMarket\(\)/);
  assert.match(source, /getExploreMarketMovers\(\)/);
  assert.doesNotMatch(source, /getPokemonSetOverview|getPokemonSetValueHistory/);
});
