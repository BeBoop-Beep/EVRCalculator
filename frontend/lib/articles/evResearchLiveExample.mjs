import { selectEvRepresentativenessPublicV1 } from "../../components/explore/evRepresentativenessSelector.mjs";
import { selectOpeningOutcomeProfileV1 } from "../../components/explore/openingOutcomeProfileSelector.mjs";
import { normalizePokemonSetSimulationEvidence } from "../pokemon/pokemonSetSimulationEvidence.mjs";

export function selectPrismaticResearchLiveExample(target, simulationEvidence) {
  if (!target || String(target.name || "").trim().toLowerCase() !== "prismatic evolutions") return null;
  const calculationRunId = String(target.calculation_run_id ?? target.calculationRunId ?? "");
  if (!calculationRunId) return null;
  const evidence = normalizePokemonSetSimulationEvidence(simulationEvidence);
  if (evidence.contractVersion !== "pokemon-set-simulation-evidence-v1" || evidence.calculationRunId !== calculationRunId) return null;
  if (!evidence.distributionBins.length && !evidence.thresholdBins.length) return null;
  const openingOutcomeProfile = selectOpeningOutcomeProfileV1(target.openingOutcomeProfile, calculationRunId);
  const evRepresentativeness = selectEvRepresentativenessPublicV1(target.evRepresentativeness, calculationRunId);
  if (!openingOutcomeProfile || !evRepresentativeness) return null;
  return {
    calculationRunId,
    setName: "Prismatic Evolutions",
    summary: evidence.summary,
    percentiles: evidence.percentiles,
    distribution: { bins: evidence.distributionBins, thresholdBins: evidence.thresholdBins, markers: evidence.summary?.markers },
    simulationCount: evidence.summary?.simulationCount ?? evidence.summary?.simulation_count ?? 1000000,
    openingOutcomeProfile: target.openingOutcomeProfile,
    evRepresentativeness: target.evRepresentativeness,
  };
}
