import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const lazy = read("./RankingsLazyClient.jsx");
const hub = read("./SetRankingsHub.jsx");
const leaderboard = read("./SetRipScoreLeaderboard.jsx");
const page = read("../../app/Explore/page.js");

test("Rankings and Era navigation use the Bucket 1 information architecture", () => {
  for (const label of ["Overview", "Eras", "Sets", "Products", "Cards"]) assert.ok(lazy.includes(`label: "${label}"`));
  assert.ok(lazy.includes('{ value: "rankings", label: "Era RIP Score" }'));
  assert.ok(lazy.includes('{ value: "economics", label: "Pack Economics" }'));
  assert.ok(page.includes("Pokémon Rankings"));
  assert.ok(!page.includes("Pokémon RIP Rankings"));
});

test("Set hub defaults to RIP Score and exposes only RIP Score + Pack Economics", () => {
  assert.ok(hub.includes('initialView = "ripScore"'));
  assert.ok(hub.includes("useState(initialView)"));
  const registry = read("./setRankingViews.mjs");
  for (const label of ["RIP Score", "Pack Economics"]) assert.ok(registry.includes(`label: "${label}"`));
  for (const removed of ["Financial", "Collector", "Chase", "Compare Metrics"]) assert.ok(!registry.includes(`label: "${removed}"`));
});

test("Set leaderboard delegates canonical scorecards to the unified table", () => {
  assert.ok(leaderboard.includes("BenchmarkEntityScoreTable"));
  assert.ok(leaderboard.includes('entity="Sets"'));
  assert.ok(leaderboard.includes("mergeScorecardRows(scorecards"));
  assert.ok(leaderboard.includes('usePaidScorecards("set"'));
  assert.ok(!leaderboard.includes("RipTierMark"));
  assert.ok(!leaderboard.includes("overallRipV12"));
  for (const paid of ["Financial RIP", "Chase Accessibility", "Format Strength", "RankingsFamilyCells"]) assert.ok(!leaderboard.includes(paid));
});

test("the hub no longer renders per-metric locks or legacy dense tables", () => {
  assert.ok(!hub.includes("PlanLock"));
  assert.ok(!hub.includes("SetMetricRankingsTable"));
  assert.ok(!hub.includes("ExploreTableClient"));
});

test("public Set headlines and paid component scorecards stay separate while Era handoff retains the filter", () => {
  assert.equal((lazy.match(/readPublicRankingsHeadlines\("set"/g) || []).length, 1);
  assert.equal((hub.match(/readRankingsScorecards\(/g) || []).length, 0);
  assert.ok(hub.includes("sessionCache = null"));
  assert.ok(hub.includes("readPackEconomics"));
  assert.ok(hub.includes("scorecards={publicScorecards}"));
  assert.ok(leaderboard.includes("sessionCache={sessionCache}") || hub.includes("sessionCache={sessionCache}"));
  assert.ok(!hub.includes("fetch("));
  assert.ok(lazy.includes("setSelectedEra(era?.eraName || null)"));
  assert.ok(lazy.includes('initialView={setEntryView} publicScorecards={visibleSetsState.scorecards} sessionCache={sessionCache}'));
  assert.ok(lazy.includes("eraFilter={selectedEra}"));
});
