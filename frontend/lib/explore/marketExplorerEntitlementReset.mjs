export const EXPLORER_PLAN_LIMITS = Object.freeze({ basic: 1, plus: 3, premium: 10 });

/** Deterministic downgrade policy. Exact/query markets are always discarded by the caller. */
export function reconcilePreparedWorkspace({ plan, loadedKeys = [], legacyKeys = [] }) {
  const limit = EXPLORER_PLAN_LIMITS[plan] || 1;
  const uniqueLoaded = [...new Set(loadedKeys)].slice(0, limit);
  return {
    keepLoadedKeys: uniqueLoaded,
    fallbackLegacyKey: uniqueLoaded.length ? null : (legacyKeys[0] || "raw"),
    limit,
  };
}
