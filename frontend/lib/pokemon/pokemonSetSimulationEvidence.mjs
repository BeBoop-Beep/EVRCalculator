const array = (value) => Array.isArray(value) ? value : [];
const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};

export function normalizePokemonSetSimulationEvidence(payload) {
  return {
    contractVersion: String(payload?.contractVersion || ""),
    setId: String(payload?.setId || ""),
    calculationRunId: String(payload?.calculationRunId || ""),
    marketDate: payload?.marketDate || null,
    summary: object(payload?.summary),
    percentiles: array(payload?.percentiles),
    distributionBins: array(payload?.distributionBins),
    thresholdBins: array(payload?.thresholdBins),
    meta: object(payload?.meta),
  };
}

export function selectSameSetSimulationEvidence(payload, { setId, calculationRunId = null } = {}) {
  const normalized = normalizePokemonSetSimulationEvidence(payload);
  if (normalized.contractVersion !== "pokemon-set-simulation-evidence-v1") return null;
  if (!setId || normalized.setId !== String(setId)) return null;
  if (calculationRunId && normalized.calculationRunId !== String(calculationRunId)) return null;
  return normalized.distributionBins.length || normalized.thresholdBins.length ? normalized : null;
}

const targetTokens = (target) => [
  target?.target_id, target?.id, target?.canonical_key, target?.canonicalKey,
  target?.slug, target?.pokemon_api_set_id,
].filter(Boolean).map((value) => String(value).toLowerCase());

export function selectRequestedPokemonSetTarget(targets, requestedTargetId, fallback = null) {
  const requested = String(requestedTargetId || "").toLowerCase();
  if (!requested) return null;
  const match = (Array.isArray(targets) ? targets : []).find((target) => targetTokens(target).includes(requested));
  if (match) return match;
  return targetTokens(fallback).includes(requested) ? fallback : null;
}
