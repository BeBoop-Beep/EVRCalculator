import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const lazy = read("./RankingsLazyClient.jsx");
const overview = read("./RankingsOverviewHighlights.jsx");
const page = read("../../app/Explore/page.js");
const overviewServer = read("../../lib/rankings/rankingsOverviewServer.js");
const products = read("./RankingsProductLensClient.jsx");
const hub = read("./CardRankingsHub.jsx");
const collector = read("./CardCollectorAppealRankings.jsx");
const chase = read("./CardChaseEfficiencyRankings.jsx");
const productReadPath = fs.readFileSync(new URL("../../lib/rankings/productRankingsClient.mjs", import.meta.url), "utf8");

test("Overview cards use the server-seeded v2 public authority", () => {
  assert.match(overview, /overview\?\.topSet/);
  assert.match(page, /getRankingsOverview\(\)/);
  assert.match(overviewServer, /\/tcgs\/pokemon\/rankings\/overview-v2/);
  assert.doesNotMatch(overview, /readBenchmarkOverviewHeadlines/);
  assert.doesNotMatch(overview, /setsState|eraState|readCurrentBenchmark/);
  assert.doesNotMatch(lazy, /<RankingsOverviewHighlights[\s\S]{0,250}(setsState|eraState)=/);
});

test("Products uses one lazy authority per active split view", () => {
  assert.match(products, /readProductRankings\(target/);
  assert.match(productReadPath, /\/api\/explore\/product-rankings\/scores/);
  assert.match(productReadPath, /\/api\/explore\/product-rankings\/economics/);
  assert.match(productReadPath, /`products:\$\{view\}`/);
  assert.doesNotMatch(lazy, /loadProductRankingsAuthorities|products:full_market/);
  assert.doesNotMatch(products, /product-rankings\/overall|rip-benchmark\/current-batch/);
});

test("first Card request waits for auth reconciliation and retries on status completion", () => {
  assert.match(lazy, /authStatus=\{authStatus\}/);
  assert.match(hub, /authStatus=\{authStatus\}/g);
  for (const source of [collector, chase]) {
    assert.match(source, /if \(authStatus === "resolving"\) return/);
    assert.match(source, /authStatus[\s\S]{0,100}entitled/);
  }
});

test("Set, Era, and Product refreshes use the tested last-good transition contract", () => {
  assert.match(lazy, /beginLastGoodRefresh\(current, isRenderableEraState\)/);
  assert.match(lazy, /failLastGoodRefresh\(current, error, isRenderableEraState/);
  assert.match(lazy, /beginLastGoodRefresh\(current, isRenderableSetState\)/);
  assert.match(lazy, /failLastGoodRefresh\(current, error, isRenderableSetState/);
  assert.match(products, /beginLastGoodRefresh\(current\[target\], renderable\)/);
  assert.match(products, /failLastGoodRefresh\(current\[target\], error, renderable/);
});
