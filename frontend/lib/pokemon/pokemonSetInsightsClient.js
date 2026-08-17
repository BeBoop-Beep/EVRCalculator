function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function toPlainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function toNullablePlainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}

async function readJsonResponse(response, fallbackMessage) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message = payload?.message || payload?.error || fallbackMessage;
    const requestError = new Error(message);
    requestError.status = response.status;
    requestError.code = payload?.code;
    throw requestError;
  }

  return payload;
}

export function normalizePokemonSetInsightsPayload(payload) {
  const outcomeDistribution = toPlainObject(payload?.outcomeDistribution);

  return {
    ripDecision: toNullablePlainObject(payload?.ripDecision),
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug ?? payload?.set?.canonicalKey),
    },
    summary: toPlainObject(payload?.summary),
    recommendation: toPlainObject(payload?.recommendation),
    // Legacy hero block (relative/min-max). Deprecated: new UI reads `rip`.
    ripScore: toPlainObject(payload?.ripScore),
    // Canonical public contract (pass-through; backend-computed).
    rip: toPlainObject(payload?.rip),
    ripCore: toPlainObject(payload?.ripCore),
    // Canonical after the V3 cutover; `rip`/`ripCore` above are the legacy
    // V2/v4 objects. Pass-through only, backend-computed.
    financialRipV3: toPlainObject(payload?.financialRipV3),
    overallRipV5: toPlainObject(payload?.overallRipV5),
    publicRipContractV5: toPlainObject(payload?.publicRipContractV5),
    // Superseded 80/20 blend over Collector Appeal V2. Transport-only: kept for
    // audit/comparison consumers, never read by a current public surface.
    overallRipV6: toPlainObject(payload?.overallRipV6),
    publicRipContractV6: toPlainObject(payload?.publicRipContractV6),
    // CANONICAL: Overall RIP V7 and the v7 public contract (Overall + Financial
    // RIP V3 + Collector Appeal V3). Pass-through only, backend-computed.
    overallRipV8: toPlainObject(payload?.overallRipV8),
    publicRipContractV8: toPlainObject(payload?.publicRipContractV8),
    overallRipV9: toPlainObject(payload?.overallRipV9),
    publicRipContractV9: toPlainObject(payload?.publicRipContractV9),
    openingExperience: toPlainObject(payload?.openingExperience),
    publicAnalyticsCohort: toPlainObject(payload?.publicAnalyticsCohort),
    publicAnalyticsStatus: toOptionalString(payload?.publicAnalyticsStatus),
    interpretation: toPlainObject(payload?.interpretation),
    ripStatistics: toPlainObject(payload?.ripStatistics),
    outcomeDistribution: {
      percentiles: toArray(outcomeDistribution.percentiles),
      distributionBins: toArray(outcomeDistribution.distributionBins),
      thresholdBins: toArray(outcomeDistribution.thresholdBins),
    },
    simulationDrivers: toArray(payload?.simulationDrivers),
    rarityContribution: toArray(payload?.rarityContribution),
    historyTrend: toArray(payload?.historyTrend),
    desirability: toPlainObject(payload?.desirability),
    // desirabilityValidation is retired: the backend no longer serves it and
    // the Desirability Evidence section it fed was replaced by Opening
    // Experience.
    meta: payload?.meta || { warnings: [] },
  };
}

// Joins concurrent identical getPokemonSetInsights calls onto one in-flight
// promise (same pattern as pokemonSetMarketClient.js's joinSlimModuleRequest)
// — React 18 StrictMode double-invokes effects in development, and the
// Insights fetch effect has no AbortController, only a local isCancelled
// flag that ignores the second result. Both requests still hit the network
// without this.
const insightsInflight = new Map();

function joinInsightsRequest(key, factory) {
  if (insightsInflight.has(key)) {
    return insightsInflight.get(key);
  }
  const request = factory().finally(() => {
    insightsInflight.delete(key);
  });
  insightsInflight.set(key, request);
  return request;
}

export async function getPokemonSetInsights(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  return joinInsightsRequest(`insights:${resolvedSetId}`, async () => {
    const response = await fetch(`/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/insights`, {
      method: "GET",
    });

    return normalizePokemonSetInsightsPayload(
      await readJsonResponse(response, "Unable to load Pokemon set insights")
    );
  });
}
