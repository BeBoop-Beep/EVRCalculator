import { getHistoryDateKey } from "./historyDateFormatting.mjs";

// Freshness-aware selection of Performance vs Cost history.
//
// The set-detail page can see the same simulation history through two
// different snapshots: the set-page /insights payload's history_trend
// (embedded in pokemon_set_page_snapshot_latest) and the market-dashboard /
// overview payload's performanceVsCostHistory (from
// pokemon_set_market_dashboard_snapshot_latest). The two are rebuilt on
// independent schedules, so either one can lag the other by days. Picking
// whichever array happens to be nonempty silently freezes the chart on the
// staler snapshot; the merge below instead combines both per real snapshot
// date so every legitimate point survives and the freshest row wins each day.

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

const DATE_KEYS = ["date", "snapshotDate", "snapshot_date", "sourceDate", "source_date"];
const RUN_TIMESTAMP_KEYS = ["runCreatedAt", "run_created_at", "runAt", "run_at"];

// Field groups that make a Performance vs Cost row renderable. Each group
// counts once toward completeness regardless of which key spelling carried
// the value (the key lists mirror normalizeHistoryTrendPoint /
// normalizeSimulationPerformanceHistory).
const COMPLETENESS_FIELD_GROUPS = [
  // mean / simulated expected value ratio
  [
    "mean_value_to_cost_ratio",
    "meanValueToCostRatio",
    "simulated_mean_pack_value_vs_pack_cost",
    "simulatedMeanPackValueVsPackCost",
    "average_return_vs_cost",
    "averageReturnVsCost",
    "mean_cost_ratio",
    "meanCostRatio",
    "average_return_ratio",
    "averageReturnRatio",
  ],
  // median / P50 ratio
  [
    "median_value_to_cost_ratio",
    "medianValueToCostRatio",
    "simulated_median_pack_value_vs_pack_cost",
    "simulatedMedianPackValueVsPackCost",
    "typical_return_vs_cost",
    "typicalReturnVsCost",
    "typical_value_to_cost_ratio",
    "typicalValueToCostRatio",
    "median_cost_ratio",
    "medianCostRatio",
    "typical_return_ratio",
    "typicalReturnRatio",
  ],
  // P95 ratio
  ["p95_value_to_cost_ratio", "p95ValueToCostRatio", "p95_cost_ratio", "p95CostRatio", "big_hit_upside_ratio", "bigHitUpsideRatio"],
  // pack cost
  ["pack_cost", "packCost", "cost"],
  // mean dollar value
  ["mean_value", "meanValue", "average_pack_value", "averagePackValue", "simulated_mean_pack_value", "simulatedMeanPackValue", "mean_pack_value", "meanPackValue"],
  // median dollar value
  ["median_value", "medianValue", "typical_pack_value", "typicalPackValue", "simulated_median_pack_value", "simulatedMedianPackValue", "median_pack_value", "medianPackValue"],
];

export function getPerformanceHistoryDate(row) {
  if (!row || typeof row !== "object") {
    return null;
  }
  for (const key of DATE_KEYS) {
    const date = getHistoryDateKey(row[key]);
    if (date) {
      return date;
    }
  }
  return null;
}

export function getPerformanceHistoryRunTimestamp(row) {
  if (!row || typeof row !== "object") {
    return null;
  }
  for (const key of RUN_TIMESTAMP_KEYS) {
    const raw = row[key];
    if (!raw) {
      continue;
    }
    const parsed = new Date(raw).getTime();
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

export function isCarriedForwardPerformancePoint(row) {
  return Boolean(row?.isCarriedForward ?? row?.is_carried_forward);
}

function getPerformanceCompleteness(row) {
  if (!row || typeof row !== "object") {
    return 0;
  }
  let score = 0;
  for (const keys of COMPLETENESS_FIELD_GROUPS) {
    if (firstFiniteNumber(row, keys) !== null) {
      score += 1;
    }
  }
  return score;
}

// True when `candidate` should replace `existing` for the same snapshot date.
function shouldReplaceMergedRow(existing, candidate) {
  // A real observation must never be displaced by a carried-forward copy —
  // and always displaces one — regardless of run timestamps.
  if (existing.carried !== candidate.carried) {
    return existing.carried;
  }

  const existingRunTs = getPerformanceHistoryRunTimestamp(existing.row);
  const candidateRunTs = getPerformanceHistoryRunTimestamp(candidate.row);
  if (existingRunTs !== null && candidateRunTs !== null && existingRunTs !== candidateRunTs) {
    return candidateRunTs > existingRunTs;
  }

  const existingCompleteness = getPerformanceCompleteness(existing.row);
  const candidateCompleteness = getPerformanceCompleteness(candidate.row);
  if (existingCompleteness !== candidateCompleteness) {
    return candidateCompleteness > existingCompleteness;
  }

  return candidate.sourcePriority > existing.sourcePriority;
}

/**
 * Merge the set-page embedded history with the market-dashboard history into
 * one date-keyed series. Neither input array is mutated; each output row is a
 * shallow copy of the winning source row with canonical snapshotDate /
 * snapshot_date keys guaranteed, sorted ascending by date.
 */
export function mergePerformanceHistories({ setPageHistory, marketHistory } = {}) {
  const merged = new Map();

  const ingest = (history, sourcePriority) => {
    (Array.isArray(history) ? history : []).forEach((row) => {
      const date = getPerformanceHistoryDate(row);
      if (!date) {
        return;
      }
      const candidate = {
        row,
        date,
        carried: isCarriedForwardPerformancePoint(row),
        sourcePriority,
      };
      const existing = merged.get(date);
      if (!existing || shouldReplaceMergedRow(existing, candidate)) {
        merged.set(date, candidate);
      }
    });
  };

  // The market-dashboard series rebuilds on the daily pipeline and is the
  // fresher source when nothing else (carried flag, run timestamp,
  // completeness) distinguishes two rows for the same date.
  ingest(setPageHistory, 1);
  ingest(marketHistory, 2);

  return Array.from(merged.values())
    .sort((a, b) => a.date.localeCompare(b.date))
    .map(({ row, date }) => ({ ...row, snapshotDate: date, snapshot_date: date }));
}

/**
 * Latest date backed by a real (non-carried-forward) point. Carried rows may
 * remain in the series for chart continuity, but they must never be reported
 * as the history's freshness.
 */
export function getLatestRealPerformanceDate(history) {
  let latest = null;
  (Array.isArray(history) ? history : []).forEach((row) => {
    if (isCarriedForwardPerformancePoint(row)) {
      return;
    }
    const date = getPerformanceHistoryDate(row);
    if (date && (!latest || date > latest)) {
      latest = date;
    }
  });
  return latest;
}
