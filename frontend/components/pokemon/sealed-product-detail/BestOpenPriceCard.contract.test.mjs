import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (url) => fs.readFileSync(new URL(url, import.meta.url), "utf8");
const card = read("./BestOpenPriceCard.jsx");
const detail = read("./SealedProductDetailClient.jsx");

test("Product Detail renders Best-Open as a separate Plus-gated Full Market card", () => {
  assert.match(detail, /entitled && detail\.rip\?\.bestOpenPrice/);
  assert.match(detail, /<BestOpenPriceCard/);
  assert.match(card, /Best-Open Price · Full Market/);
  assert.doesNotMatch(card, /overallRipLeaderScore|financialRipLeaderScore|computeOverall|RIP Score/);
});

test("the card keeps published ranking price and current tracked price visibly separate", () => {
  assert.match(card, /Ranking source price/);
  assert.match(card, /Current tracked price/);
  assert.match(card, /sourceUnitPrice/);
  assert.match(card, /market\?\.currentPrice/);
  assert.match(card, /sourceMarketDate/);
  assert.match(card, /market\?\.marketDate/);
  assert.match(card, /price comparison only/);
  assert.match(card, /remains bound to the Full Market cohort dated/);
});

test("leader and challenger semantics match the exact threshold contract", () => {
  assert.match(card, /current_number_one_with_headroom/);
  assert.match(card, /remained #1 up to/);
  assert.match(card, /would reach #1/);
  assert.match(card, /highest acquisition price at which this product would rank #1/);
  assert.match(card, /every other product at that publication's price/);
});

test("stale prepared data is shown as refreshing rather than as an old threshold", () => {
  assert.match(card, /stale_source_publication/);
  assert.match(card, /refreshing for the latest Full Market ranking/);
});

test("Product Detail does not fetch or score Best-Open in the browser", () => {
  assert.doesNotMatch(card, /fetch\(/);
  assert.doesNotMatch(card, /ExactBestOpenPriceSearch|PreparedFinancialRipDistribution|quantity_price_interval/);
});
