function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function toPlainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
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
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug ?? payload?.set?.canonicalKey),
    },
    summary: toPlainObject(payload?.summary),
    recommendation: toPlainObject(payload?.recommendation),
    ripScore: toPlainObject(payload?.ripScore),
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
    desirabilityValidation: toPlainObject(payload?.desirabilityValidation),
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
