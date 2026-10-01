import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const table = read("./BenchmarkEntityScoreTable.jsx");
const registry = read("./setRankingViews.mjs");
const overview = read("./RankingsOverviewHighlights.jsx");
const lazy = read("./RankingsLazyClient.jsx");

test("the unified score table consumes one prepared scorecard cohort with no per-row read", () => {
  assert.match(table, /filterScoreRows\(rows/);
  assert.match(table, /sortScoreRows\(/);
  assert.doesNotMatch(table, /fetch\(|readRankingsScorecards|await |N\+1/);
});

test("Set navigation is RIP Score + Pack Economics only; Pack Economics stays Plus-gated", () => {
  assert.equal((registry.match(/value: "/g) || []).length, 2);
  assert.match(registry, /ripScore[^\n]+requiredPlan: null/);
  assert.match(registry, /packEconomics[^\n]+requiredPlan: INDEX_PLAN_PLUS/);
  for (const removed of ["financial", "collectorAppeal", "chaseAccessibility"]) assert.ok(!registry.includes(`value: "${removed}"`));
});

test("Overview remains public-only and no per-metric lens endpoints are called", () => {
  for (const paid of ["Collector Appeal", "Chase Accessibility", "familyScores"]) assert.ok(!overview.includes(paid));
  assert.ok(lazy.includes('readPublicRankingsHeadlines("set"'));
  for (const endpoint of ["lens=financial", "lens=collector", "lens=chase"]) assert.ok(!lazy.includes(endpoint));
});

test("legacy per-metric Set tables and their selectors are gone", () => {
  for (const gone of ["./SetMetricRankingsTable.jsx", "./RankingsScoreTable.jsx", "./setMetricRankingSelectors.mjs"]) assert.equal(fs.existsSync(new URL(gone, import.meta.url)), false, gone);
});
