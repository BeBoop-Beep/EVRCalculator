import assert from "node:assert/strict";
import test from "node:test";
import {
  FEATURE_BEST_OPEN_PRICE,
  hasIndexFeatureAccess,
  resolveRankingsPlanAccess,
} from "./indexPlanAccess.mjs";

test("Best-Open Price is a dedicated Index Plus capability inherited by Premium", () => {
  assert.equal(FEATURE_BEST_OPEN_PRICE, "best_open_price");
  assert.equal(hasIndexFeatureAccess(null, FEATURE_BEST_OPEN_PRICE), false);
  assert.equal(hasIndexFeatureAccess("plus", FEATURE_BEST_OPEN_PRICE), true);
  assert.equal(hasIndexFeatureAccess("premium", FEATURE_BEST_OPEN_PRICE), true);
});

test("Rankings access exposes Best-Open independently through the central capability authority", () => {
  assert.equal(resolveRankingsPlanAccess(null).canViewBestOpenPrice, false);
  assert.equal(resolveRankingsPlanAccess({ index_plan: "plus" }).canViewBestOpenPrice, true);
  assert.equal(resolveRankingsPlanAccess({ index_plan: "premium" }).canViewBestOpenPrice, true);
});
