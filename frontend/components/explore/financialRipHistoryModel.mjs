const DAY = 86_400_000;

export const FINANCIAL_RIP_WINDOWS = Object.freeze([
  { key: "30D", label: "30D", days: 29, ariaLabel: "Last 30 days" },
  { key: "3M", label: "3M", days: 89, ariaLabel: "Last 3 months" },
  { key: "6M", label: "6M", days: 179, ariaLabel: "Last 6 months" },
  { key: "1Y", label: "1Y", days: 365, ariaLabel: "Last year" },
  { key: "ALL", label: "ALL", days: null, ariaLabel: "All available history" },
]);

export const FINANCIAL_RIP_COLORS = ["#38bdf8", "#c084fc", "#fbbf24", "#fb7185", "#818cf8", "#2dd4bf", "#f97316", "#a3e635", "#e879f9", "#60a5fa", "#f43f5e", "#14b8a6", "#d946ef", "#eab308", "#6366f1", "#22c55e"];

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

export function setFinancialRipCandidates(targets = [], openingSets = []) {
  const openingById = new Map(openingSets.map((row) => [String(row?.setId || row?.set_id || ""), row]).filter(([id]) => id));
  const openingByKey = new Map(openingSets.map((row) => [String(row?.setCanonicalKey || row?.canonical_key || ""), row]).filter(([key]) => key));
  return targets.map((target) => {
    const id = entityId(target);
    const canonicalKey = target?.canonical_key || target?.setCanonicalKey || null;
    const opening = openingById.get(id) || (canonicalKey ? openingByKey.get(String(canonicalKey)) : null);
    return {
      entity_type: "set",
      entity_id: id,
      name: String(target?.name || target?.setName || opening?.setName || "Unknown Set"),
      canonicalKey,
      eraId: String(target?.eraId || target?.era_id || opening?.eraId || opening?.era_id || ""),
      eraName: String(target?.eraName || target?.era_name || opening?.eraName || opening?.era_name || ""),
    };
  }).filter((item) => item.entity_id);
}

export function setIdsForEra(candidates = [], eraId) {
  const key = String(eraId || "");
  return candidates.filter((item) => item.eraId === key).map((item) => item.entity_id);
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

// With no user-selected series the chart is Overall-only, but a range change still has
// to ask the authorised endpoint for the active range.  An invisible transport anchor
// (last loaded entity, else the first cohort entity) carries that request; it is never
// plotted or listed.
export function financialRipRequestEntities(selected = [], lastSelected = [], fallback = []) {
  if (selected.length) return selected;
  if (lastSelected.length) return [lastSelected[0]];
  return fallback.length ? [fallback[0]] : [];
}

export const FINANCIAL_RIP_DEFAULT_SET_COUNT = 3;
export const FINANCIAL_RIP_FADED_OPACITY = 0.14;

export function buildFinancialRipCandidates({ financialCohort = null, targets = [], openingSets = [], eras = [] } = {}) {
  const cohortEras = Array.isArray(financialCohort?.eras) ? financialCohort.eras : [];
  const setCandidates = cohortEras.length
    ? cohortEras.flatMap((era) => (era.sets || []).map((set) => ({ entity_type: "set", entity_id: String(set.setId), name: set.setName, canonicalKey: set.canonicalKey, eraId: String(era.eraId), eraName: era.eraName })))
    : setFinancialRipCandidates(targets, openingSets);
  const eraCandidates = cohortEras.length
    ? cohortEras.map((era) => ({ entity_type: "era", entity_id: String(era.eraId), name: era.eraName }))
    : eraFinancialRipCandidates(openingSets, eras);
  return { setCandidates, eraCandidates };
}

/** The request the chart makes on first paint: first 3 Sets, 30D, ending at the publication date. */
export function defaultFinancialHistoryRequest({ financialCohort = null, targets = [], openingSets = [], eras = [], marketDate = null } = {}) {
  const { setCandidates } = buildFinancialRipCandidates({ financialCohort, targets, openingSets, eras });
  const { startDate, endDate } = financialRipWindowRange("30D", marketDate, null);
  if (!setCandidates.length || !startDate || !endDate) return null;
  const toEntity = (item) => ({ entity_type: "set", entity_id: item.entity_id });
  return {
    entities: setCandidates.slice(0, FINANCIAL_RIP_DEFAULT_SET_COUNT).map(toEntity),
    cohortEntities: setCandidates.map(toEntity),
    startDate,
    endDate,
  };
}

// ---- focus (display only: never changes the selection) -----------------------------

/** Hover focus is temporary and wins over persistent focus; both must be plotted series. */
export function resolveActiveFocus({ persistentId = null, hoverId = null, seriesIds = [] } = {}) {
  const plotted = new Set(seriesIds.map(String));
  if (hoverId != null && plotted.has(String(hoverId))) return String(hoverId);
  if (persistentId != null && plotted.has(String(persistentId))) return String(persistentId);
  return null;
}

export function toggleFocus(current, id) {
  return current != null && String(current) === String(id) ? null : String(id);
}

export function seriesEmphasis(entityIdValue, activeFocusId) {
  const faded = activeFocusId != null && String(entityIdValue) !== String(activeFocusId);
  return { faded, strokeOpacity: faded ? FINANCIAL_RIP_FADED_OPACITY : 1, strokeWidth: 1.75, showDots: !faded };
}

/** Draw the focused series last so it sits above the faded ones. */
export function orderSeriesForDrawing(series = [], activeFocusId = null) {
  if (activeFocusId == null) return series;
  return [...series.filter((item) => String(item.entity_id) !== String(activeFocusId)), ...series.filter((item) => String(item.entity_id) === String(activeFocusId))];
}

export function toggleFinancialRipSelection(current = [], id, max = Infinity) {
  if (current.includes(id)) return current.filter((item) => item !== id);
  return current.length >= max ? current : [...current, id];
}

export function buildFinancialRipChartModel(rows = [], selectedEntities = [], range = {}) {
  const selected = new Map(selectedEntities.map((item) => [String(item.entity_id), item]));
  const points = new Map();
  for (const row of rows) {
    if (row?.metric_key && row.metric_key !== "financial") continue;
    const id = String(row?.entityId || row?.entity_id || "");
    const entitySelected = selected.has(id);
    if (!entitySelected && selected.size) continue;
    const date = dateOnly(row?.marketDate || row?.market_date);
    if (!date || (range.startDate && date < range.startDate) || (range.endDate && date > range.endDate)) continue;
    const point = points.get(date) || { date, timestamp: new Date(`${date}T00:00:00Z`).getTime(), overallFinancialRip: null, entities: {} };
    points.set(date, point);
    const score = finite(row?.absoluteFinancialRipScore ?? row?.absolute_financial_rip_score);
    const reference = finite(row?.overallFinancialRipReference ?? row?.overall_financial_rip_reference);
    if (reference !== null) point.overallFinancialRip = reference;
    if (!entitySelected) continue;
    if (score === null) continue;
    const key = entitySeriesKey(id);
    point[key] = score;
    point.entities[id] = {
      financialRip: score,
      overallFinancialRip: reference,
      deltaVsOverall: finite(row?.absoluteDeltaVsOverall ?? row?.absolute_delta_vs_overall),
      rank: finite(row?.rank),
      cohortSize: finite(row?.cohortSize ?? row?.cohort_size),
      status: row?.status || null,
    };
  }
  const series = selectedEntities.map((item) => ({ ...item, key: entitySeriesKey(item.entity_id), color: stableEntityColor(item.entity_id) }));
  return { points: [...points.values()].sort((a, b) => a.timestamp - b.timestamp), series };
}

export function financialRipTooltipRows(point = {}, series = [], focusId = null) {
  const overall = finite(point.overallFinancialRip);
  const visible = focusId == null ? series : series.filter((item) => String(item.entity_id) === String(focusId));
  return visible.flatMap((item) => {
    const detail = point.entities?.[String(item.entity_id)];
    const score = finite(detail?.financialRip);
    if (score === null) return [];
    return [{ ...item, score, deltaVsOverall: overall === null ? null : score - overall }];
  }).sort((left, right) => right.score - left.score
    || String(left.name || "").localeCompare(String(right.name || ""), "en", { sensitivity: "base" })
    || String(left.entity_id).localeCompare(String(right.entity_id)));
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
  if (number === 0) return "— 0.00 vs Overall";
  return `${number > 0 ? "↑ +" : "↓ −"}${Math.abs(number).toFixed(2)} vs Overall`;
}

export function formatFinancialRipTooltipDelta(value) {
  const number = finite(value);
  if (number === null) return "Unavailable";
  if (number === 0) return "±0.00";
  return `${number > 0 ? "+" : "−"}${Math.abs(number).toFixed(2)} ${number > 0 ? "↑" : "↓"}`;
}
