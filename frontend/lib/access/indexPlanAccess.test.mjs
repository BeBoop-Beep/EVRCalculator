import assert from "node:assert/strict";
import test from "node:test";

import {
  FEATURE_CARD_CHASE_EFFICIENCY,
  FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS,
  INDEX_PLAN_LABELS,
  hasIndexPlusAccess,
  hasIndexPremiumAccess,
  hasIndexFeatureAccess,
  evaluateMarketQueryAccess,
  resolveMarketExplorerPlanAccess,
  normalizeIndexPlan,
  resolveRankingsPlanAccess,
} from "./indexPlanAccess.mjs";

test("Card Chase Efficiency is Premium-only", () => {
  assert.equal(FEATURE_CARD_CHASE_EFFICIENCY, "card_chase_efficiency");
  assert.equal(hasIndexFeatureAccess(null, FEATURE_CARD_CHASE_EFFICIENCY), false);
  assert.equal(hasIndexFeatureAccess("plus", FEATURE_CARD_CHASE_EFFICIENCY), false);
  assert.equal(hasIndexFeatureAccess("premium", FEATURE_CARD_CHASE_EFFICIENCY), true);
});

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
  assert.equal(plus.canBuildCustomMarkets, true);
  assert.equal(plus.canBuildSingleAxisMarket, true);
  assert.equal(plus.canBuildCompoundMarket, false);

  const premium = resolveMarketExplorerPlanAccess({ index_plan: "premium" });
  assert.equal(premium.accessMode, "premium");
  assert.equal(premium.canUsePreparedMarketIntelligence, true);
  assert.equal(premium.canBuildCustomMarkets, true);
  assert.equal(premium.canBuildCompoundMarket, true);
  assert.equal(premium.canUseCustomRankedComposition, true);
});

test("query access counts scope and segment axes and reserves ranking for Premium", () => {
  const scope = { eraIds: ["sv"], setIds: ["tef"], segmentIds: [], mode: "all" };
  assert.deepEqual(evaluateMarketQueryAccess("plus", scope).activeFilterAxes, ["scope"]);
  assert.equal(evaluateMarketQueryAccess("plus", scope).allowed, true);
  const compound = { ...scope, segmentIds: ["sir"] };
  assert.equal(evaluateMarketQueryAccess("plus", compound).allowed, false);
  assert.equal(evaluateMarketQueryAccess("premium", compound).allowed, true);
  assert.equal(evaluateMarketQueryAccess("plus", { ...scope, mode: "chase" }).allowed, false);
});

test("Pass 3 axes mirror backend packaging", () => {
  assert.equal(evaluateMarketQueryAccess("plus", { priceSegmentIds: ["premium"], mode: "all" }).allowed, true);
  assert.equal(evaluateMarketQueryAccess("plus", { releaseAgeCohortIds: ["new"], mode: "all" }).allowed, true);
  assert.equal(evaluateMarketQueryAccess("plus", { pokemonIds: ["149"], mode: "all" }).allowed, false);
  assert.equal(evaluateMarketQueryAccess("premium", { pokemonIds: ["149"], mode: "all" }).allowed, true);
  assert.equal(evaluateMarketQueryAccess("plus", { setIds: ["sv8"], priceSegmentIds: ["premium"], mode: "all" }).allowed, false);
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
    assert.equal(access.canBuildCustomMarkets, hasIndexPlusAccess(plan));
    assert.equal(access.canBuildCompoundMarket, hasIndexPremiumAccess(plan));
  }
});

test("plan labels use the exact product language", () => {
  assert.equal(INDEX_PLAN_LABELS.plus, "Index Plus");
  assert.equal(INDEX_PLAN_LABELS.premium, "Index Premium");
});
