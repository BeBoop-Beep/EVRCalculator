function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function firstFiniteNumber(raw, keys) {
  for (const key of keys) {
    const value = toNumber(raw?.[key]);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

function firstFiniteMetric(raw, keys) {
  for (const key of keys) {
    const value = toNumber(raw?.[key]);
    if (value !== null) {
      return { key, value };
    }
  }
  return { key: null, value: null };
}

function resolveDollarValue(explicitValue, ratioValue, packCostValue) {
  const explicit = toNumber(explicitValue);
  const ratio = toNumber(ratioValue);
  const packCost = toNumber(packCostValue);

  if (explicit !== null) {
    if (ratio !== null && packCost !== null) {
      const derived = ratio * packCost;
      if (Math.abs(explicit) < 1e-9 && Math.abs(derived) > 1e-6) {
        return derived;
      }
    }
    return explicit;
  }

  if (ratio === null || packCost === null) {
    return null;
  }

  return ratio * packCost;
}

function normalizeReturnMetrics(ratioValue, explicitValue, packCostValue) {
  const ratio = toNumber(ratioValue);
  const explicit = toNumber(explicitValue);
  const packCost = toNumber(packCostValue);

  if (ratio !== null && ratio >= 0) {
    return {
      returnValue:
        explicit !== null && Math.abs(explicit) > 1e-9
          ? explicit
          : (packCost !== null && packCost > 0 ? ratio * packCost : null),
      ratioValue: ratio,
    };
  }

  if (explicit !== null) {
    return {
      returnValue: explicit,
      ratioValue: packCost !== null && packCost > 0 ? explicit / packCost : null,
    };
  }

  if (ratio === null || ratio < 0) {
    return {
      returnValue: null,
      ratioValue: null,
    };
  }

  return {
    returnValue: packCost !== null && packCost > 0 ? ratio * packCost : null,
    ratioValue: ratio,
  };
}

function isEffectivelyZero(value, epsilon = 1e-6) {
  const parsed = toNumber(value);
  return parsed !== null && Math.abs(parsed) <= epsilon;
}

export function shouldUseSummaryRatioFallback(latestRatio, summaryRatio) {
  const latest = toNumber(latestRatio);
  const summary = toNumber(summaryRatio);

  if (summary === null || isEffectivelyZero(summary)) {
    return false;
  }

  if (latest === null) {
    return true;
  }

  return isEffectivelyZero(latest);
}

export function patchLatestHistoryRowWithSummaryRatios(
  latestRow,
  { meanRatioSummary = null, medianRatioSummary = null, effectivePackCost = null } = {}
) {
  const useSummaryMeanRatio = shouldUseSummaryRatioFallback(latestRow?.meanCostRatio, meanRatioSummary);
  const useSummaryMedianRatio = shouldUseSummaryRatioFallback(latestRow?.medianCostRatio, medianRatioSummary);

  const resolvedMeanRatio = useSummaryMeanRatio ? toNumber(meanRatioSummary) : toNumber(latestRow?.meanCostRatio);
  const resolvedMedianRatio = useSummaryMedianRatio ? toNumber(medianRatioSummary) : toNumber(latestRow?.medianCostRatio);
  const resolvedPackCost = toNumber(effectivePackCost);

  return {
    ...latestRow,
    meanCostRatio: resolvedMeanRatio,
    medianCostRatio: resolvedMedianRatio,
    meanValue: useSummaryMeanRatio
      ? (resolvedMeanRatio !== null && resolvedPackCost !== null ? resolvedMeanRatio * resolvedPackCost : null)
      : (latestRow?.meanValue ??
        (resolvedMeanRatio !== null && resolvedPackCost !== null ? resolvedMeanRatio * resolvedPackCost : null)),
    medianValue: useSummaryMedianRatio
      ? (resolvedMedianRatio !== null && resolvedPackCost !== null ? resolvedMedianRatio * resolvedPackCost : null)
      : (latestRow?.medianValue ??
        (resolvedMedianRatio !== null && resolvedPackCost !== null ? resolvedMedianRatio * resolvedPackCost : null)),
  };
}

export function normalizeHistoryTrendPoint(raw, index, fallbackPackCost) {
  const meanRatioMetric = firstFiniteMetric(raw, [
    "mean_value_to_cost_ratio",
    "meanValueToCostRatio",
    "average_return_vs_cost",
    "averageReturnVsCost",
    "mean_cost_ratio",
    "meanCostRatio",
    "average_return_ratio",
    "averageReturnRatio",
    "simulated_mean_value_to_cost_ratio",
    "simulatedMeanValueToCostRatio",
    "simulated_mean_pack_value_vs_pack_cost",
    "simulatedMeanPackValueVsPackCost",
  ]);
  const medianRatioMetric = firstFiniteMetric(raw, [
    "median_value_to_cost_ratio",
    "medianValueToCostRatio",
    "typical_return_vs_cost",
    "typicalReturnVsCost",
    "typical_value_to_cost_ratio",
    "typicalValueToCostRatio",
    "median_cost_ratio",
    "medianCostRatio",
    "typical_return_ratio",
    "typicalReturnRatio",
    "simulated_median_value_to_cost_ratio",
    "simulatedMedianValueToCostRatio",
    "simulated_median_pack_value_vs_pack_cost",
    "simulatedMedianPackValueVsPackCost",
  ]);
  const p95CostRatio = firstFiniteNumber(raw, [
    "p95_value_to_cost_ratio",
    "p95ValueToCostRatio",
    "p95_cost_ratio",
    "p95CostRatio",
    "big_hit_upside_ratio",
    "bigHitUpsideRatio",
  ]);
  const packCostValue = firstFiniteNumber(raw, ["pack_cost", "packCost", "cost"]) ?? toNumber(fallbackPackCost);

  const meanValueDirect = firstFiniteNumber(raw, [
    "average_pack_value",
    "averagePackValue",
    "simulated_mean_pack_value",
    "simulatedMeanPackValue",
    "mean_pack_value",
    "meanPackValue",
    "mean_value",
    "meanValue",
  ]);
  const medianValueDirect = firstFiniteNumber(raw, [
    "typical_pack_value",
    "typicalPackValue",
    "simulated_median_pack_value",
    "simulatedMedianPackValue",
    "median_pack_value",
    "medianPackValue",
    "median_value",
    "medianValue",
  ]);
  const p95ValueDirect = firstFiniteNumber(raw, [
    "big_hit_value",
    "bigHitValue",
    "simulated_p95_pack_value",
    "simulatedP95PackValue",
    "p95_pack_value",
    "p95PackValue",
    "p95_value",
    "p95Value",
  ]);

  const meanRatioRaw =
    (meanRatioMetric.key === "simulated_mean_pack_value_vs_pack_cost" ||
      meanRatioMetric.key === "simulatedMeanPackValueVsPackCost") &&
    meanRatioMetric.value === 0 &&
    meanValueDirect === null
      ? null
      : meanRatioMetric.value;
  const medianRatioRaw =
    (medianRatioMetric.key === "simulated_median_pack_value_vs_pack_cost" ||
      medianRatioMetric.key === "simulatedMedianPackValueVsPackCost") &&
    medianRatioMetric.value === 0 &&
    medianValueDirect === null
      ? null
      : medianRatioMetric.value;

  const normalizedMean = normalizeReturnMetrics(meanRatioRaw, meanValueDirect, packCostValue);
  const normalizedMedian = normalizeReturnMetrics(medianRatioRaw, medianValueDirect, packCostValue);

  return {
    id: `${index}:${raw?.snapshot_date || raw?.snapshotDate || "na"}:${raw?.calculation_run_id || raw?.calculationRunId || "na"}`,
    rawPoint: raw,
    snapshotDate: raw?.snapshot_date || raw?.snapshotDate || null,
    runCreatedAt: raw?.run_created_at || raw?.runCreatedAt || null,
    calculationRunId: raw?.calculation_run_id || raw?.calculationRunId || null,
    packCost: packCostValue,
    meanCostRatio: normalizedMean.ratioValue,
    medianCostRatio: normalizedMedian.ratioValue,
    p95CostRatio,
    meanValue: normalizedMean.returnValue,
    medianValue: normalizedMedian.returnValue,
    p95Value: resolveDollarValue(p95ValueDirect, p95CostRatio, packCostValue),
  };
}
