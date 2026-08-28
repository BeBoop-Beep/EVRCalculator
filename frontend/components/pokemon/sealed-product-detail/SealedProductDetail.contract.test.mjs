import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const page = read("../../../app/sealed-products/[productId]/page.js");
const client = read("./SealedProductDetailClient.jsx");
const market = read("./SealedProductMarketPanel.jsx");
const rip = read("./ProductRipSection.jsx");
const comparisons = read("./ProductComparisonSection.jsx");

test("route stays thin, real, canonical, and has availability-aware SEO", () => {
  assert.match(page, /getSealedProductDetailServer/);
  assert.match(page, /SealedProductDetailClient/);
  assert.doesNotMatch(page, /marketDataLoader|MarketModule/);
  assert.match(page, /RIP & Market Analysis \| inDex/);
  assert.match(page, /detail\.rip\.available/);
  assert.match(page, /buildSealedProductHref/);
});

test("hero mirrors current Card Detail atmosphere, navigation, and image states", () => {
  assert.match(client, /PageArtworkAtmosphere/);
  assert.match(client, /data-product-set-ambient-artwork/);
  assert.match(client, /max-w-\[1600px\]/);
  assert.match(client, /max-w-\[1400px\]/);
  assert.match(client, /buildProductParentSetHref/);
  assert.match(client, /← Back to/);
  assert.match(client, /data-product-image/);
  assert.match(client, /data-product-image-placeholder/);
  assert.match(client, /Product image unavailable/);
  assert.match(client, /detail\.product\.name/);
});

test("sealed market is public, has all approved windows, and no card mode toggle", () => {
  assert.ok(client.indexOf("SealedProductMarketPanel") < client.indexOf("detail.rip.available ?"));
  for (const token of ["1D", "7D", "30D", "3M", "6M", "1Y", "lifetime"]) assert.match(read("./productDetailModel.mjs"), new RegExp(`"${token}"`));
  assert.doesNotMatch(market, /Raw|Graded|Asset mode/);
  assert.match(market, /Price history is not available for this product yet/);
  assert.match(market, /sealed market price/);
});

test("Product RIP uses Plus entitlement and only leader-normalized ranking fields", () => {
  assert.match(client, /hasIndexPlusAccess\(user\?\.index_plan\)/);
  assert.match(client, /entitled \? <><ProductRipSection/);
  assert.match(rip, /rip\.overallRipLeaderScore/);
  assert.match(rip, /rip\.financialRipLeaderScore/);
  assert.match(rip, /rip\.publicTier/);
  assert.match(rip, /rip\.familyRank/);
  assert.match(rip, /rip\.familySize/);
  assert.match(rip, /formatPublicRipScore/);
  assert.doesNotMatch(rip, /of 138|Overall Rank|overallRipAbsoluteScore/);
});

test("Opening Outcome Profile has exactly the six approved primary measurements", () => {
  const keys = [...rip.matchAll(/\["(?:Expected Value|Typical Opening|Chance to Recover Cost|Entertainment Cost|Realistic Upside|Jackpot Upside)", "([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(keys, ["expectedValue", "medianValue", "chanceToRecoverCost", "entertainmentCost", "p95Value", "p99Value"]);
  assert.match(rip, /gross modeled market value/);
  assert.match(rip, /fees, shipping, liquidation friction, bid\/ask spread, and grading/);
});

test("comparisons and final CTA stay canonical without duplicate Set RIP metrics", () => {
  assert.match(comparisons, /comparisonRows\(detail, mode\)/);
  assert.match(comparisons, /buildSealedProductHref\(row\)/);
  assert.match(comparisons, /This Set/);
  assert.match(comparisons, /Same Format/);
  assert.match(client, /data-set-rip-cta/);
  assert.match(client, /href=\{setHref\}/);
  assert.doesNotMatch(client, /Set Overall RIP|Set Financial RIP|Set Collector Appeal/);
});
