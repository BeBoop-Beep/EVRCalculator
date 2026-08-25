export function normaliseRipStatisticsPayload(payload) {
  const sourceMeta = payload?.meta && typeof payload.meta === "object"
    ? payload.meta
    : { warnings: [], timings: {}, sources: {} };
  const snapshotFallback = Boolean(sourceMeta?.snapshot?.isStaleFallback);
  return {
    targets: Array.isArray(payload?.targets) ? payload.targets : [],
    default_target: payload?.default_target || null,
    productFamilyRankings: payload?.productFamilyRankings || null,
    overallProductRankings: payload?.overallProductRankings || null,
    meta: {
      ...sourceMeta,
      stale: Boolean(sourceMeta.stale || snapshotFallback),
      fallback: Boolean(sourceMeta.fallback || snapshotFallback),
    },
  };
}
