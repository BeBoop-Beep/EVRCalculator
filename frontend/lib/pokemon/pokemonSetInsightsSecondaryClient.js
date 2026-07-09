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

// Priority 4-5 slice of the Insights tab (charts/distributions, deep
// diagnostics) — see backend/db/services/pokemon_public_snapshot_service.py
// get_pokemon_set_insights_secondary_snapshot_payload for the field list.
export function normalizePokemonSetInsightsSecondaryPayload(payload) {
  const outcomeDistribution = toPlainObject(payload?.outcomeDistribution);

  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug ?? payload?.set?.canonicalKey),
    },
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

const insightsSecondaryInflight = new Map();

function joinInsightsSecondaryRequest(key, factory) {
  if (insightsSecondaryInflight.has(key)) {
    return insightsSecondaryInflight.get(key);
  }
  const request = factory().finally(() => {
    insightsSecondaryInflight.delete(key);
  });
  insightsSecondaryInflight.set(key, request);
  return request;
}

export async function getPokemonSetInsightsSecondary(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  return joinInsightsSecondaryRequest(`insights-secondary:${resolvedSetId}`, async () => {
    const response = await fetch(`/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/insights/secondary`, {
      method: "GET",
    });

    return normalizePokemonSetInsightsSecondaryPayload(
      await readJsonResponse(response, "Unable to load Pokemon set insights")
    );
  });
}
