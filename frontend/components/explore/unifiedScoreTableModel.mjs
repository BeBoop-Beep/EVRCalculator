// Pure model for the unified Era/Set benchmark score tables.  Ranks, cohort
// sizes and tiers are ALWAYS the canonical backend values carried on each
// metric; nothing here recomputes rank or tier from visible rows.

export const REFERENCE_SCORE = 5;

export const SCORE_COLUMNS = Object.freeze([
  Object.freeze({ key: "overall", label: "RIP Score", protectedColumn: false }),
  Object.freeze({ key: "financial", label: "Financial", protectedColumn: true }),
  Object.freeze({ key: "collector", label: "Collector Appeal", protectedColumn: true }),
  Object.freeze({ key: "chase", label: "Chase", protectedColumn: true }),
]);

export const PROTECTED_METRIC_KEYS = Object.freeze(SCORE_COLUMNS.filter((column) => column.protectedColumn).map((column) => column.key));
export const DEFAULT_SORT = Object.freeze({ key: "overall", direction: "asc" });

const finite = (value) => (value === null || value === undefined || value === "" ? null : Number.isFinite(Number(value)) ? Number(value) : null);

/** Public rows may only ever expose identity + Overall, whatever the payload says. */
export function publicOnlyRows(rows = []) {
  return (Array.isArray(rows) ? rows : []).map((row) => {
    const next = { ...row };
    for (const key of PROTECTED_METRIC_KEYS) delete next[key];
    return next;
  });
}

/**
 * Public headlines render first.  Once the paid wide scorecard for the SAME
 * publication arrives it supplies the component metrics; if the publications
 * differ the paid cohort is used wholesale so ranks are never mixed.
 */
export function mergeScorecardRows(publicScorecards, paidScorecards = null) {
  const publicRows = publicOnlyRows(publicScorecards?.rows);
  const paidRows = Array.isArray(paidScorecards?.rows) ? paidScorecards.rows : null;
  if (!paidRows) return { rows: publicRows, marketDate: publicScorecards?.marketDate || null, paid: false };
  const samePublication = !publicScorecards?.marketDate || !paidScorecards?.marketDate || publicScorecards.marketDate === paidScorecards.marketDate;
  if (!samePublication) return { rows: paidRows, marketDate: paidScorecards.marketDate || null, paid: true };
  const publicById = new Map(publicRows.map((row) => [String(row.entityId), row]));
  const rows = paidRows.map((row) => {
    const base = publicById.get(String(row.entityId)) || {};
    return { ...base, ...row, overall: row.overall || base.overall };
  });
  return { rows, marketDate: paidScorecards.marketDate || publicScorecards?.marketDate || null, paid: true };
}

export function filterScoreRows(rows = [], { query = "", eraFilter = null } = {}) {
  const needle = String(query || "").trim().toLocaleLowerCase();
  const era = String(eraFilter || "").trim().toLocaleLowerCase();
  return rows
    .filter((row) => !era || String(row?.era?.eraName || "").toLocaleLowerCase() === era)
    .filter((row) => !needle || String(row?.name || "").toLocaleLowerCase().includes(needle));
}

/** Canonical rank for the metric a table is currently ordered by. */
export function displayedRank(row, key) {
  const metric = row?.[key];
  const rank = finite(metric?.rank);
  return rank === null ? null : { rank, cohortSize: finite(metric?.cohortSize) };
}

/** direction "asc" = best-to-worst canonical rank.  Unranked rows always last. */
export function sortScoreRows(rows = [], { key = DEFAULT_SORT.key, direction = DEFAULT_SORT.direction } = {}) {
  const sign = direction === "desc" ? -1 : 1;
  return rows.slice().sort((left, right) => {
    const a = finite(left?.[key]?.rank), b = finite(right?.[key]?.rank);
    if (a !== null && b !== null && a !== b) return sign * (a - b);
    if (a === null && b !== null) return 1;
    if (a !== null && b === null) return -1;
    const byName = String(left?.name || "").localeCompare(String(right?.name || ""));
    return byName || String(left?.entityId || "").localeCompare(String(right?.entityId || ""));
  });
}

export function sortableKeys(entitled) {
  return SCORE_COLUMNS.filter((column) => entitled || !column.protectedColumn).map((column) => column.key);
}

/** First click on a metric = best-to-worst; clicking the active metric reverses. */
export function nextSort(current, key, entitled = false) {
  if (!sortableKeys(entitled).includes(key)) return current;
  if (current?.key === key) return { key, direction: current.direction === "asc" ? "desc" : "asc" };
  return { key, direction: "asc" };
}

/** A sort on a metric the viewer cannot see falls back to the default. */
export function effectiveSort(sort, entitled) {
  return sortableKeys(entitled).includes(sort?.key) ? sort : DEFAULT_SORT;
}

export function ariaSort(sort, key) {
  return sort.key !== key ? "none" : sort.direction === "asc" ? "ascending" : "descending";
}
