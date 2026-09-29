import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const setRip = read("./SetRipScoreLeaderboard.jsx");
const setMetric = read("./SetMetricRankingsTable.jsx");
const era = read("./EraRankings.jsx");
const shared = read("./RankingsScoreTable.jsx");
const lazy = read("./RankingsLazyClient.jsx");

test("all Set score tabs share table and exact search geometry", () => {
  for (const source of [setRip, setMetric]) {
    assert.match(source, /RankingsSearchInput/);
    assert.match(source, /RankingsScoreTable/);
    assert.match(source, /entity="Sets"/);
  }
  assert.match(read("./RankingsSearchInput.jsx"), /`Search \$\{entity\}…`/);
});

test("redesigned surfaces use benchmark-10 primitives and inline reference rows", () => {
  assert.doesNotMatch(`${setRip}${setMetric}${era}${shared}`, /BenchmarkScoreBadge/);
  assert.match(shared, /RankingsRipScoreBadge/);
  assert.match(era, /RankingsRipScoreBadge/);
  assert.match(era, /RankingsCompactScore/);
  assert.match(shared, /Pokémon Overall Average/);
  assert.match(era, /Pokémon Overall Average/);
});

test("scorecard fetches are entitlement-gated before cache or network access", () => {
  for (const loader of [lazy.slice(lazy.indexOf("const loadEra"), lazy.indexOf("const loadSets")), lazy.slice(lazy.indexOf("const loadSets"), lazy.indexOf("const warmProducts"))]) {
    assert.ok(loader.indexOf('if (!canViewRankingsIntelligence)') < loader.indexOf("sessionCache.peek"));
    assert.ok(loader.indexOf('authStatus !== "resolved" && authStatus !== "degraded"') < loader.indexOf("sessionCache.peek"));
  }
  assert.equal((lazy.match(/readRankingsScorecards\("set"/g) || []).length, 1);
  assert.equal((lazy.match(/readRankingsScorecards\("era"/g) || []).length, 1);
  assert.doesNotMatch(lazy, /readCurrentBenchmark/);
});
