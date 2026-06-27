import { getHistoryDateKey, getLocalHistoryDateKey } from "./historyDateFormatting.mjs";

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

function hasForwardFillValue(point, valueKeys) {
  if (!Array.isArray(valueKeys) || valueKeys.length === 0) {
    return true;
  }

  return valueKeys.some((key) => {
    const value = point?.[key];
    if (value === null || value === undefined || value === "") {
      return false;
    }
    return toNumber(value) !== null;
  });
}

function shouldReplaceDailyPoint(existing, candidate) {
  if (!existing) {
    return true;
  }

  if (existing.isCarriedForward && !candidate.isCarriedForward) {
    return true;
  }

  if (!existing.isCarriedForward && candidate.isCarriedForward) {
    return false;
  }

  return true;
}

function addDaysToDateKey(dateKey, days) {
  const match = String(dateKey || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return null;
  }
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  date.setUTCDate(date.getUTCDate() + days);
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function forwardFillDailyHistoryThroughToday(
  points,
  {
    dateField = "date",
    valueKeys = ["value"],
    todayDateKey = getLocalHistoryDateKey(),
  } = {}
) {
  const today = getHistoryDateKey(todayDateKey);
  const dailyPointMap = new Map();

  (Array.isArray(points) ? points : []).forEach((point) => {
    if (!point || typeof point !== "object") {
      return;
    }

    const date = getHistoryDateKey(point?.[dateField]);
    if (!date) {
      return;
    }

    const isCarriedForward = Boolean(point?.isCarriedForward ?? point?.is_carried_forward);
    const normalizedPoint = {
      ...point,
      [dateField]: date,
      isCarriedForward,
      sourceDate: point?.sourceDate ?? point?.source_date ?? null,
    };
    const existing = dailyPointMap.get(date);
    if (shouldReplaceDailyPoint(existing, normalizedPoint)) {
      dailyPointMap.set(date, normalizedPoint);
    }
  });

  const rows = Array.from(dailyPointMap.values()).sort((a, b) =>
    String(a?.[dateField] || "").localeCompare(String(b?.[dateField] || ""))
  );
  if (!today || rows.length === 0) {
    return rows;
  }

  const firstActualPoint = rows.find((point) => !point?.isCarriedForward && hasForwardFillValue(point, valueKeys));
  const firstDate = firstActualPoint?.[dateField] || null;
  if (!firstActualPoint || !firstDate || firstDate > today) {
    return rows;
  }

  let carryPoint = null;
  let carryDate = null;
  let cursor = firstDate;
  while (cursor && cursor <= today) {
    const existing = dailyPointMap.get(cursor);
    if (existing && !existing.isCarriedForward && hasForwardFillValue(existing, valueKeys)) {
      carryPoint = existing;
      carryDate = cursor;
    } else if (!existing && carryPoint && carryDate) {
      dailyPointMap.set(cursor, {
        ...carryPoint,
        id: `${carryPoint?.id || carryDate}:carried-forward:${cursor}`,
        [dateField]: cursor,
        isCarriedForward: true,
        sourceDate: carryDate,
        originalPoint: carryPoint?.originalPoint ?? carryPoint?.rawPoint ?? carryPoint,
      });
    }
    cursor = addDaysToDateKey(cursor, 1);
  }

  return Array.from(dailyPointMap.values()).sort((a, b) =>
    String(a?.[dateField] || "").localeCompare(String(b?.[dateField] || ""))
  );
}

export function normalizeHistoryTrendPoint(raw, index, fallbackPackCost) {
  const snapshotDate = getHistoryDateKey(raw?.snapshot_date || raw?.snapshotDate);
  const isCarriedForward = Boolean(raw?.isCarriedForward ?? raw?.is_carried_forward);
  const sourceDate = getHistoryDateKey(raw?.sourceDate ?? raw?.source_date);
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
    id: `${index}:${snapshotDate || "na"}:${raw?.calculation_run_id || raw?.calculationRunId || "na"}`,
    rawPoint: raw,
    snapshotDate,
    runCreatedAt: raw?.run_created_at || raw?.runCreatedAt || null,
    calculationRunId: raw?.calculation_run_id || raw?.calculationRunId || null,
    isCarriedForward,
    sourceDate,
    packCost: packCostValue,
    meanCostRatio: normalizedMean.ratioValue,
    medianCostRatio: normalizedMedian.ratioValue,
    p95CostRatio,
    meanValue: normalizedMean.returnValue,
    medianValue: normalizedMedian.returnValue,
    p95Value: resolveDollarValue(p95ValueDirect, p95CostRatio, packCostValue),
  };
}
