import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { bestOpenThresholdCopy, bestOpenStrategyCopy, bestOpenUnavailableCopy } from "./bestOpenPriceDetailModel.mjs";
const read = (url) => fs.readFileSync(new URL(url, import.meta.url), "utf8");
const card = read("./BestOpenPriceCard.jsx");
const detail = read("./SealedProductDetailClient.jsx");

test("Product Detail independently gates Best-Open and keeps full-market context", () => {
  assert.match(detail, /bestOpenEntitled && detail\.rip\?\.bestOpenPrice/);
  assert.match(detail, /FEATURE_BEST_OPEN_PRICE/);
  assert.match(card, /Best-Open Price · Full Market/);
  assert.doesNotMatch(card, /overallRipLeaderScore|financialRipLeaderScore|computeOverall|RIP Score/);
});
test("ranking-source price and live tracked price remain visibly distinct", () => {
  for (const text of ["Ranking source price", "Current tracked price", "sourceUnitPrice", "sourceMarketDate", "price comparison only", "remains bound to the Full Market cohort dated"]) assert.ok(card.includes(text));
  assert.match(card, /market\?\.currentPrice/);
  assert.match(card, /market\?\.marketDate/);
});
test("threshold copy claims only the tested price, not every cheaper price", () => {
  for (const status of ["resolved_below_market", "current_number_one_with_headroom"]) {
    const copy = bestOpenThresholdCopy({status,bestOpenPrice:13.23});
    assert.match(copy, /At \$13\.23 per unit/);
    assert.match(copy, /#1/);
    assert.doesNotMatch(copy, /or lower|up to|no matter what/);
  }
  assert.equal(bestOpenThresholdCopy({bestOpenPrice:null}),null);
});
test("whole-unit budget and quantity are explicit, not a one-unit promise", () => {
  const copy=bestOpenStrategyCopy({sourceFullMarketBudget:1350,thresholdQuantity:102});
  assert.match(copy,/102 whole units/);
  assert.match(copy,/\$1,350\.00/);
  assert.match(copy,/not a one-unit ranking/);
  assert.match(card,/bestOpenStrategyCopy\(bestOpen\)/);
});
test("missing publication does not pretend a running job was observed", () => {
  for(const reason of ["stale_source_publication","no_published_snapshot","incomplete_snapshot_rows"]) {
    const copy=bestOpenUnavailableCopy(reason);
    assert.match(copy,/not been published/);
    assert.doesNotMatch(copy,/refreshing|running|in progress/);
  }
});
test("Product Detail never fetches or calculates a threshold in the browser", () => {
  assert.doesNotMatch(card, /fetch\(|ExactBestOpenPriceSearch|PreparedFinancialRipDistribution|quantity_price_interval/);
});
