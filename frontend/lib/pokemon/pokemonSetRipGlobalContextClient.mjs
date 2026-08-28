import { getCachedSetRipResource } from "./pokemonSetRipResourceClient.mjs";

export function getPokemonSetRipGlobalContext(setId, { expectedCalculationRunId, force = false } = {}) {
  return getCachedSetRipResource("global-context", setId, expectedCalculationRunId, { force });
}

export function selectCompatibleSetRipGlobalContext(payload, expectedCalculationRunId) {
  if (!payload || payload.compatible !== true || payload.status !== "ready") return null;
  if (expectedCalculationRunId && String(payload.expectedCalculationRunId || "") !== String(expectedCalculationRunId)) return null;
  return payload;
}
