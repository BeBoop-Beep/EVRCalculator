import { getCachedSetRipResource } from "./pokemonSetRipResourceClient.mjs";

export function getPokemonSetRipRankContext(setId, calculationRunId, options) {
  return getCachedSetRipResource("rank-context", setId, calculationRunId, options);
}

export function selectSetRipRankContext(payload, { setId, calculationRunId } = {}) {
  if (payload?.contractVersion !== "pokemon-set-rip-rank-context-v1") return null;
  if (String(payload?.setId || "") !== String(setId || "")) return null;
  const families = payload?.productFamilyRankings?.families;
  if (!families || typeof families !== "object" || Array.isArray(families)) return null;
  const rankingCalculationRunId = String(payload?.rankingCalculationRunId || "");
  if (!rankingCalculationRunId) return null;
  return {
    ...payload,
    freshness: rankingCalculationRunId === String(calculationRunId || "") ? "current" : "latest_published",
    productFamilyRankings: { families },
  };
}
