// Pure, framework-free helpers for the set-detail Simulation Results → Metrics
// tab. Kept out of RipStatisticsPageClient.jsx so the normalization/derivation
// logic can be unit-tested in isolation (see simulationMetricsSelector.test.mjs).
//
// HARD RULE: never invent a metric. Every helper returns null / { available:
// false } when the underlying field is missing so the UI can render an honest
// "not available in this snapshot" state instead of a fabricated number.

export function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function firstFiniteField(source, keys = []) {
  if (!source || typeof source !== "object") {
    return null;
  }
  for (const key of keys) {
    const value = toFiniteNumber(source[key]);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

// Percentile rows arrive as [{ percentile, value }], where `percentile` may be
// expressed as a whole number (95) or a fraction (0.95). Mirrors the page
// client's getPercentileValue so the Metrics tab and the distribution chart
// agree on which point is which.
export function selectPercentileValue(percentiles, requestedPercentile) {
  if (!Array.isArray(percentiles)) {
    return null;
  }
  const matched = percentiles.find((entry) => {
    const percentile = toFiniteNumber(entry?.percentile);
    if (percentile === null) {
      return false;
    }
    return (
      Math.abs(percentile - requestedPercentile) < 0.001 ||
      Math.abs(percentile - requestedPercentile * 100) < 0.001
    );
  });
  return matched ? toFiniteNumber(matched.value) : null;
}

// Variance is preferred from an explicit backend field; when only std_dev is
// available we derive variance = std_dev^2 and flag it so the UI can label it
// "Derived from std dev" (never present a derived number as a primary export).
export function deriveVariance(summary) {
  const explicit = firstFiniteField(summary, ["variance", "value_variance", "valueVariance"]);
  if (explicit !== null) {
    return { value: explicit, derived: false };
  }
  const stdDev = firstFiniteField(summary, ["std_dev", "stdDev", "standard_deviation", "standardDeviation"]);
  if (stdDev !== null) {
    return { value: stdDev * stdDev, derived: true };
  }
  return { value: null, derived: false };
}

// Deterministic/calculated EV is computed by the backend runner as
// calculated_expected_value_per_pack (total_manual_ev). It is not guaranteed to
// be present in every set-page snapshot summary yet, so support every candidate
// key name and return null when none are present.
export function selectCalculatedExpectedValue(summary) {
  return firstFiniteField(summary, [
    "calculated_expected_value",
    "calculatedExpectedValue",
    "calculated_expected_value_per_pack",
    "calculatedExpectedValuePerPack",
    "calculated_ev",
    "calculatedEv",
    "manual_expected_value",
    "manualExpectedValue",
    "manual_ev",
    "manualEv",
    "expected_value_calculated",
    "expectedValueCalculated",
    "ev_calculated",
    "evCalculated",
    "deterministic_expected_value",
    "deterministicExpectedValue",
  ]);
}

export function selectSimulatedExpectedValue(summary) {
  return firstFiniteField(summary, [
    "mean_value",
    "meanValue",
    "simulated_mean_pack_value",
    "simulatedMeanPackValue",
    "actual_simulated_ev",
    "actualSimulatedEv",
  ]);
}

// Model Agreement compares deterministic/calculated EV against the Monte Carlo
// (simulated) mean. It is NOT a truth-confidence score — it says nothing about
// whether pull-rate assumptions or market prices are correct. Returns
// { available: false } whenever either input is missing so the UI never invents
// a score.
export function computeModelAgreement({ calculatedEV, simulatedEV } = {}) {
  const calc = toFiniteNumber(calculatedEV);
  const sim = toFiniteNumber(simulatedEV);
  if (calc === null || sim === null) {
    return { available: false, score: null, delta: null, deltaPercent: null };
  }
  const delta = sim - calc;
  const denom = Math.max(Math.abs(calc), Math.abs(sim), 1);
  const agreementRatio = 1 - Math.min(Math.abs(delta) / denom, 1);
  const score = agreementRatio * 100;
  const deltaPercent = Math.abs(calc) > 1e-9 ? (delta / Math.abs(calc)) * 100 : null;
  return { available: true, score, delta, deltaPercent };
}

// Standard error of the Monte Carlo mean = std_dev / sqrt(n). The 95% band is
// ±1.96 * standardError. Both return null unless std_dev and a positive
// simulation count are present.
export function computeStandardError(stdDev, simulationCount) {
  const std = toFiniteNumber(stdDev);
  const n = toFiniteNumber(simulationCount);
  if (std === null || n === null || n <= 0) {
    return null;
  }
  return std / Math.sqrt(n);
}

export function computeMonteCarloBand(standardError) {
  const se = toFiniteNumber(standardError);
  if (se === null) {
    return null;
  }
  return 1.96 * se;
}
