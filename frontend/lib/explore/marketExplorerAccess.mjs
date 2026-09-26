// ---------------------------------------------------------------------------
// Market Explorer -- the ONE application access authority for workspace limits
// and analytical focus-tool entitlement.
//
// Plan resolution stays in lib/access/indexPlanAccess.mjs (the shared frontend
// hierarchy). This module only maps a resolved plan to Explorer-specific
// commercial limits and capabilities, so no component compares plan strings or
// carries a magic number. The server mirror of the limit is
// MARKET_EXPLORER_ACTIVE_MARKET_LIMIT in backend/domain/access/index_plan_access.py
// (enforced on prepared-comparison for marketKeys U contextMarketKeys).
//
// COUNTING RULES (see countActiveMarkets):
//   - every ACTIVE market counts, prepared or query-built;
//   - HIDDEN active markets DO count (hidden is not removed);
//   - FOCUS never counts (it is presentation, not a market);
//   - a still-loading request counts once so double-clicks cannot overshoot.
// ---------------------------------------------------------------------------
import {
  FEATURE_MARKET_EXPLORER_DEMAND_PRESSURE,
  FEATURE_MARKET_EXPLORER_FAIR_VALUE,
  hasIndexFeatureAccess,
  hasIndexPlusAccess,
  hasIndexPremiumAccess,
  normalizeIndexPlan,
} from "../access/indexPlanAccess.mjs";

export const MARKET_EXPLORER_PLAN_TIER = Object.freeze({ basic: "basic", plus: "plus", premium: "premium" });

/** Simultaneous ACTIVE markets per plan. The single frontend definition. */
export const MARKET_EXPLORER_ACTIVE_MARKET_LIMIT = Object.freeze({
  [MARKET_EXPLORER_PLAN_TIER.basic]: 1,
  [MARKET_EXPLORER_PLAN_TIER.plus]: 3,
  [MARKET_EXPLORER_PLAN_TIER.premium]: 10,
});

export function marketExplorerTier(plan) {
  return normalizeIndexPlan(plan) || MARKET_EXPLORER_PLAN_TIER.basic;
}

export function activeMarketLimitFor(plan) {
  return MARKET_EXPLORER_ACTIVE_MARKET_LIMIT[marketExplorerTier(plan)];
}

/**
 * Count of markets that occupy a slot: every active series (hidden included) plus
 * loading prepared requests that are not yet in the active set.
 */
export function countActiveMarkets({ activeKeys = [], pendingKeys = [] } = {}) {
  return new Set([...(activeKeys || []), ...(pendingKeys || [])]).size;
}

export const ACTIVE_MARKET_LIMIT_COPY = Object.freeze({
  basic: "Basic includes one active market. Index+ supports up to 3 active comparison markets.",
  plus: "Index+ supports up to 3 active comparison markets.",
  premium: "Premium supports up to 10 active comparison markets.",
});

/**
 * Decide whether one more market may join the workspace.
 * Never removes or replaces anything: a full workspace returns allowed:false and the
 * caller shows `message` (and `upgrade` when a higher plan raises the cap).
 */
export function evaluateActiveMarketAdd(plan, activeCount) {
  const tier = marketExplorerTier(plan);
  const limit = MARKET_EXPLORER_ACTIVE_MARKET_LIMIT[tier];
  if (activeCount < limit) return { allowed: true, tier, limit, message: null, upgrade: false };
  return {
    allowed: false, tier, limit,
    message: ACTIVE_MARKET_LIMIT_COPY[tier],
    // Premium is the top tier: there is nothing to upgrade to.
    upgrade: tier !== MARKET_EXPLORER_PLAN_TIER.premium,
  };
}

// --- Analytical focus tools --------------------------------------------------
export const FOCUS_TOOL_STATE = Object.freeze({ locked: "locked", unavailable: "unavailable", available: "available" });

export const DEMAND_PRESSURE_UNAVAILABLE_COPY = "Demand Pressure data is not available for this market yet.";
export const FAIR_VALUE_UNAVAILABLE_COPY = "inDex Fair Value is not available for this market yet.";

/**
 * Backend capability shape (DEFAULT: nothing available). A future endpoint publishes
 *   { demandPressure: { [marketKey]: { available: true, ... } },
 *     fairValue:      { [marketKey]: { available: true, series: [...] } } }
 * Absent or non-explicit => UNAVAILABLE. Nothing is ever synthesised client-side.
 */
export const NO_BACKEND_CAPABILITIES = Object.freeze({ demandPressure: Object.freeze({}), fairValue: Object.freeze({}) });

const explicitlyAvailable = (map, key) => Boolean(map && key && map[key] && map[key].available === true);

export function resolveFocusToolStates(plan, marketKey, backendCapabilities = NO_BACKEND_CAPABILITIES) {
  const demandEntitled = hasIndexFeatureAccess(plan, FEATURE_MARKET_EXPLORER_DEMAND_PRESSURE);
  const fairEntitled = hasIndexFeatureAccess(plan, FEATURE_MARKET_EXPLORER_FAIR_VALUE);
  const caps = backendCapabilities || NO_BACKEND_CAPABILITIES;
  return {
    demandPressure: {
      state: !demandEntitled ? FOCUS_TOOL_STATE.locked
        : explicitlyAvailable(caps.demandPressure, marketKey) ? FOCUS_TOOL_STATE.available : FOCUS_TOOL_STATE.unavailable,
      requiredPlan: "plus",
      reason: !demandEntitled ? "Demand Pressure requires Index+." : explicitlyAvailable(caps.demandPressure, marketKey) ? null : DEMAND_PRESSURE_UNAVAILABLE_COPY,
    },
    fairValue: {
      state: !fairEntitled ? FOCUS_TOOL_STATE.locked
        : explicitlyAvailable(caps.fairValue, marketKey) ? FOCUS_TOOL_STATE.available : FOCUS_TOOL_STATE.unavailable,
      requiredPlan: "premium",
      reason: !fairEntitled ? "inDex Fair Value is a Premium feature." : explicitlyAvailable(caps.fairValue, marketKey) ? null : FAIR_VALUE_UNAVAILABLE_COPY,
    },
  };
}

/** Whole-plan capability map (entitlement only; availability is per focused market). */
export function resolveMarketExplorerCapabilities(plan) {
  return {
    tier: marketExplorerTier(plan),
    activeMarketLimit: activeMarketLimitFor(plan),
    canUseDemandPressure: hasIndexPlusAccess(plan),
    canUseFairValue: hasIndexPremiumAccess(plan),
  };
}
