import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeHistoryTrendPoint,
  patchLatestHistoryRowWithSummaryRatios,
  shouldUseSummaryRatioFallback,
} from "./packValueHistoryNormalization.mjs";

test("shouldUseSummaryRatioFallback returns true for null or zero latest ratio when summary ratio is non-zero", () => {
  assert.equal(shouldUseSummaryRatioFallback(null, 1.23), true);
  assert.equal(shouldUseSummaryRatioFallback(0, 1.23), true);
  assert.equal(shouldUseSummaryRatioFallback(0.0000002, 1.23), true);
  assert.equal(shouldUseSummaryRatioFallback(0.84, 1.23), false);
  assert.equal(shouldUseSummaryRatioFallback(0, 0), false);
});

test("patchLatestHistoryRowWithSummaryRatios uses summary mean/median ratios when latest historical ratios are zero placeholders", () => {
  const latestRow = {
    snapshotDate: "2026-06-09",
    meanCostRatio: 0,
    medianCostRatio: 0,
    meanValue: 0,
    medianValue: 0,
    p95CostRatio: 2.78,
    p95Value: 82.0,
  };

  const patched = patchLatestHistoryRowWithSummaryRatios(latestRow, {
    meanRatioSummary: 0.5,
    medianRatioSummary: 0.133,
    effectivePackCost: 29.47,
  });

  assert.equal(patched.meanCostRatio, 0.5);
  assert.equal(patched.medianCostRatio, 0.133);
  assert.ok(Math.abs(patched.meanValue - 14.735) < 0.001);
  assert.ok(Math.abs(patched.medianValue - 3.91951) < 0.001);
  assert.equal(patched.p95CostRatio, 2.78);
  assert.equal(patched.p95Value, 82.0);
});

test("normalizeHistoryTrendPoint resolves camelCase historical fields", () => {
  const point = normalizeHistoryTrendPoint(
    {
      snapshotDate: "2026-06-09",
      calculationRunId: "run-123",
      runCreatedAt: "2026-06-09T17:15:58.820087+00:00",
      packCost: 29.47,
      meanValueToCostRatio: 0.5,
      medianValueToCostRatio: 0.133,
      p95ValueToCostRatio: 2.7883,
    },
    0,
    null
  );

  assert.equal(point.snapshotDate, "2026-06-09");
  assert.equal(point.calculationRunId, "run-123");
  assert.equal(point.meanCostRatio, 0.5);
  assert.equal(point.medianCostRatio, 0.133);
  assert.equal(point.p95CostRatio, 2.7883);
});

test("normalizeHistoryTrendPoint resolves snake_case historical fields", () => {
  const point = normalizeHistoryTrendPoint(
    {
      snapshot_date: "2026-06-05",
      calculation_run_id: "run-456",
      run_created_at: "2026-06-05T17:15:58.820087+00:00",
      pack_cost: 29.47,
      mean_value_to_cost_ratio: 0.494,
      median_value_to_cost_ratio: 0.1282,
      p95_value_to_cost_ratio: 2.8173,
    },
    1,
    null
  );

  assert.equal(point.snapshotDate, "2026-06-05");
  assert.equal(point.calculationRunId, "run-456");
  assert.equal(point.meanCostRatio, 0.494);
  assert.equal(point.medianCostRatio, 0.1282);
  assert.equal(point.p95CostRatio, 2.8173);
});
