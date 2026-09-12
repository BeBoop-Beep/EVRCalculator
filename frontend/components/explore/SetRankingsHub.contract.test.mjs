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
  assert.ok(lazy.includes('{ value: "rankings", label: "Set Strength" }'));
  assert.ok(lazy.includes('{ value: "economics", label: "Pack Economics" }'));
  assert.ok(page.includes("Pokémon Rankings"));
  assert.ok(!page.includes("Pokémon RIP Rankings"));
});

test("Set hub defaults to RIP Score and exposes exactly three Bucket 1 tabs", () => {
  assert.ok(hub.includes('initialView = "ripScore"'));
  assert.ok(hub.includes("useState(initialView)"));
  for (const label of ["RIP Score", "Pack Economics", "Compare Metrics"]) assert.ok(hub.includes(`label: "${label}"`));
  for (const deferred of ["Financial RIP", "Collector Appeal", "Chase Accessibility"]) assert.ok(!hub.includes(`label: "${deferred}"`));
});

test("public leaderboard is lean and reads only canonical Set RIP presentation", () => {
  for (const heading of ["Rank", "Set", "Era", "Set RIP Score", "RIP Tier"]) assert.ok(leaderboard.includes(heading));
  assert.ok(leaderboard.includes("readPublicSetRip(target)"));
  assert.ok(!leaderboard.includes("overallRipV12"));
  for (const paid of ["Financial RIP", "Chase Accessibility", "Collector Appeal", "Format Strength", "RankingsFamilyCells"]) assert.ok(!leaderboard.includes(paid));
});

test("Compare Metrics is one Plus lock and entitled users receive the existing dense table", () => {
  assert.ok(hub.includes("<PlanLock requiredPlan={INDEX_PLAN_PLUS}"));
  assert.ok(hub.includes("canViewRankingsIntelligence ? <ExploreTableClient"));
  assert.equal((hub.match(/<PlanLock requiredPlan=/g) || []).length, 1);
});

test("all Set tabs reuse one loaded cohort and Era handoff retains the filter", () => {
  assert.equal((lazy.match(/fetch\("\/api\/explore\/rankings\/lens\?lens=sets"/g) || []).length, 1);
  assert.ok(hub.includes("targets={targets}"));
  assert.ok(!hub.includes("fetch("));
  assert.ok(lazy.includes("setSelectedEra(era?.eraName || null)"));
  assert.ok(lazy.includes('initialView={setEntryView} targets={setTargets}'));
  assert.ok(lazy.includes("eraFilter={selectedEra}"));
});
