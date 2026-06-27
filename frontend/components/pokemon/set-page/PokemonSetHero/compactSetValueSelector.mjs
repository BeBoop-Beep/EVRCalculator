import {
  getSelectedDeltaWindowFromHistory,
  getVisibleHistoryWindowMetrics,
} from "../../../../lib/explore/marketDeltaWindows.mjs";
import { toOptionalNumber } from "../sharedStats.mjs";

function normalizePoint(point) {
  const date = String(point?.date || point?.snapshotDate || point?.snapshot_date || "").slice(0, 10);
  const setValue = toOptionalNumber(point?.setValue ?? point?.set_value ?? point?.value);
  return date && setValue !== null
    ? {
        ...point,
        date,
        setValue,
        isCarriedForward: Boolean(point?.isCarriedForward ?? point?.is_carried_forward),
        sourceDate: String(point?.sourceDate || point?.source_date || "").slice(0, 10) || null,
      }
    : null;
}

export function selectCompactSetValue({ history, historiesByScope, fallbackMetric } = {}) {
  const sourceHistory = Array.isArray(historiesByScope?.standard)
    ? historiesByScope.standard
    : Array.isArray(history)
    ? history
    : [];
  const points = sourceHistory.map(normalizePoint).filter(Boolean).sort((a, b) => a.date.localeCompare(b.date));
  const { selectedWindow } = getSelectedDeltaWindowFromHistory(points, {
    selectedKey: "30D",
    preferredKey: "30D",
    dateKey: "date",
    valueKey: "setValue",
    preferObservedPoints: true,
  });
  const metrics = getVisibleHistoryWindowMetrics(points, selectedWindow, {
    dateKey: "date",
    valueKey: "setValue",
    preferObservedPoints: true,
  });
  const fallbackValue = toOptionalNumber(fallbackMetric?.value);

  return {
    value: metrics.currentValue ?? fallbackValue,
    sourceKey: metrics.currentValue !== null ? "setValueHistoriesByScope.standard" : fallbackMetric?.key || null,
    visiblePoints: metrics.points,
    deltaAmount: metrics.deltaAmount,
    deltaPercent: metrics.deltaPercent,
    asOf: metrics.latestPoint?.sourceDate || metrics.latestPoint?.date || points.at(-1)?.sourceDate || points.at(-1)?.date || null,
    diagnostics: {
      sourcePointCount: points.length,
      usedFallback: metrics.currentValue === null && fallbackValue !== null,
    },
  };
}
