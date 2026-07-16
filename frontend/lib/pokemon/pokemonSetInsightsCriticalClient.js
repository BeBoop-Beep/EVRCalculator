function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function toPlainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
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

// Priority 1-3 slice of the Insights tab (RIP Score hero, pillar cards,
// recommendation copy) — see backend/db/services/pokemon_public_snapshot_service.py
// get_pokemon_set_insights_critical_snapshot_payload for the field list.
export function normalizePokemonSetInsightsCriticalPayload(payload) {
  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug ?? payload?.set?.canonicalKey),
    },
    summary: toPlainObject(payload?.summary),
    recommendation: toPlainObject(payload?.recommendation),
    // Legacy hero block (relative/min-max). Deprecated: new UI reads `rip`.
    ripScore: toPlainObject(payload?.ripScore),
    // The canonical public contract. Pass-through only: scores, ranks, tiers,
    // weights and cohort sizes are backend-computed; the frontend never
    // derives them (see backend explore_rip_statistics_service).
    rip: toPlainObject(payload?.rip),
    ripCore: toPlainObject(payload?.ripCore),
    openingExperience: toPlainObject(payload?.openingExperience),
    publicAnalyticsCohort: toPlainObject(payload?.publicAnalyticsCohort),
    publicAnalyticsStatus: toOptionalString(payload?.publicAnalyticsStatus),
    interpretation: toPlainObject(payload?.interpretation),
    meta: payload?.meta || { warnings: [] },
  };
}

// Joins concurrent identical calls onto one in-flight promise — same pattern
// as pokemonSetInsightsClient.js's joinInsightsRequest, needed because React
// 18 StrictMode double-invokes effects in development and this fetch effect
// has no AbortController.
const insightsCriticalInflight = new Map();

function joinInsightsCriticalRequest(key, factory) {
  if (insightsCriticalInflight.has(key)) {
    return insightsCriticalInflight.get(key);
  }
  const request = factory().finally(() => {
    insightsCriticalInflight.delete(key);
  });
  insightsCriticalInflight.set(key, request);
  return request;
}

export async function getPokemonSetInsightsCritical(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  return joinInsightsCriticalRequest(`insights-critical:${resolvedSetId}`, async () => {
    const response = await fetch(`/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/insights/critical`, {
      method: "GET",
    });

    return normalizePokemonSetInsightsCriticalPayload(
      await readJsonResponse(response, "Unable to load Pokemon set insights")
    );
  });
}
