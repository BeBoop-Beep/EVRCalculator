import {
  calculatePearsonCorrelation,
  calculateSpearmanCorrelation,
  getFirstNumericMetric,
  toOptionalNumber,
  toOptionalString,
} from "../sharedStats.mjs";

export const DESIRABILITY_VALIDATION_METRICS = [
  {
    key: "setValue",
    label: "Set Value",
    summaryLabel: "Set Value",
    sampleLabel: "opening sets with value data",
    valueKeys: [],
  },
  {
    key: "packCost",
    label: "Pack Cost",
    summaryLabel: "Pack Market Price",
    sampleLabel: "opening sets with pack cost",
    valueKeys: ["pack_cost", "packCost", "current_pack_cost", "currentPackCost"],
  },
  {
    key: "expectedValue",
    label: "Expected Value",
    summaryLabel: "Expected Value",
    sampleLabel: "simulated opening sets",
    valueKeys: ["mean_value", "meanValue", "expected_value", "expectedValue", "average_pack_value", "averagePackValue"],
  },
  {
    key: "p95",
    label: "P95",
    summaryLabel: "Cost-Adjusted P95 Upside",
    sampleLabel: "simulated opening sets",
    valueKeys: ["p95_value_to_cost_ratio", "p95ValueToCostRatio", "big_hit_upside", "bigHitUpside"],
  },
];

function latestSetValueFromHistory(history, sourceKey) {
  if (!Array.isArray(history)) {
    return { key: null, value: null };
  }
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const point = history[index];
    const value = toOptionalNumber(point?.setValue ?? point?.set_value ?? point?.value);
    if (value !== null && value > 0) {
      return { key: sourceKey, value };
    }
  }
  return { key: null, value: null };
}

export function getValidationSetValueMetric(row) {
  if (!row || typeof row !== "object") {
    return { key: null, value: null, usedCompatibilityFallback: false };
  }

  const direct = [
    { key: "currentChecklistSetValue", value: row.currentChecklistSetValue },
    { key: "current_checklist_set_value", value: row.current_checklist_set_value },
    { key: "set_value_for_validation", value: row.set_value_for_validation },
    { key: "setValueForValidation", value: row.setValueForValidation },
    { key: "checklistSetValue", value: row.checklistSetValue },
    { key: "checklist_set_value", value: row.checklist_set_value },
    { key: "summary.currentChecklistSetValue", value: row.summary?.currentChecklistSetValue },
    { key: "summary.current_checklist_set_value", value: row.summary?.current_checklist_set_value },
    { key: "summary.set_value_for_validation", value: row.summary?.set_value_for_validation },
    { key: "summary.setValueForValidation", value: row.summary?.setValueForValidation },
    { key: "summary.checklistSetValue", value: row.summary?.checklistSetValue },
    { key: "summary.checklist_set_value", value: row.summary?.checklist_set_value },
    { key: "market.currentChecklistSetValue", value: row.market?.currentChecklistSetValue },
    { key: "market.current_checklist_set_value", value: row.market?.current_checklist_set_value },
    { key: "market.set_value_for_validation", value: row.market?.set_value_for_validation },
    { key: "market.setValueForValidation", value: row.market?.setValueForValidation },
    { key: "market.checklistSetValue", value: row.market?.checklistSetValue },
    { key: "market.checklist_set_value", value: row.market?.checklist_set_value },
  ];
  for (const entry of direct) {
    const value = toOptionalNumber(entry.value);
    if (value !== null && value > 0) {
      return { key: entry.key, value, usedCompatibilityFallback: false };
    }
  }

  const historiesByScope =
    row.setValueHistoriesByScope ||
    row.set_value_histories_by_scope ||
    row.market?.setValueHistoriesByScope ||
    row.market?.set_value_histories_by_scope ||
    row.marketDashboard?.setValueHistoriesByScope ||
    row.marketDashboard?.set_value_histories_by_scope ||
    row.snapshot?.setValueHistoriesByScope ||
    row.snapshot?.set_value_histories_by_scope ||
    null;
  const historyMetric = latestSetValueFromHistory(historiesByScope?.standard || historiesByScope?.checklist, "setValueHistoriesByScope.standard");
  if (historyMetric.value !== null) {
    return { ...historyMetric, usedCompatibilityFallback: false };
  }

  const directHistoryMetric = latestSetValueFromHistory(row.setValueHistory || row.set_value_history, "setValueHistory");
  if (directHistoryMetric.value !== null) {
    return { ...directHistoryMetric, usedCompatibilityFallback: false };
  }

  for (const entry of [
    { key: "simulated_set_value", value: row.simulated_set_value },
    { key: "simulatedSetValue", value: row.simulatedSetValue },
    { key: "summary.simulated_set_value", value: row.summary?.simulated_set_value },
    { key: "summary.simulatedSetValue", value: row.summary?.simulatedSetValue },
  ]) {
    const value = toOptionalNumber(entry.value);
    if (value !== null && value > 0) {
      return { key: entry.key, value, usedCompatibilityFallback: true };
    }
  }

  return { key: null, value: null, usedCompatibilityFallback: false };
}

function isOpeningSetRow(row) {
  const type = String(row?.target_type || row?.targetType || row?.type || row?.scope || "").toLowerCase();
  if (type && !["set", "pokemon_set", "opening_set", "pack"].includes(type)) {
    return false;
  }
  return true;
}

function getMetricValue(row, metric) {
  if (metric?.key === "setValue") {
    return getValidationSetValueMetric(row);
  }
  return getFirstNumericMetric(row, metric?.valueKeys || []);
}

function buildPoint(row, metric) {
  const x =
    getFirstNumericMetric(row, ["desirability_score", "desirabilityScore", "pure_desirability_score", "pureDesirabilityScore"]).value ??
    getFirstNumericMetric(row, ["relative_desirability_score", "relativeDesirabilityScore"]).value;
  const metricResult = getMetricValue(row, metric);
  const y = metricResult.value;
  if (x === null || y === null) {
    return null;
  }
  return {
    kind: "set",
    x,
    y,
    ySourceKey: metricResult.key,
    usedCompatibilityFallback: Boolean(metricResult.usedCompatibilityFallback),
    name: toOptionalString(row?.name || row?.set_name || row?.setName || row?.target_id) || "Unknown Set",
    slug: toOptionalString(row?.slug || row?.canonical_key || row?.target_id),
    era: toOptionalString(row?.era || row?.era_name || row?.eraName),
    ripScore: getFirstNumericMetric(row, ["relative_pack_score", "relativePackScore", "pack_score", "packScore"]).value,
    rank: getFirstNumericMetric(row, ["pack_rank", "packRank", "rank"]).value,
  };
}

export function selectDesirabilityValidation(rawRows, { metricKey = "setValue" } = {}) {
  const rows = Array.isArray(rawRows) ? rawRows : [];
  const metric = DESIRABILITY_VALIDATION_METRICS.find((entry) => entry.key === metricKey) || DESIRABILITY_VALIDATION_METRICS[0];
  const diagnostics = {
    totalRows: rows.length,
    rowsWithDesirability: 0,
    rowsWithSelectedMetric: 0,
    rowsExcludedByOpeningSetFilter: 0,
    finalPlottedRows: 0,
    compatibilityFallbackRows: 0,
    firstRejectionReasons: [],
  };

  const points = [];
  rows.forEach((row) => {
    const desirability =
      getFirstNumericMetric(row, ["desirability_score", "desirabilityScore", "pure_desirability_score", "pureDesirabilityScore"]).value ??
      getFirstNumericMetric(row, ["relative_desirability_score", "relativeDesirabilityScore"]).value;
    const metricResult = getMetricValue(row, metric);
    if (desirability !== null) diagnostics.rowsWithDesirability += 1;
    if (metricResult.value !== null) diagnostics.rowsWithSelectedMetric += 1;
    if (metricResult.usedCompatibilityFallback) diagnostics.compatibilityFallbackRows += 1;

    if (!isOpeningSetRow(row)) {
      diagnostics.rowsExcludedByOpeningSetFilter += 1;
      if (diagnostics.firstRejectionReasons.length < 6) diagnostics.firstRejectionReasons.push("not_opening_set");
      return;
    }
    const point = buildPoint(row, metric);
    if (!point) {
      if (diagnostics.firstRejectionReasons.length < 6) {
        diagnostics.firstRejectionReasons.push(desirability === null ? "missing_desirability" : "missing_selected_metric");
      }
      return;
    }
    points.push(point);
  });

  points.sort((left, right) => left.x - right.x);
  diagnostics.finalPlottedRows = points.length;

  return {
    rows: rows.map((row) => ({ ...row })),
    metric,
    points,
    pearson: calculatePearsonCorrelation(points),
    spearman: calculateSpearmanCorrelation(points),
    sampleCount: points.length,
    diagnostics,
  };
}
