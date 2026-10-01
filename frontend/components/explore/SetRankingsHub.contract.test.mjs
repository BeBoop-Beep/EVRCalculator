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

test("Set hub defaults to RIP Score and exposes the five Benchmark V1 lenses", () => {
  assert.ok(hub.includes('initialView = "ripScore"'));
  assert.ok(hub.includes("useState(initialView)"));
  const registry = read("./setRankingViews.mjs");
  for (const label of ["RIP Score", "Financial", "Collector", "Chase", "Pack Economics"]) assert.ok(registry.includes(`label: "${label}"`));
  assert.ok(!registry.includes('label: "Compare Metrics"'));
});

test("Set leaderboard delegates canonical scorecards to the shared table", () => {
  assert.ok(leaderboard.includes("RankingsScoreTable"));
  assert.ok(leaderboard.includes('scoreLabel="RIP Score"'));
  assert.ok(leaderboard.includes('entity="Sets"'));
  assert.ok(leaderboard.includes('canonicalMetricRows(scorecards?.rows, "overall"'));
  assert.ok(!leaderboard.includes("RipTierMark"));
  assert.ok(!leaderboard.includes("overallRipV12"));
  for (const paid of ["Financial RIP", "Chase Accessibility", "Collector Appeal", "Format Strength", "RankingsFamilyCells"]) assert.ok(!leaderboard.includes(paid));
});

test("paid Benchmark lenses share one Plus lock and no legacy dense score table is reachable", () => {
  assert.ok(hub.includes("<PlanLock requiredPlan={INDEX_PLAN_PLUS}"));
  assert.ok(!hub.includes("ExploreTableClient"));
  assert.equal((hub.match(/<PlanLock requiredPlan=/g) || []).length, 1);
});

test("public Set headlines and paid component scorecards stay separate while Era handoff retains the filter", () => {
  assert.equal((lazy.match(/readPublicRankingsHeadlines\("set"/g) || []).length, 1);
  assert.equal((hub.match(/readRankingsScorecards\("set"/g) || []).length, 1);
  assert.ok(hub.includes("sessionCache = null"));
  assert.ok(hub.includes("readPackEconomics"));
  assert.ok(hub.includes("scorecards={publicScorecards}"));
  assert.ok(!hub.includes("fetch("));
  assert.ok(lazy.includes("setSelectedEra(era?.eraName || null)"));
  assert.ok(lazy.includes('initialView={setEntryView} publicScorecards={visibleSetsState.scorecards} sessionCache={sessionCache}'));
  assert.ok(lazy.includes("eraFilter={selectedEra}"));
});
