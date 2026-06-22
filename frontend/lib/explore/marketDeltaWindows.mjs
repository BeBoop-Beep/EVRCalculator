export const DELTA_WINDOW_DEFINITIONS = [
  { key: "1D", label: "1D", days: 1 },
  { key: "7D", label: "7D", days: 7 },
  { key: "30D", label: "30D", days: 30 },
  { key: "3M", label: "3M", days: 90 },
  { key: "6M", label: "6M", days: 180 },
  { key: "1Y", label: "1Y", days: 365 },
  { key: "lifetime", label: "Lifetime", days: null },
];

export const STANDARD_DELTA_WINDOW_KEYS = DELTA_WINDOW_DEFINITIONS.map((definition) => definition.key);

const DELTA_WINDOWS_BY_KEY = new Map(
  DELTA_WINDOW_DEFINITIONS.map((definition) => [definition.key.toLowerCase(), definition])
);

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeWindowKey(value) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  const upper = text.toUpperCase();
  if (upper === "LIFETIME") {
    return "lifetime";
  }
  return DELTA_WINDOWS_BY_KEY.has(upper.toLowerCase()) ? upper : null;
}

function getWindowDefinition(value) {
  const key = normalizeWindowKey(value);
  return key ? DELTA_WINDOWS_BY_KEY.get(key.toLowerCase()) || null : null;
}

export function getStandardDeltaWindowDefinitions(supportedKeys = STANDARD_DELTA_WINDOW_KEYS) {
  const supportedKeySet = normalizeSupportedKeys(supportedKeys);
  return DELTA_WINDOW_DEFINITIONS.filter((definition) => supportedKeySet.has(definition.key));
}

function normalizeSupportedKeys(supportedKeys) {
  const keys = Array.isArray(supportedKeys) && supportedKeys.length > 0
    ? supportedKeys
    : STANDARD_DELTA_WINDOW_KEYS;
  const normalized = keys.map(normalizeWindowKey).filter(Boolean);
  return new Set(normalized);
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

function candidateFieldNames(prefix, key) {
  const lower = key.toLowerCase();
  const compact = lower.replace(/[^a-z0-9]/g, "");
  return [
    `${prefix}_${lower}`,
    `${prefix}${compact}`,
    `${prefix}${key}`,
    key,
    lower,
  ];
}

function firstNumberFromFields(source, fields) {
  for (const field of fields) {
    const value = toNumber(source?.[field]);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

export function getPreferredDeltaWindowKey(entries, preferredKey = "7D") {
  const available = Array.isArray(entries) ? entries.filter(Boolean) : [];
  if (available.length === 0) {
    return null;
  }

  const preferred = normalizeWindowKey(preferredKey);
  if (preferred && available.some((entry) => entry.key === preferred)) {
    return preferred;
  }

  const fallbackOrder = ["7D", "30D", "1D", "3M", "6M", "1Y", "lifetime"];
  return fallbackOrder.find((key) => available.some((entry) => entry.key === key)) || available[0].key;
}

export function getDeltaWindowLabel(key) {
  return getWindowDefinition(key)?.label || String(key || "").trim();
}

export function getDeltaTrendDirection(value) {
  const parsed = toNumber(value);
  if (parsed === null || Math.abs(parsed) < 0.000001) {
    return "neutral";
  }
  return parsed > 0 ? "up" : "down";
}

export function extractDeltaWindows(source = {}) {
  const root = source && typeof source === "object" ? source : {};
  const nestedDeltas = root.deltas && typeof root.deltas === "object" ? root.deltas : {};

  return DELTA_WINDOW_DEFINITIONS.map((definition) => {
    const amount = firstNumberFromFields(root, candidateFieldNames("delta", definition.key));
    const percent =
      firstNumberFromFields(root, candidateFieldNames("delta_pct", definition.key)) ??
      firstNumberFromFields(root, candidateFieldNames("delta_percent", definition.key)) ??
      firstNumberFromFields(nestedDeltas, [definition.key, definition.key.toLowerCase(), definition.label]);

    if (amount === null && percent === null) {
      return null;
    }

    return {
      key: definition.key,
      label: definition.label,
      amount,
      percent,
      source: "fields",
    };
  }).filter(Boolean);
}

export function computeDeltaWindowsFromHistory(
  points,
  { dateKey = "date", valueKey = "value", supportedKeys = STANDARD_DELTA_WINDOW_KEYS } = {}
) {
  const supportedKeySet = normalizeSupportedKeys(supportedKeys);
  const rows = (Array.isArray(points) ? points : [])
    .map((point) => ({
      date: String(point?.[dateKey] || "").slice(0, 10),
      value: toNumber(point?.[valueKey]),
      isCarriedForward: Boolean(point?.isCarriedForward ?? point?.is_carried_forward),
      point,
    }))
    .filter((point) => /^\d{4}-\d{2}-\d{2}$/.test(point.date) && point.value !== null)
    .sort((a, b) => a.date.localeCompare(b.date));

  if (rows.length < 2) {
    return [];
  }

  const latest = rows[rows.length - 1];
  return getStandardDeltaWindowDefinitions([...supportedKeySet]).map((definition) => {
    let baseline = null;
    let targetDate = null;
    let isSinceFirstAvailable = false;
    if (definition.days === null) {
      baseline = rows[0];
      isSinceFirstAvailable = true;
    } else {
      const spanOffset = definition.days === 1 ? 1 : definition.days - 1;
      targetDate = addDaysToDateKey(latest.date, -spanOffset);
      if (!targetDate) {
        baseline = rows[0];
        isSinceFirstAvailable = true;
      } else if (rows[0].date > targetDate) {
        baseline = rows[0];
        isSinceFirstAvailable = true;
      } else {
        baseline = [...rows].reverse().find((point) => point.date <= targetDate) || rows[0];
      }
    }

    if (!baseline || baseline.date === latest.date || baseline.value === 0) {
      return null;
    }

    const amount = latest.value - baseline.value;
    return {
      key: definition.key,
      label: definition.label,
      amount,
      percent: (amount / baseline.value) * 100,
      startDate: baseline.date,
      endDate: latest.date,
      targetStartDate: targetDate,
      isSinceFirstAvailable,
      isCarriedForward: latest.isCarriedForward,
      source: "history",
    };
  }).filter(Boolean);
}

export function getSelectedDeltaWindowFromHistory(
  points,
  {
    selectedKey = null,
    preferredKey = "7D",
    dateKey = "date",
    valueKey = "value",
    supportedKeys = STANDARD_DELTA_WINDOW_KEYS,
  } = {}
) {
  const windows = computeDeltaWindowsFromHistory(points, { dateKey, valueKey, supportedKeys });
  const controlWindows = getStandardDeltaWindowDefinitions(supportedKeys);
  const normalizedSelectedKey = normalizeWindowKey(selectedKey);
  const preferredControlKey = getPreferredDeltaWindowKey(controlWindows, preferredKey);
  const effectiveKey =
    normalizedSelectedKey && controlWindows.some((entry) => entry.key === normalizedSelectedKey)
      ? normalizedSelectedKey
      : preferredControlKey;

  return {
    windows: controlWindows,
    effectiveKey,
    selectedWindow: windows.find((entry) => entry.key === effectiveKey) || null,
  };
}

export function getVisibleHistoryWindowMetrics(
  points,
  selectedWindow,
  { dateKey = "date", valueKey = "value", amountKey = "deltaFromPrevious", percentKey = "deltaPercentFromPrevious" } = {}
) {
  const visiblePoints = filterHistoryPointsForDeltaWindow(points, selectedWindow, { dateKey });
  let firstValuedPoint = null;

  const pointsWithChanges = visiblePoints.map((point) => {
    const value = toNumber(point?.[valueKey]);
    if (value !== null && !firstValuedPoint) {
      firstValuedPoint = { value, point };
    }

    const baselineValue = firstValuedPoint?.value ?? null;
    const isBaselinePoint = value !== null && point === firstValuedPoint?.point;
    const amount = value !== null && baselineValue !== null && !isBaselinePoint ? value - baselineValue : null;
    const percent = amount !== null && baselineValue !== 0 ? (amount / baselineValue) * 100 : null;
    const nextPoint = {
      ...point,
      [amountKey]: amount,
      [percentKey]: percent,
    };

    return nextPoint;
  });

  const valuedPoints = pointsWithChanges.filter((point) => toNumber(point?.[valueKey]) !== null);
  const firstPoint = valuedPoints[0] || null;
  const latestPoint = valuedPoints[valuedPoints.length - 1] || null;
  const firstValue = toNumber(firstPoint?.[valueKey]);
  const currentValue = toNumber(latestPoint?.[valueKey]);
  const hasWindowDelta = firstPoint && latestPoint && firstPoint !== latestPoint && firstValue !== null && currentValue !== null;
  const deltaAmount = hasWindowDelta ? currentValue - firstValue : null;

  return {
    points: pointsWithChanges,
    valuedPoints,
    firstPoint,
    latestPoint,
    currentValue,
    deltaAmount,
    deltaPercent: deltaAmount !== null && firstValue !== 0 ? (deltaAmount / firstValue) * 100 : null,
  };
}

export function filterHistoryPointsForDeltaWindow(points, window, { dateKey = "date" } = {}) {
  const rows = Array.isArray(points) ? points : [];
  const startDate = window?.startDate || null;
  if (!startDate) {
    return rows;
  }
  return rows.filter((point) => {
    const date = String(point?.[dateKey] || "").slice(0, 10);
    return !date || date >= startDate;
  });
}
