import assert from "node:assert/strict";
import test from "node:test";

import {
  FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS,
  INDEX_PLAN_LABELS,
  hasIndexPlusAccess,
  hasIndexPremiumAccess,
  resolveMarketExplorerPlanAccess,
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

// --- Market Explorer ladder -------------------------------------------------

test("Market Explorer has three levels and Premium inherits Plus", () => {
  const basic = resolveMarketExplorerPlanAccess({ index_plan: null });
  assert.equal(basic.accessMode, "basic");
  assert.equal(basic.canUsePreparedMarketIntelligence, false);
  assert.equal(basic.canBuildCustomMarkets, false);

  const plus = resolveMarketExplorerPlanAccess({ index_plan: "plus" });
  assert.equal(plus.accessMode, "plus");
  assert.equal(plus.canUsePreparedMarketIntelligence, true);
  assert.equal(plus.canBuildCustomMarkets, false);

  const premium = resolveMarketExplorerPlanAccess({ index_plan: "premium" });
  assert.equal(premium.accessMode, "premium");
  assert.equal(premium.canUsePreparedMarketIntelligence, true);
  assert.equal(premium.canBuildCustomMarkets, true);
});

test("signing in alone unlocks nothing", () => {
  // The correction this ladder exists to encode: authentication identifies a
  // user, PLAN ENTITLEMENT decides access. An authenticated account with no
  // paid plan has exactly the feature access an anonymous visitor has.
  const anonymous = resolveMarketExplorerPlanAccess(null);
  const authenticatedBasic = resolveMarketExplorerPlanAccess({ id: "u1", index_plan: null });
  assert.equal(anonymous.canUsePreparedMarketIntelligence, authenticatedBasic.canUsePreparedMarketIntelligence);
  assert.equal(anonymous.canBuildCustomMarkets, authenticatedBasic.canBuildCustomMarkets);
  assert.equal(anonymous.accessMode, authenticatedBasic.accessMode);
  // ...but the two are still distinguishable, because the upgrade path differs.
  assert.equal(anonymous.isAuthenticated, false);
  assert.equal(authenticatedBasic.isAuthenticated, true);
});

test("an unrecognised plan string fails closed", () => {
  for (const plan of ["pro", "PLUS ", "", "free", 7, {}]) {
    const access = resolveMarketExplorerPlanAccess({ index_plan: plan });
    if (plan === "PLUS ") {
      // Normalization trims and lowercases, so this IS Plus.
      assert.equal(access.canUsePreparedMarketIntelligence, true);
      continue;
    }
    assert.equal(access.canUsePreparedMarketIntelligence, false, `${String(plan)} must not grant access`);
    assert.equal(access.canBuildCustomMarkets, false);
  }
});

test("the plan hierarchy is not duplicated — the ladder reuses the shared helpers", () => {
  for (const plan of [null, "plus", "premium"]) {
    const access = resolveMarketExplorerPlanAccess({ index_plan: plan });
    assert.equal(access.canUsePreparedMarketIntelligence, hasIndexPlusAccess(plan));
    assert.equal(access.canBuildCustomMarkets, hasIndexPremiumAccess(plan));
  }
});

test("plan labels use the exact product language", () => {
  assert.equal(INDEX_PLAN_LABELS.plus, "Index Plus");
  assert.equal(INDEX_PLAN_LABELS.premium, "Index Premium");
});
