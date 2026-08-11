function number(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function dualKeyCase(value) {
  if (Array.isArray(value)) return value.map(dualKeyCase);
  if (!value || typeof value !== "object") return value;
  const result = {};
  for (const [key, inner] of Object.entries(value)) {
    const converted = dualKeyCase(inner);
    result[key] = converted;
    const snakeKey = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
    if (!(snakeKey in result)) result[snakeKey] = converted;
  }
  return result;
}

function percentileValue(rows, percentile) {
  const match = rows.find((row) => number(row?.percentile) === percentile);
  return number(match?.value);
}

function distributionMaximum(rows) {
  return rows.reduce((highest, row) => {
    const ceiling = number(row?.binCeiling ?? row?.bin_ceiling);
    return ceiling === null ? highest : Math.max(highest, ceiling);
  }, Number.NEGATIVE_INFINITY);
}

/** Adapt the canonical Insights payload for the shared distribution chart. */
export function selectLandingDistribution(payload, fallback = {}) {
  const outcome = payload?.outcomeDistribution || payload?.outcome_distribution || {};
  const percentiles = Array.isArray(outcome.percentiles) ? outcome.percentiles : [];
  const bins = Array.isArray(outcome.distributionBins)
    ? outcome.distributionBins
    : Array.isArray(outcome.distribution_bins) ? outcome.distribution_bins : [];
  const thresholdBins = Array.isArray(outcome.thresholdBins)
    ? outcome.thresholdBins
    : Array.isArray(outcome.threshold_bins) ? outcome.threshold_bins : [];

  if (bins.length === 0 && thresholdBins.length === 0) return null;
  const measuredMaximum = distributionMaximum(bins);

  const markers = [
    { key: "p05", short: "P05", label: "Bad Floor", value: percentileValue(percentiles, 5) ?? number(fallback.p05Value) },
    { key: "p50", short: "P50", label: "Typical Opening", value: percentileValue(percentiles, 50) ?? number(fallback.medianValue) },
    { key: "p95", short: "P95", label: "Strong Upside", value: percentileValue(percentiles, 95) ?? number(fallback.p95Value) },
    { key: "p99", short: "P99", label: "Jackpot Upside", value: percentileValue(percentiles, 99) ?? number(fallback.p99Value) },
    { key: "max", short: "MAX", label: "Best Pull", value: number(fallback.maxValue) ?? (Number.isFinite(measuredMaximum) ? measuredMaximum : null) },
  ].filter((marker) => marker.value !== null);

  return {
    bins: dualKeyCase(bins),
    thresholdBins: dualKeyCase(thresholdBins),
    markers,
  };
}
