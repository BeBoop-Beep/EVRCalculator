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

export async function getPokemonSetInsights(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const response = await fetch(`/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/insights`, {
    method: "GET",
  });

  return normalizePokemonSetInsightsPayload(
    await readJsonResponse(response, "Unable to load Pokemon set insights")
  );
}
