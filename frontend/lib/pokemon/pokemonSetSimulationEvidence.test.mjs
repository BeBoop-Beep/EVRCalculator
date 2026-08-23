import assert from "node:assert/strict";
import test from "node:test";
import { selectRequestedPokemonSetTarget, selectSameSetSimulationEvidence } from "./pokemonSetSimulationEvidence.mjs";

const evidence = { contractVersion: "pokemon-set-simulation-evidence-v1", setId: "prismatic", calculationRunId: "run-2", distributionBins: [{ x: 1 }], thresholdBins: [], percentiles: [], summary: {} };
test("accepts only same-set same-run simulation evidence", () => {
  assert.ok(selectSameSetSimulationEvidence(evidence, { setId: "prismatic", calculationRunId: "run-2" }));
  assert.equal(selectSameSetSimulationEvidence(evidence, { setId: "ascended", calculationRunId: "run-2" }), null);
  assert.equal(selectSameSetSimulationEvidence(evidence, { setId: "prismatic", calculationRunId: "old" }), null);
});
test("requested target wins over a stale selected target during navigation", () => {
  const prismatic = { target_id: "prismatic", name: "Prismatic Evolutions" };
  const ascended = { target_id: "ascended", name: "Ascended Heroes" };
  assert.equal(selectRequestedPokemonSetTarget([ascended, prismatic], "prismatic", ascended), prismatic);
  assert.equal(selectRequestedPokemonSetTarget([ascended], "prismatic", ascended), null);
});
