import assert from "node:assert/strict";
import test from "node:test";
import { selectPrismaticResearchLiveExample } from "./evResearchLiveExample.mjs";
import { buildRipDistributionMarkers } from "../../components/explore/ripDistributionMarkers.mjs";

const buckets = [
  ["under_25", 0, .25, .4], ["recover_25_50", .25, .5, .3], ["recover_50_75", .5, .75, .1], ["recover_75_100", .75, 1, .05],
  ["recover_100_150", 1, 1.5, .05], ["recover_150_200", 1.5, 2, .04], ["recover_200_500", 2, 5, .04], ["recover_500_plus", 5, null, .02],
].map(([key, floorRatio, ceilingRatio, probability]) => ({ key, label: key, floorRatio, ceilingRatio, probability, occurrenceCount: probability * 1000000, interpretation: key }));
const target = { name: "Prismatic Evolutions", target_id: "set-a", calculation_run_id: "run-A",
  openingOutcomeProfile: { contractVersion: "opening_outcome_profile_v1", researchMethodVersion: "opening_outcome_profile_research_v1", calculationRunId: "run-A", buckets, cumulativeProbabilities: [] },
  evRepresentativeness: { contractVersion: "ev_representativeness_public_v1", methodVersion: "ev_representativeness_v1", calculationRunId: "run-A", typicalCapture: .2, top1OutcomeEvShare: .6, realizationByPackCount: [] },
};
const evidence = { contractVersion: "pokemon-set-simulation-evidence-v1", setId: "set-a", calculationRunId: "run-A", distributionBins: [{ min: 0, max: 1, count: 1 }], thresholdBins: [], percentiles: [{ percentile: 5, value: .5 }, { percentile: 50, value: 2 }, { percentile: 95, value: 20 }, { percentile: 99, value: 60 }], summary: { meanValue: 8, packCost: 5, p95ValueToCostRatio: 4, p99ValueToCostRatio: 12 } };

test("assembles a live model only when all three contracts share run identity", () => {
  const result = selectPrismaticResearchLiveExample(target, evidence);
  assert.equal(result.calculationRunId, "run-A");
  assert.equal(result.distribution.bins.length, 1);
  assert.deepEqual(result.distribution.markers, buildRipDistributionMarkers({ summary: evidence.summary, percentiles: evidence.percentiles }));
});
test("rejects mismatched simulation evidence", () => assert.equal(selectPrismaticResearchLiveExample(target, { ...evidence, calculationRunId: "run-B" }), null));
test("missing current evidence leaves the live model unavailable", () => assert.equal(selectPrismaticResearchLiveExample(target, null), null));
