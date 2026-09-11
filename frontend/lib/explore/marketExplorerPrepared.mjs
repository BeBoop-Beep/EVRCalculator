const startFor = (endDate, days) => {
  const value = new Date(`${endDate}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() - days);
  return value.toISOString().slice(0, 10);
};
const change = (value, startDate, endDate) => value == null ? { available: false } : {
  available: true, percent: Number(value), startDate, endDate,
};

export function buildPreparedSeries(rows = [], history = []) {
  const historyByKey = new Map();
  for (const point of history) {
    const key = point.market_key;
    if (!historyByKey.has(key)) historyByKey.set(key, []);
    historyByKey.get(key).push({ date: point.market_date, value: Number(point.index_value), trackedValue: point.tracked_value == null ? null : Number(point.tracked_value) });
  }
  return rows.map((row) => {
    const end = row.comparison_as_of;
    const changes = {
      "7D": change(row.return_7d_pct, startFor(end, 7), end), "30D": change(row.return_30d_pct, startFor(end, 30), end),
      "90D": change(row.return_90d_pct, startFor(end, 90), end), "1Y": change(row.return_1y_pct, startFor(end, 365), end),
      SinceTracking: change(null),
    };
    const color = resolveSeriesIdentityColor(row.market_key, row.market_key);
    return {
      key: row.market_key, label: row.label, shortLabel: row.label, group: row.asset === "sealed" ? "sealed" : "card",
      marketType: row.market_type, setId: row.set_id, eraId: row.era_id, parentEraId: row.parent_era_id,
      available: true, historyAvailable: row.history_available, basketValue: row.comparison_value,
      browseValue: row.current_value, sourceAsOf: row.source_as_of, comparisonAsOf: end,
      indexValue: row.comparison_index_value, historyStartDate: row.history_start_date,
      trend: historyByKey.get(row.market_key) || [], changes, familyChanges: changes,
      analytics: {
        currentDrawdown: row.current_drawdown_pct, maxDrawdown: row.max_drawdown_pct,
        relative7D: row.relative_7d_vs_era_pct, relative30D: row.relative_30d_vs_era_pct,
        relative90D: row.relative_90d_vs_era_pct, relative1Y: row.relative_1y_vs_era_pct,
      },
      sourceStatus: row.source_status, metadata: row.metadata || {},
      color, softColor: softSeriesColor(color),
    };
  });
}

export const QUICK_MARKET_KEYS = Object.freeze([
  "curated:obtainable", "curated:intermediate", "curated:premium",
  "curated:new-releases", "curated:established", "curated:global-top10",
]);

export function groupPreparedDirectory(rows = [], search = "") {
  const term = search.trim().toLowerCase();
  const visible = rows.filter((row) => !term || row.label.toLowerCase().includes(term));
  const eras = visible.filter((row) => row.market_type === "era").sort((a, b) => a.label.localeCompare(b.label));
  const eraById = new Map(rows.filter((row) => row.market_type === "era").map((row) => [row.era_id, row]));
  const sets = new Map();
  for (const row of visible.filter((item) => item.market_type === "set").sort((a, b) => a.label.localeCompare(b.label))) {
    const era = eraById.get(row.parent_era_id);
    const key = era?.market_key || `era:${row.parent_era_id}`;
    if (!sets.has(key)) sets.set(key, { era, rows: [] });
    sets.get(key).rows.push(row);
  }
  const quick = QUICK_MARKET_KEYS.map((key) => visible.find((row) => row.market_key === key)).filter(Boolean);
  return { eras, sets: [...sets.values()].sort((a, b) => (a.era?.label || "").localeCompare(b.era?.label || "")), quick };
}
import { resolveSeriesIdentityColor, softSeriesColor } from "./marketExplorerSeriesColors.mjs";
