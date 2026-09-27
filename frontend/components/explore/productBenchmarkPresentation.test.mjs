import assert from "node:assert/strict";
import test from "node:test";
import { compactFamilyBenchmarkLabel, productBenchmarkMetrics } from "./productBenchmarkPresentation.mjs";

const benchmark = {
  opening_economics_reference: { source: "published" },
  rows: [
    { entity_type: "sealed_product", entity_id: "p1", metric_key: "overall", benchmark_status: "available", benchmark_score: 6.4, rank: 2, cohort_size: 12 },
    { entity_type: "sealed_product", entity_id: "p1", metric_key: "financial", benchmark_status: "available", benchmark_score: 5, modeled_return_on_spend: 0.8, expected_value_per_pack: 3.2 },
    { entity_type: "sealed_product", entity_id: "p1", metric_key: "chase", benchmark_status: "available", benchmark_score: 7.2 },
    { entity_type: "sealed_product", entity_id: "p1", metric_key: "collector", benchmark_status: "available", benchmark_score: 8.1 },
  ],
};

test("Product metrics use native Overall and Financial plus inherited Set pillars", () => {
  const metrics = productBenchmarkMetrics({ sealedProductId: "p1" }, benchmark);
  assert.deepEqual([metrics.overall.score, metrics.overall.rank, metrics.overall.cohortSize], [6.4, 2, 12]);
  assert.equal(metrics.financial.score, 5);
  assert.equal(metrics.financial.financialEvidence.expectedValuePerPack, 3.2);
  assert.deepEqual([metrics.chase.score, metrics.collector.score], [7.2, 8.1]);
});

test("family context uses compact labels where useful", () => {
  assert.equal(compactFamilyBenchmarkLabel("Elite Trainer Box"), "ETB");
  assert.equal(compactFamilyBenchmarkLabel("Booster Box"), "Booster Box");
});
