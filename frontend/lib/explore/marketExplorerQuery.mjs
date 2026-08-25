// ---------------------------------------------------------------------------
// Market Explorer — card query specification (frontend mirror).
//
// WHAT THIS IS. The client-side half of the backend's normalized query spec
// (backend/domain/pokemon/market_explorer_query.py). A user's filter selections
// become one canonical spec here, and that spec is what the series builder
// turns into a comparison chip. Both halves must normalize identically, or the
// same user selection would carry two different fingerprints and defeat the
// cache it exists to key.
//
// FILTER-FIRST IS A BACKEND GUARANTEE, NOT A CLIENT ONE. Nothing here ranks,
// prices, or decides membership. This module only DESCRIBES a query; the
// engine resolves the universe, applies era -> set -> segment -> price
// eligibility, and only then ranks for chase mode. A chase basket is never
// assembled or re-sorted on the client.
//
// EMPTY MEANS ALL. An empty era/set/segment list means "every eligible member
// of that dimension", never "nothing". A freshly opened filter panel therefore
// describes the whole market.
//
// NO HARDCODED RARITY AUTHORITY. Segment options are whatever the backend
// publishes (section 34). There is deliberately no rarity list in this file:
// a segment the backend does not publish must not be selectable.
// ---------------------------------------------------------------------------

export const MARKET_EXPLORER_QUERY_CONTRACT_VERSION = "pokemon-market-explorer-query-v1";

export const QUERY_ASSET_CARDS = "cards";
export const QUERY_MODE_ALL = "all";
export const QUERY_MODE_CHASE = "chase";

/**
 * The only chase cutoff published today. Additional cutoffs are a product
 * decision, so the control renders this single value rather than a range.
 */
export const DEFAULT_CHASE_TOP_N = 10;

export const MARKET_MODE_OPTIONS = [
  { id: QUERY_MODE_ALL, label: "All Constituents" },
  { id: QUERY_MODE_CHASE, label: "Chase" },
];

function cleanIds(values) {
  if (!Array.isArray(values)) return [];
  const cleaned = new Set();
  for (const value of values) {
    const text = String(value ?? "").trim();
    if (text) cleaned.add(text);
  }
  // Sorting is what collapses two equivalent selections onto one fingerprint.
  return [...cleaned].sort();
}

/** Canonical form of a card query. Mirrors normalize_query_spec exactly. */
export function normalizeQuerySpec({
  mode = QUERY_MODE_ALL,
  eraIds = [],
  setIds = [],
  segmentIds = [],
  topN = null,
} = {}) {
  const resolvedMode = mode === QUERY_MODE_CHASE ? QUERY_MODE_CHASE : QUERY_MODE_ALL;
  return {
    contractVersion: MARKET_EXPLORER_QUERY_CONTRACT_VERSION,
    asset: QUERY_ASSET_CARDS,
    eraIds: cleanIds(eraIds),
    setIds: cleanIds(setIds),
    segmentIds: cleanIds(segmentIds),
    mode: resolvedMode,
    // topN is not part of an "all constituents" market's identity; carrying a
    // stray value would fingerprint two identical markets apart.
    topN: resolvedMode === QUERY_MODE_CHASE
      ? (Number.isFinite(Number(topN)) && Number(topN) > 0 ? Number(topN) : DEFAULT_CHASE_TOP_N)
      : null,
  };
}

// ---------------------------------------------------------------------------
// CANONICAL OPTION ORDER.
//
// The filter controls must render the same list in the same order every time,
// on the server and on the client. The backend already sorts, but its ordering
// keys can tie (two eras sharing a sortOrder, two sets sharing a name), and a
// tie resolved by database iteration order is not an order at all. These
// comparators break every tie on the id, which is unique, so the rendered list
// is a pure function of the payload contents rather than of how the rows
// happened to arrive.
//
// Segment options are deliberately NOT re-sorted: the backend publishes them in
// taxonomy order, which separates the modern market from the legacy one. Sorting
// them alphabetically here would interleave "Rare Holo" with "Rare Ultra" and
// destroy that separation.
// ---------------------------------------------------------------------------
const byId = (left, right) => String(left.id).localeCompare(String(right.id));

/** Eras in publication order: sortOrder, then name, then id. */
export function sortEraOptions(eras) {
  return [...(Array.isArray(eras) ? eras : [])].sort((left, right) => {
    const leftOrder = Number.isFinite(Number(left.sortOrder)) ? Number(left.sortOrder) : Number.MAX_SAFE_INTEGER;
    const rightOrder = Number.isFinite(Number(right.sortOrder)) ? Number(right.sortOrder) : Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) return leftOrder - rightOrder;
    const byLabel = String(left.label || "").localeCompare(String(right.label || ""));
    return byLabel !== 0 ? byLabel : byId(left, right);
  });
}

/** Sets alphabetically, which is how a user scans for one by name. */
export function sortSetOptions(sets) {
  return [...(Array.isArray(sets) ? sets : [])].sort((left, right) => {
    const byLabel = String(left.label || "").localeCompare(String(right.label || ""));
    return byLabel !== 0 ? byLabel : byId(left, right);
  });
}

function keyPart(label, values) {
  return `${label}=${values.length ? values.join("+") : "all"}`;
}

/**
 * Stable human-readable identity, byte-identical to the backend's query_key.
 * This is the cache key and the URL-serialisable form.
 */
export function buildQueryKey(spec) {
  const normalized = normalizeQuerySpec(spec);
  return [
    normalized.asset,
    keyPart("era", normalized.eraIds),
    keyPart("set", normalized.setIds),
    keyPart("segment", normalized.segmentIds),
    `mode=${normalized.mode}`,
    `topN=${normalized.topN ?? "na"}`,
  ].join("|");
}

function nameFor(lookup, id) {
  return (lookup && lookup[id]) || id;
}

/**
 * The chip/legend label, e.g. "Scarlet & Violet · Special Illustration Rare · Top 10".
 *
 * SCOPE PRECEDENCE. An explicit set selection is the most specific statement
 * the user made, so it wins over the era it belongs to; naming both would make
 * the chip too long to scan at the exact moment it is being compared with five
 * others.
 */
export function buildQueryLabel(spec, { eraNames, setNames, segmentNames } = {}) {
  const normalized = normalizeQuerySpec(spec);
  let scope = "Global";
  if (normalized.setIds.length) {
    scope = normalized.setIds.map((id) => nameFor(setNames, id)).join(", ");
  } else if (normalized.eraIds.length) {
    scope = normalized.eraIds.map((id) => nameFor(eraNames, id)).join(", ");
  }
  const segment = normalized.segmentIds.length
    ? normalized.segmentIds.map((id) => nameFor(segmentNames, id)).join(", ")
    : "All rarities";
  const mode = normalized.mode === QUERY_MODE_CHASE ? `Top ${normalized.topN}` : "All";
  return `${scope} · ${segment} · ${mode}`;
}

/**
 * The natural benchmark for a query (section 31).
 *
 * THE RULE: a chase query's parent is THE SAME FILTERED UNIVERSE IN ALL MODE.
 * "SV SIR Top 10" is benchmarked against "SV SIR All", not against the global
 * raw market. That answers the question a chase series actually poses — "is the
 * top of this market outperforming the rest of THIS market?" — whereas a global
 * benchmark conflates two differences at once (chase-vs-broad AND
 * this-scope-vs-everything) and cannot separate them.
 *
 * An "all" query is already its own broadest form and has no narrower parent,
 * so it returns null rather than inventing one.
 */
export function resolveBenchmarkSpec(spec) {
  const normalized = normalizeQuerySpec(spec);
  if (normalized.mode !== QUERY_MODE_CHASE) return null;
  return normalizeQuerySpec({ ...normalized, mode: QUERY_MODE_ALL, topN: null });
}

/** A comparison series carries its identity, never just its display string. */
export function buildQuerySeries(spec, labels) {
  const normalized = normalizeQuerySpec(spec);
  const queryKey = buildQueryKey(normalized);
  return {
    seriesId: `query:${queryKey}`,
    queryKey,
    displayLabel: buildQueryLabel(normalized, labels),
    asset: normalized.asset,
    scopeSummary: {
      eraIds: normalized.eraIds,
      setIds: normalized.setIds,
      isGlobal: !normalized.eraIds.length && !normalized.setIds.length,
    },
    segmentSummary: {
      segmentIds: normalized.segmentIds,
      isAllRarities: !normalized.segmentIds.length,
    },
    mode: normalized.mode,
    topN: normalized.topN,
    spec: normalized,
  };
}

/** De-duplicate by identity, so the same market cannot be charted twice. */
export function addQuerySeries(existing, series) {
  const list = Array.isArray(existing) ? existing : [];
  if (list.some((entry) => entry.queryKey === series.queryKey)) return list;
  return [...list, series];
}

export function removeQuerySeries(existing, queryKey) {
  const list = Array.isArray(existing) ? existing : [];
  return list.filter((entry) => entry.queryKey !== queryKey);
}

/** Stable non-semantic series color derived from the backend fingerprint. */
export function colorForQueryFingerprint(fingerprint) {
  let hash = 2166136261;
  for (const character of String(fingerprint || "query")) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  const hue = ((hash >>> 0) % 260) + 20;
  return `hsl(${hue} 72% 58%)`;
}

function normalizeChangeMap(source) {
  const result = {};
  for (const [key, value] of Object.entries(source && typeof source === "object" ? source : {})) {
    result[key] = value && typeof value === "object" ? value : null;
  }
  return result;
}

/** Adapt prepared backend output to the existing chart/detail series shape. */
export function queryResultToSeries(result) {
  if (!result?.queryFingerprint || !Array.isArray(result?.trend)) return null;
  const color = colorForQueryFingerprint(result.queryFingerprint);
  const changes = normalizeChangeMap(result.familyChanges);
  return {
    key: `query:${result.queryFingerprint}`,
    queryKey: result.queryKey,
    queryFingerprint: result.queryFingerprint,
    label: result.displayLabel,
    shortLabel: result.displayLabel,
    color,
    softColor: color,
    group: "query",
    isParent: false,
    available: true,
    basketValue: result.trackedValue,
    indexValue: result.indexValue,
    historyStartDate: result.historyStartDate,
    changes,
    familyChanges: changes,
    basketChanges: normalizeChangeMap(result.trackedValueChanges),
    trend: result.trend.map(([date, value]) => ({ date, value })),
    spec: result.spec,
    scope: result.scope,
    currentConstituents: Array.isArray(result.currentConstituents) ? result.currentConstituents : [],
    membershipByDate: Array.isArray(result.membershipByDate) ? result.membershipByDate : [],
    reconciliation: result.reconciliation || {},
    metadata: result.metadata || {},
    diagnostics: result.diagnostics || {},
  };
}
