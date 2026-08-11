const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const exploreSource = fs.readFileSync(path.resolve(__dirname, "page.js"), "utf8");
const rankingsSource = fs.readFileSync(path.resolve(__dirname, "../Rankings/page.js"), "utf8");
const marketSource = fs.readFileSync(path.resolve(__dirname, "../Market/page.js"), "utf8");

test("Rankings is the public name and /Explore remains backwards compatible", () => {
  assert.ok(exploreSource.includes('<h1 className="sr-only">Pokémon Set Rankings</h1>'));
  assert.ok(exploreSource.includes('title: "Pokémon Set Rankings — inDex"'));
  assert.ok(rankingsSource.includes('export { default, metadata } from "../Explore/page"'));
});

test("Rankings contains only the canonical RIP leaderboard", () => {
  assert.ok(exploreSource.includes("<ExploreTableClient targets={leaderboardTargets} loadError={rankingsLoadError} />"));
  assert.ok(!exploreSource.includes("ExploreMarketMovers"));
  assert.ok(!exploreSource.includes("ExploreTopRankings"));
  assert.ok(!exploreSource.includes("getExploreMarketMovers"));
  assert.equal((exploreSource.match(/getRipStatisticsTargets\(/g) || []).length, 1);
  assert.ok(exploreSource.includes("targets.filter(isPublicAnalyticsEligiblePokemonSet)"));
});

test("Rankings preserves its bounded layout and existing atmosphere", () => {
  assert.ok(exploreSource.includes("max-w-7xl"));
  assert.ok(exploreSource.includes("max-w-5xl"));
  assert.ok(/px-4[^\"]*sm:px-6[^\"]*lg:px-8/.test(exploreSource));
  assert.ok(exploreSource.includes('getExploreBackground("pokemon")'));
});

test("Market reuses the existing canonical market modules and one loader per data family", () => {
  assert.ok(marketSource.includes("<ExploreMarketMovers payload={moversPayload} />"));
  assert.ok(marketSource.includes("<ExploreTopRankings targets={targets} loadError={loadError} />"));
  assert.equal((marketSource.match(/getExploreMarketMovers\(\)/g) || []).length, 1);
  assert.equal((marketSource.match(/getRipStatisticsTargets\(/g) || []).length, 1);
  assert.ok(marketSource.includes("Promise.allSettled"));
  assert.ok(marketSource.includes("requestFailed: true"));
  assert.ok(marketSource.includes("filter(isPublicAnalyticsEligiblePokemonSet)"));
});
