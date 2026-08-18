import assert from "node:assert/strict";
import test from "node:test";
import { normalizePokemonSetInsightsCriticalPayload } from "./pokemonSetInsightsCriticalNormalizer.mjs";
import { adaptCriticalInsightsToExplorePayload } from "./pokemonSetInsightsCriticalExploreAdapter.mjs";

test("ripDecision survives critical normalization and the Explore adapter unchanged", () => {
  const ripDecision = {
    contractVersion: "rip-decision-contract-v1",
    sourceCalculationRunId: "run-current",
    currentRunAvailable: true,
    sealedProducts: { productCount: 1, products: [{ sealedProductId: "sku-1" }] },
    topChase: { cardName: "Chase" },
  };
  const normalized = normalizePokemonSetInsightsCriticalPayload({ ripDecision });
  const explorePayload = adaptCriticalInsightsToExplorePayload(normalized);
  assert.equal(normalized.ripDecision, ripDecision);
  assert.equal(explorePayload.ripDecision, ripDecision);
});
