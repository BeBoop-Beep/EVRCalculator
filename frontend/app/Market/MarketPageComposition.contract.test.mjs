// The Pokémon Market page composition.
//
// Locked information hierarchy: header → Market Overview → Pokémon Market
// Performance → 7D Market Movers → Set Value Rankings. The two modules that
// already existed must survive the redesign unchanged, and a missing Market
// Overview must not suppress either of them.

import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const here = path.dirname(new URL(import.meta.url).pathname.slice(1));
const read = (relative) => fs.readFileSync(path.resolve(here, relative), "utf8");

const page = read("page.js");
const rankings = read("../../components/explore/ExploreTopRankings.jsx");
const movers = read("../../components/explore/ExploreMarketMovers.jsx");

test("the page header carries the locked copy", () => {
  assert.match(page, />Pokémon Market</);
  assert.match(page, /Track the value and performance of the Pokémon card market\./);
  assert.doesNotMatch(page, /What is happening with Pokémon prices\?/);
});

test("sections render in the locked order", () => {
  const order = ["PokemonMarketOverview", "PokemonMarketPerformance", "ExploreMarketMovers", "ExploreTopRankings"];
  const positions = order.map((name) => page.indexOf(`<${name}`));
  assert.ok(positions.every((position) => position > 0), `every section must render: ${JSON.stringify(positions)}`);
  assert.deepEqual([...positions].sort((a, b) => a - b), positions, "sections must appear in the locked order");
});

test("Market Overview is read from the snapshot, never computed in the frontend", () => {
  assert.match(page, /resolveMarketOverview\(setValuePayload\)/);
  assert.match(page, /setValuePayload\?\.sets/);
  // No local arithmetic on market figures.
  assert.doesNotMatch(page, /basketValue\s*[-+*/]/);
  assert.doesNotMatch(page, /indexValue\s*[-+*/]/);
});

test("the page still serves exactly two global snapshots in parallel", () => {
  assert.match(page, /Promise\.allSettled/);
  assert.match(page, /getExploreSetValueMarket\(\)/);
  assert.match(page, /getExploreMarketMovers\(\)/);
  // The Market Overview rides the SAME set-value snapshot — no third request.
  assert.equal((page.match(/await fetch\(/g) || []).length, 0);
  assert.equal((page.match(/getExploreSetValueMarket\(\)/g) || []).length, 1);
});

test("Movers and Set Value Rankings render regardless of Market Overview availability", () => {
  // Both receive their own payload/props, neither is nested inside an
  // overview-conditional branch.
  assert.match(page, /<ExploreMarketMovers payload=\{moversPayload\} \/>/);
  assert.match(page, /<ExploreTopRankings targets=\{targets\} loadError=\{loadError\} \/>/);
  const overviewIndex = page.indexOf("<PokemonMarketOverview");
  const conditionalOverview = /\{overview \?[\s\S]*<ExploreTopRankings/.test(page);
  assert.ok(overviewIndex > 0);
  assert.equal(conditionalOverview, false, "the rankings must not be gated on the overview");
});

test("Set Value Rankings keeps its existing behaviour", () => {
  assert.match(rankings, /MOBILE_PREVIEW_LIMIT = 5/);
  assert.match(rankings, /Show \$\{hiddenCount\} more/);
  assert.match(rankings, /Show less/);
  assert.match(rankings, /MarketWindowSelector/);
  assert.match(rankings, /MarketSparkline/);
  // Ranked by current Set Value, not by a market index.
  assert.match(rankings, /sort\(\(a, b\) => b\.value - a\.value/);
  assert.doesNotMatch(rankings, /indexValue/);
});

test("Movers still renders the current mover payload through the existing ticker", () => {
  assert.match(movers, /SevenDayMarketMoversTicker/);
  assert.match(movers, /entry=\{payload\?\.marketMovers\}/);
  assert.match(movers, /scope="explore" thumbnailSize="medium"/);
  assert.match(movers, />7D Market Movers</);
});

test("metadata describes the page without claiming forecasts or capitalization", () => {
  // Scoped to the metadata literal: the surrounding comment legitimately names
  // the vocabularies the page refuses to use.
  const metadata = page.slice(page.indexOf("buildRouteMetadata({"), page.indexOf("export default"));
  assert.match(metadata, /Pokémon Market Index, Trends & Set Values — inDex/);
  assert.match(metadata, /Track Pokémon card-market performance, Raw Card and Top Chase indexes, market movers, and current set values\./);
  assert.doesNotMatch(metadata, /market cap/i);
  assert.doesNotMatch(metadata, /forecast|prediction|investment advice|live trading/i);
});
