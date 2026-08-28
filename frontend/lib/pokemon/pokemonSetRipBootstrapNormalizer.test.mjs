import assert from "node:assert/strict";
import test from "node:test";

import { normalizePokemonSetRipBootstrap } from "./pokemonSetRipBootstrapNormalizer.mjs";
import { resolveCanonicalRipV7, readCanonicalBlock } from "../../components/explore/canonicalRipV7.mjs";
import { selectCompatibleSetRipGlobalContext } from "./pokemonSetRipGlobalContextClient.mjs";

test("bootstrap adapts current V10 without transporting legacy models", () => {
  const normalized = normalizePokemonSetRipBootstrap({
    contractVersion: "pokemon-set-rip-bootstrap-v1",
    set: { id: "set-1", name: "Ascended Heroes" },
    calculationRunId: "run-new",
    marketDate: "2026-08-28",
    canonicalRip: {
      overall: { leaderNormalizedScore: 91, relativeScore: 90, rank: 1 },
      financial: { leaderNormalizedScore: 81, relativeScore: 80, rank: 2 },
      collector: { relativeScore: 70, rank: 3 },
    },
    ripDecision: { sourceCalculationRunId: "run-new", products: [{ id: "current" }] },
    collectorSubjects: [{ name: "Pikachu" }],
  });
  const stale = { publicRipContractV10: { overallRip: { leaderNormalizedScore: 12, relativeScore: 11 } }, ripDecision: { products: [{ id: "stale" }] } };
  const canonical = resolveCanonicalRipV7(normalized.canonicalSource, stale);
  assert.equal(readCanonicalBlock(canonical.overall).publicScore, 91);
  assert.equal(normalized.ripDecision.products[0].id, "current");
  assert.equal(canonical.collectorAppeal.topSubjects[0].name, "Pikachu");
  assert.equal(JSON.stringify(normalized).includes("publicRipContractV9"), false);
});

test("global context is consumed only for the matching ready generation", () => {
  const ready = { compatible: true, status: "ready", expectedCalculationRunId: "run-1" };
  assert.equal(selectCompatibleSetRipGlobalContext(ready, "run-1"), ready);
  assert.equal(selectCompatibleSetRipGlobalContext({ ...ready, compatible: false }, "run-1"), null);
  assert.equal(selectCompatibleSetRipGlobalContext(ready, "run-2"), null);
});

