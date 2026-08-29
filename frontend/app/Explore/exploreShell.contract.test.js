const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const exploreSource = fs.readFileSync(path.resolve(__dirname, "page.js"), "utf8");
const rankingsSource = fs.readFileSync(path.resolve(__dirname, "../Rankings/page.js"), "utf8");
const marketSource = fs.readFileSync(path.resolve(__dirname, "../Market/page.js"), "utf8");

test("Rankings is the public name and /Explore remains backwards compatible", () => {
  // The public question is visible before the rankings data.
  assert.ok(exploreSource.includes('<header className="mb-5 w-full">'));
  assert.ok(exploreSource.includes("Pokémon RIP Rankings"));
  assert.ok(rankingsSource.includes('export { default } from "../Explore/page"'));
});

test("Rankings — not /Explore — owns the canonical identity of the leaderboard", () => {
  // /Explore permanently redirects to /Rankings, so a metadata object left in
  // app/Explore/page.js would put a live route's title, canonical and og:url in
  // a directory that no longer answers requests.
  assert.ok(!/export const metadata\b/.test(exploreSource), "/Explore must not declare metadata");
  assert.ok(rankingsSource.includes('title: "Best Pokémon Sets to Rip Right Now — inDex"'));
  assert.ok(rankingsSource.includes('path: "/Rankings"'));
  assert.ok(rankingsSource.includes('buildRouteMetadata'));
});

test("Rankings contains one lazy canonical leaderboard with all five views", () => {
  assert.ok(exploreSource.includes("<RankingsLazyClient"));
  assert.ok(!exploreSource.includes("ExploreMarketMovers"));
  assert.ok(!exploreSource.includes("SetMarketExplorer"));
  assert.ok(!exploreSource.includes("getExploreMarketMovers"));
  assert.equal((exploreSource.match(/getRipStatisticsTargets\(/g) || []).length, 0);
  assert.ok(exploreSource.includes("getPokemonSetRouteDirectory"));
});

test("Rankings preserves its bounded layout and existing atmosphere", () => {
  assert.ok(exploreSource.includes("max-w-7xl"));
  assert.ok(exploreSource.includes("md:max-w-[100rem]"));
  assert.ok(/px-4[^\"]*sm:px-6[^\"]*lg:px-8/.test(exploreSource));
  assert.ok(exploreSource.includes('getExploreBackground("pokemon")'));
});

test("Market reuses the existing canonical market modules and one loader per data family", () => {
  assert.ok(marketSource.includes("<ExploreMarketMovers payload={moversPayload} />"));
  assert.ok(marketSource.includes("<SetMarketExplorer targets={targets} loadError={loadError} />"));
  assert.equal((marketSource.match(/getExploreMarketMovers\(\)/g) || []).length, 1);
  assert.equal((marketSource.match(/getExploreSetValueMarket\s*\(/g) || []).length, 1);
  assert.ok(marketSource.includes("Promise.allSettled"));
  assert.ok(marketSource.includes("requestFailed: true"));
  assert.ok(marketSource.includes("setValuePayload?.sets"));
});
