import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const lazy = read("./RankingsLazyClient.jsx");
const overview = read("./RankingsOverviewHighlights.jsx");
const products = read("./RankingsProductLensClient.jsx");
const hub = read("./CardRankingsHub.jsx");
const collector = read("./CardCollectorAppealRankings.jsx");
const chase = read("./CardChaseEfficiencyRankings.jsx");

test("Overview headlines use only the narrow public authority", () => {
  assert.match(overview, /readBenchmarkOverviewHeadlines\(\)/);
  assert.doesNotMatch(overview, /setsState|eraState|readCurrentBenchmark/);
  assert.doesNotMatch(lazy, /<RankingsOverviewHighlights[\s\S]{0,250}(setsState|eraState)=/);
});

test("default All Products and its warm path share the dedicated Full Market contract", () => {
  for (const source of [lazy, products]) {
    assert.match(source, /\/api\/explore\/rankings\/lens\?lens=products/);
    assert.match(source, /\/api\/explore\/product-rankings\/overall\?budget=full_market/);
    assert.match(source, /sessionCache\.request\("products:full_market"/);
  }
  assert.doesNotMatch(products, /normalizeOverallProductResult\(payload\.overallProductRankings\)/);
  assert.doesNotMatch(lazy, /normalizeOverallProductResult\(payload\.overallProductRankings\)/);
  assert.match(products, /\[\.\.\.familyProducts, \.\.\.fullMarketProducts\]/);
});

test("first Card request waits for auth reconciliation and retries on status completion", () => {
  assert.match(lazy, /authStatus=\{authStatus\}/);
  assert.match(hub, /authStatus=\{authStatus\}/g);
  for (const source of [collector, chase]) {
    assert.match(source, /if \(authStatus === "resolving"\) return/);
    assert.match(source, /authStatus[\s\S]{0,100}entitled/);
  }
});

test("Set and Era transient errors preserve the previous visible payload", () => {
  assert.match(lazy, /setEraState\(\(current\) => \(\{ \.\.\.current, status: "error"/);
  assert.match(lazy, /setSetsState\(\(current\) => \(\{ \.\.\.current, status: "error"/);
});
