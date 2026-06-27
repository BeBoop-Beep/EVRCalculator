import {
  getSelectedDeltaWindowFromHistory,
  getVisibleHistoryWindowMetrics,
} from "../../lib/explore/marketDeltaWindows.mjs";
import { getHistoryDateKey } from "./historyDateFormatting.mjs";
import { forwardFillDailyHistoryThroughToday } from "./packValueHistoryNormalization.mjs";

export const CANONICAL_SET_VALUE_SCOPE_KEY = "standard";

export const SET_VALUE_TREND_SCOPE_OPTIONS = [
  { key: "standard", label: "Checklist" },
  { key: "hits", label: "Hits" },
  { key: "top10", label: "Top 10" },
];

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeScopeKey(scope) {
  const text = String(scope || "").trim();
  return text || CANONICAL_SET_VALUE_SCOPE_KEY;
}

export function getSetValueTrendScopeLabel(scope) {
  const scopeKey = normalizeScopeKey(scope);
  return SET_VALUE_TREND_SCOPE_OPTIONS.find((entry) => entry.key === scopeKey)?.label || scopeKey;
}

export function getSetValueTrendMetricLabel(scope) {
  return `${getSetValueTrendScopeLabel(scope)} Set Value`;
}

export function normalizeSetValueTrendPoints(points) {
  const dailyPointMap = new Map();

  (Array.isArray(points) ? points : []).forEach((point) => {
    const date = getHistoryDateKey(point?.date ?? point?.snapshotDate ?? point?.snapshot_date);
    const setValue = toNumber(point?.setValue ?? point?.set_value ?? point?.value);
    if (!date) {
      return;
    }
    dailyPointMap.set(date, {
      ...point,
      date,
      setValue,
      isCarriedForward: Boolean(point?.isCarriedForward ?? point?.is_carried_forward),
      sourceDate: getHistoryDateKey(point?.sourceDate ?? point?.source_date),
    });
  });

  return forwardFillDailyHistoryThroughToday(
    Array.from(dailyPointMap.values()).sort((a, b) => a.date.localeCompare(b.date)),
    {
      dateField: "date",
      valueKeys: ["setValue"],
    }
  );
}

export function getSetValueTrendHistoryForScope(input = {}) {
  const safeInput = input && typeof input === "object" ? input : {};
  const { history, historiesByScope, scope = CANONICAL_SET_VALUE_SCOPE_KEY } = safeInput;
  const requestedScope = normalizeScopeKey(scope);
  const scopedHistory = historiesByScope?.[requestedScope];

  if (Array.isArray(scopedHistory)) {
    return {
      history: scopedHistory,
      source: `setValueHistoriesByScope.${requestedScope}`,
      hasRequestedScopeHistory: scopedHistory.length > 0,
    };
  }

  if (requestedScope === CANONICAL_SET_VALUE_SCOPE_KEY && Array.isArray(history)) {
    return {
      history,
      source: "setValueHistory.standard",
      hasRequestedScopeHistory: history.length > 0,
    };
  }

  return {
    history: [],
    source: null,
    hasRequestedScopeHistory: false,
  };
}

export function selectOverviewSetValueTrendByScope(input = {}) {
  const safeInput = input && typeof input === "object" ? input : {};
  const {
    history,
    historiesByScope,
    selectedScope = CANONICAL_SET_VALUE_SCOPE_KEY,
    selectedWindowKey = null,
    preferredWindowKey = "30D",
  } = safeInput;
  const scope = normalizeScopeKey(selectedScope);
  const selectedHistory = getSetValueTrendHistoryForScope({ history, historiesByScope, scope });
  const points = normalizeSetValueTrendPoints(selectedHistory.history);
  const valuedPoints = points.filter((point) => toNumber(point?.setValue) !== null);
  const {
    windows: availableDeltaWindows,
    effectiveKey: effectiveWindowKey,
    selectedWindow,
  } = getSelectedDeltaWindowFromHistory(valuedPoints, {
    selectedKey: selectedWindowKey,
    preferredKey: preferredWindowKey,
    dateKey: "date",
    valueKey: "setValue",
    preferObservedPoints: true,
  });
  const visibleWindowMetrics = getVisibleHistoryWindowMetrics(points, selectedWindow, {
    dateKey: "date",
    valueKey: "setValue",
    preferObservedPoints: true,
  });
  const { selectedWindow: thirtyDayWindow } = getSelectedDeltaWindowFromHistory(valuedPoints, {
    selectedKey: "30D",
    preferredKey: "30D",
    dateKey: "date",
    valueKey: "setValue",
    preferObservedPoints: true,
  });
  const thirtyDayWindowMetrics = getVisibleHistoryWindowMetrics(points, thirtyDayWindow, {
    dateKey: "date",
    valueKey: "setValue",
    preferObservedPoints: true,
  });
  const scopePointCounts = Object.fromEntries(
    Object.entries(historiesByScope || {}).map(([scopeKey, scopeHistory]) => [
      scopeKey,
      Array.isArray(scopeHistory) ? scopeHistory.length : 0,
    ])
  );

  return {
    scope,
    label: getSetValueTrendScopeLabel(scope),
    metricLabel: getSetValueTrendMetricLabel(scope),
    currentValue: visibleWindowMetrics.currentValue,
    deltaAmount: visibleWindowMetrics.deltaAmount,
    deltaPercent: visibleWindowMetrics.deltaPercent,
    delta30d: thirtyDayWindowMetrics.deltaAmount,
    delta30dPct: thirtyDayWindowMetrics.deltaPercent,
    series: visibleWindowMetrics.points,
    points,
    valuedPoints,
    firstPoint: visibleWindowMetrics.firstPoint,
    lastPoint: visibleWindowMetrics.latestPoint,
    selectedWindow,
    availableDeltaWindows,
    effectiveWindowKey,
    hasTrend: visibleWindowMetrics.deltaAmount !== null,
    diagnostics: {
      requestedScope: scope,
      selectedScope: scope,
      source: selectedHistory.source,
      hasRequestedScopeHistory: selectedHistory.hasRequestedScopeHistory,
      missingRequestedScope: !selectedHistory.hasRequestedScopeHistory,
      pointCountsByScope: scopePointCounts,
      selectedWindowKey,
      effectiveWindowKey,
      latestObservedDate: visibleWindowMetrics.latestPoint?.sourceDate || visibleWindowMetrics.latestPoint?.date || null,
    },
  };
}
