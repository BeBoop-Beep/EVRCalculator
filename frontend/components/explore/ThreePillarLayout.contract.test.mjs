import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (url) => fs.readFileSync(new URL(url, import.meta.url), "utf8");
const setRip = read("./RipDecisionPage.jsx");
const analysis = read("../pokemon/set-page/Analysis/PokemonSetAnalysisClient.jsx");
const product = read("../pokemon/sealed-product-detail/ProductRipSection.jsx");
const productRankings = read("./RankingsProductLensClient.jsx");
const setRankings = read("./ExploreTableClient.jsx");

test("mounted Set RIP presents Overall above three peer pillar cards", () => {
  assert.ok(setRip.indexOf("metrics.overall") < setRip.indexOf("data-three-pillar-summary"));
  assert.match(setRip, /styles\.pillarCardRow/);
  for (const destination of ["set-detail-financial-rip", "set-detail-chase-accessibility", "set-detail-collector-appeal"]) assert.ok(setRip.includes(destination));
  assert.doesNotMatch(setRip, /data-market-based-summary-group/);
});

test("Chase headline uses publicScore while raw Accessibility stays in details", () => {
  assert.match(setRip, /chase\.publicScore/);
  assert.match(setRip, /Raw Accessibility:/);
  assert.match(setRip, /chaseAccessibility\.rank/);
});

test("Set Analysis exposes six destinations and no Market-Based section", () => {
  for (const destination of ["overview", "simulation", "financial-rip", "chase-accessibility", "collector-appeal", "market-context"]) assert.ok(analysis.includes(`"${destination}"`));
  assert.doesNotMatch(analysis, /activeSection === "market-based"/);
  assert.match(analysis, /requestedSectionRaw === "market-based" \? "financial-rip"/);
});

test("Product RIP uses the peer hierarchy and preserves inheritance labels", () => {
  assert.match(product, /data-three-pillar-summary="product"/);
  assert.match(product, /This product/);
  assert.match(product, /Parent set/);
  assert.match(product, /chase\.publicScore/);
});

test("active ranking tables have peer columns without a spanning Market-Based header", () => {
  for (const source of [productRankings, setRankings]) {
    assert.ok(source.includes("Financial RIP") && source.includes("Chase Accessibility") && source.includes("Collector Appeal"));
    assert.doesNotMatch(source, /data-market-based-header/);
  }
});
