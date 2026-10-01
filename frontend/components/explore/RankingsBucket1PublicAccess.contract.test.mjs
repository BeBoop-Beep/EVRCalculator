import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const lazy = read("./RankingsLazyClient.jsx");
const products = read("./RankingsProductLensClient.jsx");
const sets = read("./SetRankingsHub.jsx");
const pack = read("./SetPackMetrics.jsx");

test("anonymous Era and Set headlines use only the public client", () => {
  assert.match(lazy, /readPublicRankingsHeadlines\("era"/);
  assert.match(lazy, /readPublicRankingsHeadlines\("set"/);
  assert.doesNotMatch(lazy.slice(lazy.indexOf("const loadEra"), lazy.indexOf("const loadSets")), /readRankingsScorecards/);
});

test("paid Set component cells retain a separate, entitlement-gated scorecards read", () => {
  const leaderboard = fs.readFileSync(new URL("./SetRipScoreLeaderboard.jsx", import.meta.url), "utf8");
  const hook = fs.readFileSync(new URL("../../lib/rankings/usePaidScorecards.js", import.meta.url), "utf8");
  assert.match(leaderboard, /usePaidScorecards\("set"/);
  assert.match(hook, /readRankingsScorecards\(entityType/);
  assert.match(hook, /if \(!entitled \|\| !sessionCache\)/);
});

test("Set Pack Economics preview exposes cost and locks protected component cells", () => {
  assert.match(sets, /readPublicPackEconomicsPreview/);
  assert.match(pack, /key === "averagePackCostPerPack"/);
  assert.match(pack, /aria-label="Requires Index Plus"/);
  assert.match(pack, /data-pack-economics-entitled=\{entitled/);
});

test("anonymous Products load the independent catalogue without paid ranking reads", () => {
  assert.match(products, /readPublicProductCatalogue\(\{ sessionCache \}\)/);
  assert.match(products, /publicMode \? catalogue\.contract\?\.rows/);
  assert.match(products, /String\(a\.productName \|\| ""\)\.localeCompare/);
});

test("anonymous Product Scores and Economics render ordinary locked cells", () => {
  assert.match(products, /function PublicScoresTable/);
  assert.match(products, /function PublicEconomicsTable/);
  assert.match(products, /<LockedCell \/>/);
  assert.doesNotMatch(products, /PlanLock/);
});

test("Product type controls and search remain backed by catalogue rows", () => {
  assert.match(products, /productFamilyOptions\(familyRows\)/);
  assert.match(products, /filterProductRows\(rawRows, \{ query, family \}\)/);
  assert.match(products, /searchLabel="Search Products"/);
});

test("downgrade clears paid Product and Set state while public rows remain independent", () => {
  assert.match(products, /if \(!canViewRankingsIntelligence\) setStates/);
  assert.match(sets, /if \(!canViewRankingsIntelligence\) setPackState/);
  assert.match(fs.readFileSync(new URL("../../lib/rankings/paidScorecardVisibility.mjs", import.meta.url), "utf8"), /Boolean\(entitled\) && identity != null && state\?\.identity === identity/);
  assert.match(lazy, /publicScorecards=\{visibleSetsState\.scorecards\}/);
});
