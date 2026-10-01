import test from "node:test";
import assert from "node:assert/strict";
import { activityChartDto, MARKET_ACTIVITY_SUPPORTED_WINDOWS } from "./marketActivityChartAdapter.mjs";

test("chart adapter preserves sparse dates and distinct sales/supply units", () => {
  const dto = activityChartDto({
    activityGenerationId: "g", roster: { rosterRevision: { generationId: "r" } },
    coverage: { rosterDenominator: 174, notCollected: 155 },
    totals: { observedConstituentCount: 19, observedSaleCountLowerBound: 1583 },
    series: {
      asOf: "2026-09-30", storage: "SPARSE_DAILY",
      zeroRule: "ABSENT_DATE_IS_ZERO_ONLY_INSIDE_PROVEN_SPAN",
      sales: { source: "pkmnprices_ebay_sold", counts: { points: [
        { date: "2026-09-01", observedCount: 2, proofState: "OBSERVED_ONLY" },
        { date: "2026-09-03", observedCount: 0, proofState: "PROVEN_ZERO" },
      ] } },
      supply: { source: "pkmnprices_tcgplayer_listings", aggregation: "LOWER_BOUND",
        listings: { points: [{ date: "2026-09-23", value: 38 }] },
        quantity: { points: [{ date: "2026-09-23", value: 40 }] } },
    },
  });
  assert.deepEqual(dto.sales.points.map((point) => point.date), ["2026-09-01", "2026-09-03"]);
  assert.equal(dto.sales.points[1].observedSoldCount, 0);
  assert.deepEqual(dto.supply.points.map((point) => [point.listingOfferCount, point.listedQuantity]), [[38, 40]]);
  assert.equal(dto.supply.points[0].observedAt, null, "date-only authority must stay date-only");
  assert.equal(dto.supply.points[0].state, "HISTORICAL_OBSERVATION");
  assert.deepEqual(dto.supportedWindows, MARKET_ACTIVITY_SUPPORTED_WINDOWS);
});

test("supply uses the date union without zero-fill or midnight synthesis", () => {
  const dto = activityChartDto({ series: { supply: {
    listings: { points: [
      { date: "2026-09-20", value: 0, contributingConstituents: 1 },
      { date: "2026-09-23", value: 38, contributingConstituents: 2 },
    ] },
    quantity: { points: [
      { date: "2026-09-20", value: 4, contributingConstituents: 1 },
      { date: "2026-09-25", value: 40, contributingConstituents: 2 },
    ] },
  } } });
  assert.deepEqual(dto.supply.points, [
    { date: "2026-09-20", listingOfferCount: 0, listedQuantity: 4,
      contributingConstituents: 1, source: null, quantityProvenance: null,
      observedAt: null, currentUntil: null, state: "HISTORICAL_OBSERVATION" },
    { date: "2026-09-23", listingOfferCount: 38, listedQuantity: null,
      contributingConstituents: 2, source: null, quantityProvenance: null,
      observedAt: null, currentUntil: null, state: "HISTORICAL_OBSERVATION" },
    { date: "2026-09-25", listingOfferCount: null, listedQuantity: 40,
      contributingConstituents: 2, source: null, quantityProvenance: null,
      observedAt: null, currentUntil: null, state: "HISTORICAL_OBSERVATION" },
  ]);
  assert.equal(JSON.stringify(dto).includes("T00:00:00Z"), false);
});
