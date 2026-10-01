import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const setRip = read("./SetRipScoreLeaderboard.jsx");
const era = read("./EraRankings.jsx");
const shared = read("./BenchmarkEntityScoreTable.jsx");
const lazy = read("./RankingsLazyClient.jsx");

test("Set and Era share ONE unified table and exact search geometry", () => {
  for (const source of [setRip, era]) assert.match(source, /BenchmarkEntityScoreTable/);
  assert.match(setRip, /RankingsSearchInput/);
  assert.match(setRip, /entity="Sets"/);
  assert.match(read("./RankingsSearchInput.jsx"), /`Search \$\{entity\}…`/);
});

test("the unified table uses benchmark-10 primitives and a single pinned reference row", () => {
  assert.doesNotMatch(`${setRip}${era}${shared}`, /BenchmarkScoreBadge/);
  assert.match(shared, /RankingsRipScoreBadge/);
  assert.match(shared, /RankingsBenchmarkComponentScore/);
  assert.match(shared, /Pokémon Overall Average/);
  assert.equal((shared.match(/<tr data-rankings-reference-row/g) || []).length, 1);
});

test("Era and Set each issue exactly one public headline read; paid reads live in one shared hook", () => {
  assert.equal((lazy.match(/readPublicRankingsHeadlines\("set"/g) || []).length, 1);
  assert.equal((lazy.match(/readPublicRankingsHeadlines\("era"/g) || []).length, 1);
  assert.doesNotMatch(lazy, /readCurrentBenchmark|readRankingsScorecards/);
  const hook = read("../../lib/rankings/usePaidScorecards.js");
  assert.equal((hook.match(/readRankingsScorecards\(/g) || []).length, 1);
  assert.match(hook, /if \(!entitled \|\| !sessionCache\)/);
});
