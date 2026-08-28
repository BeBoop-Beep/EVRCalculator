import { getCachedSetRipResource } from "./pokemonSetRipResourceClient.mjs";

const array = (value) => Array.isArray(value) ? value : [];
const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};

export function selectSameRunRipSimulation(payload, { setId, calculationRunId } = {}) {
  if (payload?.contractVersion !== "pokemon-set-rip-simulation-evidence-v1") return null;
  if (String(payload?.setId || "") !== String(setId || "")) return null;
  if (String(payload?.calculationRunId || "") !== String(calculationRunId || "")) return null;
  const openingOutcomeProfile = object(payload.openingOutcomeProfile);
  if (Object.keys(openingOutcomeProfile).length && String(openingOutcomeProfile.calculationRunId || "") !== String(calculationRunId || "")) return null;
  const evRepresentativeness = object(payload.evRepresentativeness);
  if (Object.keys(evRepresentativeness).length && String(evRepresentativeness.calculationRunId || "") !== String(calculationRunId || "")) return null;
  return { ...payload, summary: object(payload.summary), percentiles: array(payload.percentiles), distributionBins: array(payload.distributionBins), thresholdBins: array(payload.thresholdBins), openingOutcomeProfile: Object.keys(openingOutcomeProfile).length ? openingOutcomeProfile : null, evRepresentativeness: Object.keys(evRepresentativeness).length ? evRepresentativeness : null };
}

export function selectSameRunRipAdvanced(payload, { setId, calculationRunId, bootstrapCanonical } = {}) {
  if (payload?.contractVersion !== "pokemon-set-rip-advanced-v1") return null;
  if (String(payload?.setId || "") !== String(setId || "")) return null;
  if (String(payload?.calculationRunId || "") !== String(calculationRunId || "")) return null;
  const advanced = { ...payload, financialRip: object(payload.financialRip), collectorAppeal: object(payload.collectorAppeal), rarityContribution: array(payload.rarityContribution) };
  const headlineFinancial = bootstrapCanonical?.publicRipContractV10?.financialRip || {};
  const headlineCollector = bootstrapCanonical?.publicRipContractV10?.collectorAppeal || {};
  for (const [published, detail] of [[headlineFinancial, advanced.financialRip], [headlineCollector, advanced.collectorAppeal]]) {
    for (const key of ["leaderNormalizedScore", "relativeScore", "rank", "tier", "cohortSize", "rankedSetCount"]) {
      if (published[key] != null && detail[key] != null && published[key] !== detail[key]) return null;
    }
  }
  return advanced;
}

export function getPokemonSetRipSimulationEvidence(setId, calculationRunId, options) {
  return getCachedSetRipResource("simulation-evidence", setId, calculationRunId, options);
}

export function getPokemonSetRipAdvanced(setId, calculationRunId, options) {
  return getCachedSetRipResource("advanced", setId, calculationRunId, options);
}
