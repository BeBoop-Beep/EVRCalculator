const DAY = 86_400_000;

export const FINANCIAL_RIP_WINDOWS = Object.freeze([
  { key: "30D", label: "30D", days: 29, ariaLabel: "Last 30 days" },
  { key: "3M", label: "3M", days: 89, ariaLabel: "Last 3 months" },
  { key: "6M", label: "6M", days: 179, ariaLabel: "Last 6 months" },
  { key: "1Y", label: "1Y", days: 365, ariaLabel: "Last year" },
  { key: "ALL", label: "ALL", days: null, ariaLabel: "All available history" },
]);

export const MAX_FINANCIAL_RIP_SET_SELECTION = 5;
export const FINANCIAL_RIP_COLORS = ["#38bdf8", "#c084fc", "#fbbf24", "#fb7185", "#818cf8"];

const dateOnly = (value) => value ? String(value).slice(0, 10) : null;
const finite = (value) => value === null || value === undefined || value === "" ? null : Number.isFinite(Number(value)) ? Number(value) : null;
const entityId = (target) => String(target?.target_id || target?.setId || target?.set_id || target?.id || "");

export function subtractUtcDays(endDate, days) {
  return new Date(new Date(`${dateOnly(endDate)}T00:00:00Z`).getTime() - days * DAY).toISOString().slice(0, 10);
}

export function financialRipWindowRange(windowKey, availableThrough, availableFrom = null) {
  const endDate = dateOnly(availableThrough);
  if (!endDate) return { startDate: null, endDate: null };
  const option = FINANCIAL_RIP_WINDOWS.find((item) => item.key === windowKey) || FINANCIAL_RIP_WINDOWS[0];
  const startDate = option.days === null
    ? dateOnly(availableFrom) || subtractUtcDays(endDate, 3652)
    : subtractUtcDays(endDate, option.days);
  return { startDate, endDate };
}

export function setFinancialRipCandidates(targets = []) {
  return targets.map((target) => ({
    entity_type: "set",
    entity_id: entityId(target),
    name: String(target?.name || target?.setName || "Unknown Set"),
    canonicalKey: target?.canonical_key || target?.setCanonicalKey || null,
  })).filter((item) => item.entity_id);
}

export function eraFinancialRipCandidates(openingSets = [], fallbackEras = []) {
  const values = [];
  for (const row of openingSets) {
    const id = String(row?.eraId || row?.era_id || "");
    if (id) values.push({ entity_type: "era", entity_id: id, name: String(row?.eraName || row?.era_name || "Unknown Era") });
  }
  for (const row of fallbackEras) {
    const id = String(row?.eraId || row?.era_id || row?.id || "");
    if (id) values.push({ entity_type: "era", entity_id: id, name: String(row?.eraName || row?.era_name || row?.name || "Unknown Era") });
  }
  return [...new Map(values.map((item) => [item.entity_id, item])).values()]
    .sort((left, right) => left.name.localeCompare(right.name));
}

export function stableEntityColor(entityIdValue) {
  let hash = 0;
  for (const character of String(entityIdValue)) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return FINANCIAL_RIP_COLORS[Math.abs(hash) % FINANCIAL_RIP_COLORS.length];
}

export function entitySeriesKey(entityIdValue) {
  return `entity_${String(entityIdValue).replace(/[^a-zA-Z0-9]/g, "_")}`;
}

export function shouldFetchFinancialRipHistory({ entitled, authStatus, selectedCount, startDate, endDate }) {
  return Boolean(
    entitled
    && (authStatus === "resolved" || authStatus === "degraded")
    && selectedCount > 0
    && startDate
    && endDate,
  );
}

export function toggleFinancialRipSelection(current = [], id, max = Infinity) {
  if (current.includes(id)) return current.filter((item) => item !== id);
  return current.length >= max ? current : [...current, id];
}

export function buildFinancialRipChartModel(rows = [], selectedEntities = [], range = {}) {
  const selected = new Map(selectedEntities.map((item) => [String(item.entity_id), item]));
  const points = new Map();
  if (range.startDate && range.endDate) {
    for (let cursor = new Date(`${range.startDate}T00:00:00Z`), end = new Date(`${range.endDate}T00:00:00Z`); cursor <= end; cursor = new Date(cursor.getTime() + DAY)) {
      const date = cursor.toISOString().slice(0, 10);
      points.set(date, { date, overallFinancialRip: null, entities: {} });
    }
  }
  for (const row of rows) {
    if (row?.metric_key !== "financial") continue;
    const id = String(row?.entity_id || "");
    if (!selected.has(id)) continue;
    const date = dateOnly(row?.market_date);
    const point = points.get(date);
    if (!point) continue;
    const score = finite(row?.absolute_financial_rip_score);
    const reference = finite(row?.overall_financial_rip_reference);
    if (reference !== null) point.overallFinancialRip = reference;
    if (score === null) continue;
    const key = entitySeriesKey(id);
    point[key] = score;
    point.entities[id] = {
      financialRip: score,
      overallFinancialRip: reference,
      deltaVsOverall: finite(row?.absolute_delta_vs_overall),
      rank: finite(row?.rank),
      cohortSize: finite(row?.cohort_size),
      status: row?.status || null,
    };
  }
  const series = selectedEntities.map((item) => ({ ...item, key: entitySeriesKey(item.entity_id), color: stableEntityColor(item.entity_id) }));
  return { points: [...points.values()], series };
}

export function financialRipYAxisDomain(points = [], series = []) {
  const values = [];
  for (const point of points) {
    const reference = finite(point?.overallFinancialRip);
    if (reference !== null) values.push(reference);
    for (const item of series) {
      const value = finite(point?.[item.key]);
      if (value !== null) values.push(value);
    }
  }
  if (!values.length) return [0, 10];
  const min = Math.min(...values), max = Math.max(...values);
  const padding = Math.max((max - min) * 0.12, 1);
  return [Math.floor((min - padding) * 10) / 10, Math.ceil((max + padding) * 10) / 10];
}

export function formatFinancialRip(value) {
  const number = finite(value);
  return number === null ? "Unavailable" : number.toFixed(2);
}

export function formatFinancialRipDelta(value) {
  const number = finite(value);
  if (number === null) return "Unavailable";
  if (number === 0) return "0.00 vs Overall";
  return `${number > 0 ? "+" : "−"}${Math.abs(number).toFixed(2)} vs Overall`;
}
