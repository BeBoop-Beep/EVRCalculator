export function normaliseRipStatisticsTarget(target) {
  if (!target || typeof target !== "object" || Array.isArray(target)) {
    return target;
  }

  const era = target.era;
  if (!era || typeof era !== "object" || Array.isArray(era)) {
    return target;
  }

  return {
    ...target,
    era: era.name ?? target.era_name ?? target.eraName ?? null,
    era_id: target.era_id ?? target.eraId ?? era.id ?? null,
  };
}

export function normaliseRipStatisticsPayload(payload) {
  const sourceMeta = payload?.meta && typeof payload.meta === "object"
    ? payload.meta
    : { warnings: [], timings: {}, sources: {} };
  const snapshotFallback = Boolean(sourceMeta?.snapshot?.isStaleFallback);
  return {
    targets: Array.isArray(payload?.targets)
      ? payload.targets.map(normaliseRipStatisticsTarget)
      : [],
    default_target: normaliseRipStatisticsTarget(payload?.default_target || null),
    productFamilyRankings: payload?.productFamilyRankings || null,
    meta: {
      ...sourceMeta,
      stale: Boolean(sourceMeta.stale || snapshotFallback),
      fallback: Boolean(sourceMeta.fallback || snapshotFallback),
    },
  };
}
