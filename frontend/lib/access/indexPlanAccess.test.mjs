import assert from "node:assert/strict";
import test from "node:test";

import {
  hasIndexPlusAccess,
  hasIndexPremiumAccess,
  normalizeIndexPlan,
  resolveRankingsPlanAccess,
} from "./indexPlanAccess.mjs";

const cases = [
  [null, null, false, false],
  ["plus", "plus", true, false],
  ["premium", "premium", true, true],
  ["unknown", null, false, false],
];

for (const [input, normalized, plus, premium] of cases) {
  test(`Index plan access for ${String(input)}`, () => {
    assert.equal(normalizeIndexPlan(input), normalized);
    assert.equal(hasIndexPlusAccess(input), plus);
    assert.equal(hasIndexPremiumAccess(input), premium);
  });
}

test("Rankings unlock for Plus and Premium plans only", () => {
  assert.equal(resolveRankingsPlanAccess({ index_plan: "premium" }).canViewRankingsIntelligence, true);
  assert.equal(resolveRankingsPlanAccess({ index_plan: "plus" }).canViewRankingsIntelligence, true);
  assert.equal(resolveRankingsPlanAccess({ index_plan: null }).canViewRankingsIntelligence, false);
  assert.equal(resolveRankingsPlanAccess(null).canViewRankingsIntelligence, false);
});

test("a subsequently resolved Premium user replaces an initially locked auth state", () => {
  const initialAccess = resolveRankingsPlanAccess(null);
  const hydratedAccess = resolveRankingsPlanAccess({ index_plan: "premium" });
  assert.equal(initialAccess.canViewRankingsIntelligence, false);
  assert.equal(hydratedAccess.canViewRankingsIntelligence, true);
});
