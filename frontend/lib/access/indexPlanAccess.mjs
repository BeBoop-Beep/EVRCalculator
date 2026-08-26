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
  return {
    accessMode: indexPlan || "basic",
    isAuthenticated: Boolean(user),
    indexPlan,
    // Plus AND Premium — Premium inherits the whole prepared layer.
    canUsePreparedMarketIntelligence: hasIndexPlusAccess(indexPlan),
    // Premium only. Browsing Era & Sets is a Plus capability; turning a scope
    // into a real custom market is not.
    canBuildCustomMarkets: hasIndexPremiumAccess(indexPlan),
  };
}

export function resolveRankingsPlanAccess(user) {
  const indexPlan = normalizeIndexPlan(user?.index_plan);
  return {
    canViewRankingsIntelligence: hasIndexPlusAccess(indexPlan),
    accessMode: indexPlan || "basic",
  };
}
