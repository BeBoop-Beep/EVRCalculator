import assert from "node:assert/strict";
import test from "node:test";
import { selectSameRunRipAdvanced, selectSameRunRipSimulation } from "./pokemonSetRipProgressiveClient.mjs";

test("simulation accepts only the selected set and bootstrap run", () => {
  const payload = { contractVersion: "pokemon-set-rip-simulation-evidence-v1", setId: "set-a", calculationRunId: "run-a", percentiles: [{ percentile: 50, value: 4 }], distributionBins: [], thresholdBins: [] };
  assert.ok(selectSameRunRipSimulation(payload, { setId: "set-a", calculationRunId: "run-a" }));
  assert.equal(selectSameRunRipSimulation(payload, { setId: "set-b", calculationRunId: "run-a" }), null);
  assert.equal(selectSameRunRipSimulation(payload, { setId: "set-a", calculationRunId: "run-b" }), null);
});

test("advanced rejects stale runs and headline parity failures", () => {
  const payload = { contractVersion: "pokemon-set-rip-advanced-v1", setId: "set-a", calculationRunId: "run-a", financialRip: { leaderNormalizedScore: 82, rank: 2 }, collectorAppeal: { leaderNormalizedScore: 75 }, rarityContribution: [] };
  const bootstrapCanonical = { publicRipContractV10: { financialRip: { leaderNormalizedScore: 82, rank: 2 }, collectorAppeal: { leaderNormalizedScore: 75 } } };
  assert.ok(selectSameRunRipAdvanced(payload, { setId: "set-a", calculationRunId: "run-a", bootstrapCanonical }));
  assert.equal(selectSameRunRipAdvanced(payload, { setId: "set-a", calculationRunId: "old", bootstrapCanonical }), null);
  assert.equal(selectSameRunRipAdvanced({ ...payload, financialRip: { leaderNormalizedScore: 81, rank: 2 } }, { setId: "set-a", calculationRunId: "run-a", bootstrapCanonical }), null);
});
