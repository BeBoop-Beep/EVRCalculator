const stableRoster = (rosterRef) =>
  rosterRef
    ? [
        rosterRef.kind,
        rosterRef.marketKey,
        rosterRef.generationId || rosterRef.revisionId,
      ].join(":")
    : "";

export function activityRosterRefForSeries(series) {
  if (!series || series.asset === "sealed" || series.asset === "graded")
    return null;
  if (series.queryFingerprint) {
    const revisionId =
      series.revisionId ||
      series.queryRevisionId ||
      series.publishedRevisionId ||
      series.rosterRef?.revisionId;
    return revisionId
      ? {
          kind: "QUERY_CACHE_PUBLISHED_REVISION",
          revisionId,
          marketKey: series.marketKey || series.key,
        }
      : null;
  }
  if (!series.generationId || !series.key) return null;
  return {
    kind: "SURFACE_V2_GENERATION",
    generationId: series.generationId,
    marketKey: series.key,
  };
}

export function eligibleActivityMarkets(series = []) {
  return series
    .flatMap((entry) => {
      const rosterRef = activityRosterRefForSeries(entry);
      return rosterRef
        ? [
            {
              focusKey: entry.key,
              marketKey: entry.marketKey || entry.key,
              rosterRef,
            },
          ]
        : [];
    })
    .sort((left, right) => left.focusKey.localeCompare(right.focusKey));
}

export function activityCapabilityBatchKey(markets, identityKey, plan) {
  if (!identityKey || !["plus", "premium"].includes(plan) || !markets.length)
    return null;
  return `${identityKey}|${plan}|${markets.map((entry) => `${entry.focusKey}|${entry.marketKey}|${stableRoster(entry.rosterRef)}`).join(";")}`;
}

export function normalizeCapabilityResponse(payload, requestedMarkets) {
  if (
    payload?.contractVersion !== "market_activity_v1.1" ||
    !payload.capabilities
  ) {
    throw new Error("Market Activity capability response contract mismatch.");
  }
  const requested = new Map(
    requestedMarkets.map((entry) => [entry.focusKey, entry]),
  );
  const capabilities = {};
  for (const [focusKey, capability] of Object.entries(payload.capabilities)) {
    const request = requested.get(focusKey);
    if (!request || capability?.marketKey !== request.marketKey) continue;
    capabilities[focusKey] = capability;
  }
  return capabilities;
}
