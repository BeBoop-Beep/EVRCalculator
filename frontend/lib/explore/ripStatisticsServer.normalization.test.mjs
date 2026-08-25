import assert from "node:assert/strict";
import test from "node:test";
import { normaliseRipStatisticsPayload as normalisePayload } from "./ripStatisticsNormalizer.mjs";

test("productFamilyRankings survives RIP statistics normalization unchanged", () => {
  const rankings = { calculationRunId: "run-current", families: { booster_box: { products: [{ sealedProductId: "sku-1" }] } } };
  const normalized = normalisePayload({ targets: [], productFamilyRankings: rankings });
  assert.equal(normalized.productFamilyRankings, rankings);
  assert.equal(normalized.productFamilyRankings.families.booster_box.products.length, 1);
});

test("Overall rankings do not travel through RIP statistics normalization", () => {
  const normalized = normalisePayload({ targets: [], overallProductRankings: { cohorts: {} } });
  assert.equal(normalized.overallProductRankings, undefined);
});
