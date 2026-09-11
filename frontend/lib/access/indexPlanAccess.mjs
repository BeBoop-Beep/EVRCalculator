// ---------------------------------------------------------------------------
// Index plan hierarchy — the ONE frontend entitlement authority.
//
// Basic -> Index Plus -> Index Premium. Premium satisfies every Plus check.
//
// AUTHENTICATION IS NOT ENTITLEMENT. Being signed in identifies a user; it
// grants nothing. An authenticated account with no paid plan has exactly the
// FEATURE access an anonymous visitor has. The two states are still kept apart
// wherever they are user-visible, because their upgrade paths differ (an
// anonymous visitor needs an account first), but no feature check may treat
// "signed in" as "entitled".
//
// The server half is `backend/domain/access/index_plan_access.py` and is an
// exact mirror. Neither side may invent its own reading of the same plans, and
// no surface may define a parallel notion of paid access — a second
// interpretation is how a paid feature quietly becomes free on one page.
// ---------------------------------------------------------------------------

export const INDEX_PLAN_PLUS = "plus";
export const INDEX_PLAN_PREMIUM = "premium";

export function normalizeIndexPlan(plan) {
  if (typeof plan !== "string") return null;
  const normalized = plan.trim().toLowerCase();
  return normalized === INDEX_PLAN_PLUS || normalized === INDEX_PLAN_PREMIUM
    ? normalized
    : null;
}

export function hasIndexPlusAccess(plan) {
  const normalized = normalizeIndexPlan(plan);
  return normalized === INDEX_PLAN_PLUS || normalized === INDEX_PLAN_PREMIUM;
}

export function hasIndexPremiumAccess(plan) {
  return normalizeIndexPlan(plan) === INDEX_PLAN_PREMIUM;
}

/**
 * Feature identity for Build a Market.
 *
 * Named for the CAPABILITY, not the plan. Commercial packaging is not final,
 * so the tier a feature maps to must be changeable in ONE place; hardcoding a
 * plan name at every call site is what makes repackaging a rewrite.
 */
export const FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS = "market_explorer_custom_markets";
export const FEATURE_MARKET_EXPLORER_SINGLE_AXIS = "market_explorer_single_axis";
export const FEATURE_MARKET_EXPLORER_COMPOUND = "market_explorer_compound";
export const FEATURE_MARKET_EXPLORER_CUSTOM_RANKED = "market_explorer_custom_ranked";
export const FEATURE_MARKET_EXPLORER_POKEMON = "market_explorer_pokemon";
export const FEATURE_MARKET_EXPLORER_EXPLICIT_INSTRUMENTS = "market_explorer_explicit_instruments";
export const FEATURE_MARKET_EXPLORER_PREPARED_COMPARE = "market_explorer_prepared_compare";
export const FEATURE_MARKET_EXPLORER_ANALYTICAL_SCREENS = "market_explorer_analytical_screens";
export const FEATURE_MARKET_EXPLORER_ADVANCED_RANKING = "market_explorer_advanced_ranking";
export const FEATURE_CARD_CHASE_EFFICIENCY = "card_chase_efficiency";
export const FEATURE_PRODUCT_RIP = "product_rip";
export const FEATURE_DETAILED_OPENING_ECONOMICS = "detailed_opening_economics";
export const FEATURE_SET_PACK_ECONOMICS = "set_pack_economics";
export const FEATURE_ERA_PACK_ECONOMICS = "era_pack_economics";
export const FEATURE_MARKET_BREADTH = "market_breadth";
export const FEATURE_CARD_PULL_ODDS = "card_pull_odds";
export const FEATURE_ACQUISITION_MILESTONES = "acquisition_milestones";
export const FEATURE_PREPARED_MARKET_INTELLIGENCE = "prepared_market_intelligence";
export const FEATURE_CHASE_OPENING_ROUTE = "chase_opening_route";
export const FEATURE_CHASE_VS_BUY = "chase_vs_buy";
export const FEATURE_CHASE_RANKINGS = "chase_rankings";
// Product Chase Intelligence (Chase Access at Budget, O_budget) - a DISTINCT
// Premium construct from Card Chase Efficiency/Opening Route/vs Buy/Rankings
// above. "Which sealed product gives the most reach into a set's important
// value at my budget?", not "what's the best way to pursue this card?".
export const FEATURE_PRODUCT_CHASE_INTELLIGENCE = "product_chase_intelligence";

export const PLUS_FEATURES = Object.freeze(new Set([
  FEATURE_PRODUCT_RIP, FEATURE_DETAILED_OPENING_ECONOMICS,
  FEATURE_SET_PACK_ECONOMICS, FEATURE_ERA_PACK_ECONOMICS,
  FEATURE_MARKET_BREADTH, FEATURE_CARD_PULL_ODDS,
  FEATURE_ACQUISITION_MILESTONES, FEATURE_PREPARED_MARKET_INTELLIGENCE,
  FEATURE_MARKET_EXPLORER_PREPARED_COMPARE,
  FEATURE_MARKET_EXPLORER_ANALYTICAL_SCREENS,
  FEATURE_MARKET_EXPLORER_ADVANCED_RANKING,
]));
export const PREMIUM_FEATURES = Object.freeze(new Set([
  FEATURE_CARD_CHASE_EFFICIENCY, FEATURE_CHASE_OPENING_ROUTE,
  FEATURE_CHASE_VS_BUY, FEATURE_CHASE_RANKINGS,
  FEATURE_MARKET_EXPLORER_COMPOUND, FEATURE_MARKET_EXPLORER_CUSTOM_RANKED,
  FEATURE_MARKET_EXPLORER_POKEMON, FEATURE_MARKET_EXPLORER_EXPLICIT_INSTRUMENTS,
  FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS, FEATURE_MARKET_EXPLORER_SINGLE_AXIS,
  FEATURE_PRODUCT_CHASE_INTELLIGENCE,
]));

export function hasIndexFeatureAccess(plan, feature) {
  if (PREMIUM_FEATURES.has(feature)) return hasIndexPremiumAccess(plan);
  if (PLUS_FEATURES.has(feature)) return hasIndexPlusAccess(plan);
  return false;
}

export function activeMarketFilterAxes(spec) {
  const axes = [];
  if (spec?.eraIds?.length || spec?.setIds?.length) axes.push("scope");
  if (spec?.segmentIds?.length) axes.push("segment");
  if (spec?.pokemonIds?.length) axes.push("pokemon");
  if (spec?.priceSegmentIds?.length) axes.push("priceSegment");
  if (spec?.releaseAgeCohortIds?.length) axes.push("releaseAge");
  return axes;
}

export function evaluateMarketQueryAccess(plan, spec) {
  const activeFilterAxes = activeMarketFilterAxes(spec);
  const ranked = spec?.mode === "chase";
  const pokemon = Boolean(spec?.pokemonIds?.length);
  const explicit = spec?.membershipMode === "explicit";
  // Every arbitrary Builder execution is creation, and creation is Premium.
  // Prepared-market browsing/comparison is evaluated by the Explorer
  // capability layer below and never reaches this query gate.
  const requiredPlan = INDEX_PLAN_PREMIUM;
  const capability = explicit
    ? FEATURE_MARKET_EXPLORER_EXPLICIT_INSTRUMENTS
    : pokemon
    ? FEATURE_MARKET_EXPLORER_POKEMON
    : ranked
      ? FEATURE_MARKET_EXPLORER_CUSTOM_RANKED
    : activeFilterAxes.length > 1
      ? FEATURE_MARKET_EXPLORER_COMPOUND
      : FEATURE_MARKET_EXPLORER_SINGLE_AXIS;
  const allowed = hasIndexPremiumAccess(plan);
  return { allowed, requiredPlan, capability, activeFilterAxes };
}

/** Plan display names. The product language, in one place. */
export const INDEX_PLAN_LABELS = Object.freeze({
  [INDEX_PLAN_PLUS]: "Index Plus",
  [INDEX_PLAN_PREMIUM]: "Index Premium",
});

/**
 * The Market Explorer access ladder for one user.
 *
 * THREE LEVELS, NOT TWO:
 *   basic   — Asset Market only (Raw, Sealed; Graded is unavailable to all).
 *   plus    — the prepared research layers: rarities, sealed families,
 *             Era & Sets browsing, benchmarks, prepared constituents.
 *   premium — everything above PLUS the custom-market builder.
 *
 * `accessMode` is "basic" for an anonymous visitor AND for an authenticated
 * account with no paid plan, because their FEATURE access is identical.
 * `isAuthenticated` is reported separately so the UI can offer the right next
 * step — sign in, or upgrade — without either being mistaken for entitlement.
 */
export function resolveMarketExplorerPlanAccess(user) {
  const indexPlan = normalizeIndexPlan(user?.index_plan);
  const canComparePreparedMarkets = hasIndexPlusAccess(indexPlan);
  const canBuildCustomMarkets = hasIndexPremiumAccess(indexPlan);
  return {
    accessMode: indexPlan || "basic",
    isAuthenticated: Boolean(user),
    indexPlan,
    // Plus AND Premium — Premium inherits the whole prepared layer.
    canBrowsePreparedMarkets: true,
    canComparePreparedMarkets,
    canUseAnalyticalScreens: canComparePreparedMarkets,
    canUseAdvancedMarketRanking: canComparePreparedMarkets,
    canUsePreparedMarketIntelligence: canComparePreparedMarkets,
    // Premium only. Browsing Era & Sets is a Plus capability; turning a scope
    // into a real custom market is not.
    canBuildCustomMarkets,
    canBuildSingleAxisMarket: canBuildCustomMarkets,
    canBuildCompoundMarket: hasIndexPremiumAccess(indexPlan),
    canUseCustomRankedComposition: hasIndexPremiumAccess(indexPlan),
  };
}

export function resolveRankingsPlanAccess(user) {
  const indexPlan = normalizeIndexPlan(user?.index_plan);
  return {
    canViewRankingsIntelligence: hasIndexPlusAccess(indexPlan),
    canViewCardChaseEfficiency: hasIndexFeatureAccess(indexPlan, FEATURE_CARD_CHASE_EFFICIENCY),
    accessMode: indexPlan || "basic",
  };
}
