import test from "node:test";
import assert from "node:assert/strict";

import {
  deriveVariance,
  selectPercentileValue,
  selectCalculatedExpectedValue,
  computeModelAgreement,
  computeStandardError,
  computeMonteCarloBand,
} from "./simulationMetricsSelector.mjs";

test("deriveVariance prefers an explicit backend field over std_dev", () => {
  const result = deriveVariance({ variance: 12.5, std_dev: 3 });
  assert.equal(result.value, 12.5);
  assert.equal(result.derived, false);
});

test("deriveVariance derives variance from std_dev when no explicit field exists", () => {
  const result = deriveVariance({ std_dev: 4 });
  assert.equal(result.value, 16);
  assert.equal(result.derived, true);
});

test("deriveVariance returns a null value (never 0) when std_dev is missing", () => {
  const result = deriveVariance({ mean_value: 10 });
  assert.equal(result.value, null);
  assert.equal(result.derived, false);
});

test("selectPercentileValue matches a stored whole-number percentile for whole and fractional requests", () => {
  const percentiles = [
    { percentile: 5, value: 1.1 },
    { percentile: 50, value: 4.2 },
    { percentile: 95, value: 9.9 },
  ];
  assert.equal(selectPercentileValue(percentiles, 5), 1.1);
  assert.equal(selectPercentileValue(percentiles, 50), 4.2);
  assert.equal(selectPercentileValue(percentiles, 95), 9.9);
  // A fractional request (0.95) must still resolve the stored 95 point.
  assert.equal(selectPercentileValue(percentiles, 0.95), 9.9);
  assert.equal(selectPercentileValue(percentiles, 99), null);
  assert.equal(selectPercentileValue(null, 50), null);
});

test("selectCalculatedExpectedValue supports the backend runner field name", () => {
  assert.equal(selectCalculatedExpectedValue({ calculated_expected_value_per_pack: 6.75 }), 6.75);
  assert.equal(selectCalculatedExpectedValue({ deterministic_expected_value: 5 }), 5);
  assert.equal(selectCalculatedExpectedValue({ mean_value: 6 }), null, "must not fall back to the simulated mean");
});

test("computeModelAgreement returns unavailable (no invented score) when either EV is missing", () => {
  const missingCalc = computeModelAgreement({ calculatedEV: null, simulatedEV: 6 });
  assert.equal(missingCalc.available, false);
  assert.equal(missingCalc.score, null);
  assert.equal(missingCalc.delta, null);

  const missingSim = computeModelAgreement({ calculatedEV: 6, simulatedEV: undefined });
  assert.equal(missingSim.available, false);
  assert.equal(missingSim.score, null);
});

test("computeModelAgreement scores only when both calculated and simulated EV exist", () => {
  const identical = computeModelAgreement({ calculatedEV: 6, simulatedEV: 6 });
  assert.equal(identical.available, true);
  assert.equal(identical.score, 100);
  assert.equal(identical.delta, 0);
  assert.equal(identical.deltaPercent, 0);

  const diverged = computeModelAgreement({ calculatedEV: 5, simulatedEV: 6 });
  assert.equal(diverged.available, true);
  // denom = max(5, 6, 1) = 6; agreementRatio = 1 - (1/6); score ≈ 83.33
  assert.ok(Math.abs(diverged.score - (1 - 1 / 6) * 100) < 1e-9);
  assert.equal(diverged.delta, 1);
  assert.ok(Math.abs(diverged.deltaPercent - 20) < 1e-9);
});

test("computeStandardError and computeMonteCarloBand require std_dev and a positive count", () => {
  assert.equal(computeStandardError(10, 100), 1);
  assert.equal(computeStandardError(10, 0), null);
  assert.equal(computeStandardError(null, 100), null);

  assert.ok(Math.abs(computeMonteCarloBand(1) - 1.96) < 1e-9);
  assert.equal(computeMonteCarloBand(null), null);
});
