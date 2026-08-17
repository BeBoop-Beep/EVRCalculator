import assert from "node:assert/strict";
import test from "node:test";

import { normalizePokemonSetInsightsCriticalPayload } from "./pokemonSetInsightsCriticalClient.js";

test("critical Insights preserves the canonical ripDecision object", () => {
  const contract = { contractVersion: "rip-decision-contract-v1", topChase: { cardName: "Mega Gengar ex" } };
  assert.equal(normalizePokemonSetInsightsCriticalPayload({ ripDecision: contract }).ripDecision, contract);
});

test("critical Insights preserves absent/null ripDecision as null", () => {
  assert.equal(normalizePokemonSetInsightsCriticalPayload({}).ripDecision, null);
  assert.equal(normalizePokemonSetInsightsCriticalPayload({ ripDecision: null }).ripDecision, null);
});
