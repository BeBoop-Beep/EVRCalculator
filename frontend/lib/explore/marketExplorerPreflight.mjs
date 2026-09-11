export const PREFLIGHT_STATE = Object.freeze({
  idle: "idle", checking: "checking", ready: "ready", empty: "empty",
  noHistory: "no_history", unavailable: "unavailable", rateLimited: "rate_limited", failed: "failed",
});

export function preflightRequestSpec(spec) {
  if (!spec || spec.asset !== "cards" || spec.membershipMode === "explicit") return null;
  return {
    eraIds: spec.eraIds || [], setIds: spec.setIds || [], segmentIds: spec.segmentIds || [],
    pokemonIds: spec.pokemonIds || [], priceSegmentIds: spec.priceSegmentIds || [],
    releaseAgeCohortIds: spec.releaseAgeCohortIds || [],
  };
}

export function resolvePreflightState(payload, httpStatus = 200) {
  const code = payload?.queryOutcome || payload?.code;
  if (httpStatus === 429 || code === "QUERY_RATE_LIMITED") return PREFLIGHT_STATE.rateLimited;
  if (code === "QUERY_EMPTY_NOW" || payload?.readiness === "PREFLIGHT_EMPTY") return PREFLIGHT_STATE.empty;
  if (code === "QUERY_NO_HISTORY" || ["PREFLIGHT_CURRENT_ONLY", "PREFLIGHT_DISCONNECTED_HISTORY"].includes(payload?.readiness)) return PREFLIGHT_STATE.noHistory;
  if (code === "QUERY_UNAVAILABLE" || ["PREFLIGHT_PROJECTION_LAGGING", "PREFLIGHT_HISTORY_UNAVAILABLE", "PREFLIGHT_NO_APPROVED_DATE", "PREFLIGHT_UNKNOWN"].includes(payload?.readiness)) return PREFLIGHT_STATE.unavailable;
  if (httpStatus >= 400) return PREFLIGHT_STATE.failed;
  return payload?.readiness === "PREFLIGHT_READY" ? PREFLIGHT_STATE.ready : PREFLIGHT_STATE.unavailable;
}

export function preflightMessage(state, payload = {}, retryAfter = null) {
  if (state === PREFLIGHT_STATE.checking) return "Checking matching cards…";
  if (state === PREFLIGHT_STATE.ready) return `~${payload.matchingConstituentCount ?? 0} matching cards across ${payload.matchingSetCount ?? 0} sets.`;
  if (state === PREFLIGHT_STATE.empty) return "No cards currently match these filters.";
  if (state === PREFLIGHT_STATE.noHistory) return "Matching cards do not yet have enough connected market history.";
  if (state === PREFLIGHT_STATE.rateLimited) return `Matching-card check is rate limited.${retryAfter ? ` Try again in ${retryAfter} seconds.` : ""}`;
  if (state === PREFLIGHT_STATE.unavailable) return "Matching-card availability is temporarily unavailable. This is not a zero-match result.";
  if (state === PREFLIGHT_STATE.failed) return "Unable to check matching cards right now.";
  return "";
}

export function buildErrorMessage(error) {
  const retry = error?.retryAfter ? ` Try again in ${error.retryAfter} seconds.` : "";
  return ({
    QUERY_EMPTY_NOW: "No cards currently match these filters.",
    QUERY_NO_HISTORY: "Matching cards do not yet have enough connected market history.",
    QUERY_BUILDING: `This market is being built.${retry}`,
    QUERY_CACHE_REFRESHING: `This market is refreshing.${retry}`,
    QUERY_RATE_LIMITED: `Market builds are temporarily rate limited.${retry}`,
    QUERY_INVALID: "This market definition is not valid.",
    QUERY_UNAVAILABLE: "This market is temporarily unavailable.",
    QUERY_FAILED: "Unable to build this market right now.",
  })[error?.code] || error?.message || "Unable to build this market right now.";
}
