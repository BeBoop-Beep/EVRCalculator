// ---------------------------------------------------------------------------
// Market Explorer — the comparable-series model.
//
// Phase 1 could assume the three published parent markets were the whole world.
// Phase 2 adds Sealed product-family submarkets, so a "series" is no longer the
// same thing as a "family key on the overview".
//
// A SERIES ID is a stable, namespaced string:
//
//   raw | topChase | sealedMarket        — parent markets
//   sealed:boosterBox | sealed:etb | …   — Sealed product-family submarkets
//
// The namespace is deliberate: the next phases add `card:sir`, `era:sv` and so
// on, and they slot in as new prefixes without reshaping selection state, the
// chart, the legend, the detail table or the URL contract.
//
// NOTHING HERE COMPUTES A MARKET NUMBER. Every series' basketValue, indexValue,
// trend and window movement is read verbatim from the published snapshot. This
// module resolves identity, color and availability.
// ---------------------------------------------------------------------------

import {
  MARKET_OVERVIEW_WINDOWS,
  MARKET_SERIES_DEFINITIONS,
  getFamilyChange,
  getPricePerformanceChange,
} from "./marketOverviewPresentation.mjs";

/** Namespace prefix for a Sealed product-family submarket series. */
export const SEALED_SEGMENT_PREFIX = "sealed:";

/** The parent Sealed series id, which the backend also publishes as segment `total`. */
export const SEALED_PARENT_SERIES_ID = "sealedMarket";

export const PARENT_SERIES_IDS = MARKET_SERIES_DEFINITIONS.map((entry) => entry.key);

/**
 * Sealed submarket identity.
 *
 * COLORS ARE A FAMILY, NOT A RANDOM SET. Total Sealed keeps its established
 * amber identity; every child is a hue-adjacent amber/orange variant, so the
 * chart reads as "the sealed group plus two card markets" at a glance while
 * still separating the children from each other.
 *
 * Green and red are never used here — those stay reserved for gain/loss.
 *
 * `backendKey` is the segment key the backend publishes. A segment the backend
 * does not publish simply never becomes a series.
 */
export const SEALED_SEGMENT_SERIES = [
  { backendKey: "boosterBox", shortLabel: "Booster Boxes", color: "rgba(249,115,22,0.95)", softColor: "rgba(249,115,22,0.16)" },
  { backendKey: "eliteTrainerBox", shortLabel: "ETBs", color: "rgba(253,186,116,0.95)", softColor: "rgba(253,186,116,0.16)" },
  { backendKey: "pokemonCenterEliteTrainerBox", shortLabel: "Pokémon Center ETBs", color: "rgba(217,119,6,0.95)", softColor: "rgba(217,119,6,0.16)" },
  { backendKey: "boosterBundle", shortLabel: "Booster Bundles", color: "rgba(250,204,21,0.95)", softColor: "rgba(250,204,21,0.16)" },
  { backendKey: "packs", shortLabel: "Packs", color: "rgba(234,88,12,0.95)", softColor: "rgba(234,88,12,0.16)" },
];

export const sealedSeriesId = (backendKey) => `${SEALED_SEGMENT_PREFIX}${backendKey}`;

export const isSealedSegmentSeriesId = (seriesId) =>
  String(seriesId || "").startsWith(SEALED_SEGMENT_PREFIX);

export const sealedBackendKeyFromSeriesId = (seriesId) =>
  isSealedSegmentSeriesId(seriesId) ? String(seriesId).slice(SEALED_SEGMENT_PREFIX.length) : null;

const numeric = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const dateKey = (value) => {
  const text = String(value ?? "").slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : null;
};

function normalizeChange(raw) {
  if (!raw || typeof raw !== "object") return null;
  const percent = numeric(raw.percent);
  const available = raw.available === true && percent !== null;
  return {
    available,
    percent: available ? percent : null,
    startDate: dateKey(raw.startDate),
    endDate: dateKey(raw.endDate),
    targetStartDate: dateKey(raw.targetStartDate),
    coverage: String(raw.coverage || (available ? "full" : "unavailable")),
  };
}

function normalizeChangeMap(source) {
  const result = {};
  for (const [key, value] of Object.entries(source && typeof source === "object" ? source : {})) {
    result[key] = normalizeChange(value);
  }
  return result;
}

function normalizeTrend(raw) {
  return (Array.isArray(raw) ? raw : [])
    .map((point) => (Array.isArray(point)
      ? { date: dateKey(point[0]), value: numeric(point[1]) }
      : { date: dateKey(point?.date), value: numeric(point?.value) }))
    .filter((point) => point.date && point.value !== null)
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

/**
 * Normalize the published `sealedSegments` collection into comparable series.
 *
 * The parent (`total`) is deliberately NOT re-emitted here: it is already the
 * `sealedMarket` family on the overview, and publishing it twice would let a
 * user put the same line on the chart under two names.
 */
export function resolveSealedSegmentSeries(payload) {
  const overview = payload?.marketOverview && typeof payload.marketOverview === "object"
    ? payload.marketOverview
    : payload;
  const published = overview?.sealedSegments && typeof overview.sealedSegments === "object"
    ? overview.sealedSegments
    : null;
  if (!published) return [];
  const segments = published.segments && typeof published.segments === "object" ? published.segments : {};
  const definitions = Array.isArray(published.definitions?.segments) ? published.definitions.segments : [];
  const definitionByKey = new Map(definitions.map((entry) => [String(entry.key), entry]));

  return SEALED_SEGMENT_SERIES.map((identity) => {
    const raw = segments[identity.backendKey];
    if (!raw || typeof raw !== "object") return null;
    const definition = definitionByKey.get(identity.backendKey) || {};
    const base = {
      key: sealedSeriesId(identity.backendKey),
      backendKey: identity.backendKey,
      // The backend's own label is authoritative; the short label is only a
      // compact alternative for chips and legends.
      label: String(raw.label || definition.label || identity.shortLabel),
      shortLabel: identity.shortLabel,
      color: identity.color,
      softColor: identity.softColor,
      group: "sealed",
      parentSeriesId: SEALED_PARENT_SERIES_ID,
      isComposite: raw.isComposite === true,
      productFamilies: Array.isArray(raw.productFamilies) ? raw.productFamilies : [],
      definition: String(raw.definition || definition.definition || ""),
    };
    if (raw.available !== true) {
      return { ...base, available: false, unavailableReason: String(raw.unavailableReason || "unavailable") };
    }
    const indexValue = numeric(raw.indexValue);
    const trend = normalizeTrend(raw.trend);
    if (indexValue === null || trend.length === 0) {
      return { ...base, available: false, unavailableReason: "no published history" };
    }
    return {
      ...base,
      available: true,
      basketValue: numeric(raw.basketValue),
      indexValue,
      historyStartDate: dateKey(raw.historyStartDate),
      changes: normalizeChangeMap(raw.changes),
      familyChanges: normalizeChangeMap(raw.familyChanges),
      basketChanges: normalizeChangeMap(raw.basketChanges),
      trend,
      productCount: numeric(raw.metadata?.eligibleProductCount),
    };
  }).filter(Boolean);
}

/** Reconciliation metadata, so the UI can state the residual honestly. */
export function resolveSealedSegmentReconciliation(payload) {
  const overview = payload?.marketOverview && typeof payload.marketOverview === "object"
    ? payload.marketOverview
    : payload;
  const reconciliation = overview?.sealedSegments?.reconciliation;
  if (!reconciliation || typeof reconciliation !== "object") return null;
  return {
    parentBasketValue: numeric(reconciliation.parentBasketValue),
    publishedSegmentBasketValue: numeric(reconciliation.publishedSegmentBasketValue),
    residualLabel: String(reconciliation.residual?.label || "Other Sealed"),
    residualBasketValue: numeric(reconciliation.residual?.basketValue),
    residualProductCount: numeric(reconciliation.residual?.productCount),
    eligibleProductCount: numeric(reconciliation.eligibleProductCount),
  };
}

/**
 * Every comparable series: the published parent markets, then the published
 * Sealed submarkets. One flat list, one identity vocabulary.
 */
export function buildComparableSeries(overview, sealedSegments = [], cardSegments = []) {
  const parents = (overview?.families || []).map((family) => ({
    ...family,
    label: family.key === "topChase" ? "Per-Set Chase Market" : family.label,
    definition: family.key === "topChase"
      ? "Tracks the combined chase-card baskets from each eligible Set. Explorer Top 10 queries rank the entire filtered universe instead."
      : family.definition,
    group: family.key === SEALED_PARENT_SERIES_ID ? "sealed" : "card",
    isParent: true,
    available: true,
    shortLabel: family.label,
  }));
  return [
    ...parents,
    ...sealedSegments.map((series) => ({ ...series, isParent: false })),
    ...cardSegments.map((series) => ({ ...series, isParent: false })),
  ];
}

/** Look one series' shared-comparison change up, whatever kind it is. */
export function getSeriesComparisonChange(series, windowKey) {
  return getPricePerformanceChange(series, windowKey);
}

/** Look one series' own family-specific change up, whatever kind it is. */
export function getSeriesFamilyChange(series, windowKey) {
  return getFamilyChange(series, windowKey);
}

/**
 * The comparison-chart model for an ARBITRARY set of series.
 *
 * `buildMarketPerformanceSeries` is fixed to `overview.families` — the three
 * parent markets — and cannot see a Sealed submarket. This is the same clipping
 * contract generalized over any series list: the visible span comes from the
 * BACKEND's comparison window for `windowKey`, never a locally derived cutoff,
 * so every line and every reported percentage describe the same interval.
 *
 * A series whose shared-comparison change is unavailable contributes no line
 * rather than a partial one drawn over a span it cannot support.
 */
export function buildExplorerChartModel(overview, series, windowKey) {
  const definition = MARKET_OVERVIEW_WINDOWS.find((entry) => entry.key === windowKey);
  const window = definition ? overview?.comparisonWindows?.[definition.changeKey] : null;
  const active = (series || []).filter((entry) => entry.available !== false);
  const drawable = active.filter(
    (entry) => getPricePerformanceChange(entry, windowKey)?.available === true
  );
  if (!window?.available || drawable.length === 0) {
    return { windowKey, available: false, startDate: null, endDate: null, dates: [], series: [] };
  }
  const startDate = window.displayStartDate;
  const endDate = window.displayEndDate;
  const dates = [];
  for (
    let cursor = new Date(`${startDate}T00:00:00Z`), end = new Date(`${endDate}T00:00:00Z`);
    cursor <= end;
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  ) {
    dates.push(cursor.toISOString().slice(0, 10));
  }
  return {
    windowKey,
    available: true,
    startDate,
    endDate,
    dates,
    series: drawable.map((entry) => {
      const change = getPricePerformanceChange(entry, windowKey);
      const sourceTrend = windowKey === "1D" && entry.oneDayComparisonTrend?.length
        ? entry.oneDayComparisonTrend
        : entry.trend || [];
      const points = sourceTrend.filter((point) => point.date >= startDate && point.date <= endDate);
      const byDate = new Map(points.map((point) => [point.date, point.value]));
      const pointByDate = new Map(points.map((point) => [point.date, point]));
      return {
        key: entry.key,
        label: entry.label,
        color: entry.color,
        softColor: entry.softColor,
        change,
        values: dates.map((date) => (byDate.has(date) ? byDate.get(date) : null)),
        pointMeta: dates.map((date) => pointByDate.get(date) || null),
        points,
      };
    }),
  };
}

// ---------------------------------------------------------------------------
// Card-rarity submarkets (Phase 3).
//
// Namespaced `card:<parentMarket>:<segmentKey>` so the id says which universe
// a rarity index describes. A Special Illustration Rare index over ALL tracked
// cards and one over only the Top Chase cohort are different markets, and the
// id must not let them be confused.
// ---------------------------------------------------------------------------

export const CARD_SEGMENT_PREFIX = "card:";
export const RAW_PARENT_SERIES_ID = "raw";
export const TOP_CHASE_PARENT_SERIES_ID = "topChase";

/**
 * Card submarket identity.
 *
 * COLORS ARE A FAMILY. Raw Cards keeps its established violet identity and
 * every rarity child is a hue-adjacent violet/purple variant, so the chart
 * reads as "the card group" against the amber sealed group at a glance. Green
 * and red stay reserved for gain/loss.
 */
export const CARD_SEGMENT_SERIES = [
  { backendKey: "specialIllustrationRare", shortLabel: "SIR", color: "rgba(139,92,246,0.95)", softColor: "rgba(139,92,246,0.16)" },
  { backendKey: "illustrationRare", shortLabel: "IR", color: "rgba(196,181,253,0.95)", softColor: "rgba(196,181,253,0.16)" },
  { backendKey: "ultraRare", shortLabel: "Ultra Rare", color: "rgba(124,58,237,0.95)", softColor: "rgba(124,58,237,0.16)" },
  { backendKey: "hyperRare", shortLabel: "Hyper Rare", color: "rgba(216,180,254,0.95)", softColor: "rgba(216,180,254,0.16)" },
  { backendKey: "doubleRare", shortLabel: "Double Rare", color: "rgba(168,85,247,0.95)", softColor: "rgba(168,85,247,0.16)" },
];

export const cardSeriesId = (parentMarket, backendKey) =>
  `${CARD_SEGMENT_PREFIX}${parentMarket}:${backendKey}`;

export const isCardSegmentSeriesId = (seriesId) =>
  String(seriesId || "").startsWith(CARD_SEGMENT_PREFIX);

/** `card:raw:sir` -> { parentMarket: "raw", backendKey: "sir" }, else null. */
export function parseCardSeriesId(seriesId) {
  if (!isCardSegmentSeriesId(seriesId)) return null;
  const [parentMarket, backendKey] = String(seriesId)
    .slice(CARD_SEGMENT_PREFIX.length)
    .split(":");
  return parentMarket && backendKey ? { parentMarket, backendKey } : null;
}

function normalizeCardSegment(identity, raw, definition, parentMarket) {
  const base = {
    key: cardSeriesId(parentMarket, identity.backendKey),
    backendKey: identity.backendKey,
    parentMarket,
    parentSeriesId: parentMarket === "raw" ? RAW_PARENT_SERIES_ID : TOP_CHASE_PARENT_SERIES_ID,
    label: String(raw.label || definition.label || identity.shortLabel),
    shortLabel: identity.shortLabel,
    color: identity.color,
    softColor: identity.softColor,
    group: "card",
    definition: String(raw.definition || definition.definition || ""),
    taxonomyVersion: String(raw.taxonomyVersion || ""),
  };
  if (raw.available !== true) {
    return { ...base, available: false, unavailableReason: String(raw.unavailableReason || "unavailable") };
  }
  const indexValue = numeric(raw.indexValue);
  const trend = normalizeTrend(raw.trend);
  if (indexValue === null || trend.length === 0) {
    return { ...base, available: false, unavailableReason: "no published history" };
  }
  return {
    ...base,
    available: true,
    basketValue: numeric(raw.basketValue),
    indexValue,
    historyStartDate: dateKey(raw.historyStartDate),
    changes: normalizeChangeMap(raw.changes),
    familyChanges: normalizeChangeMap(raw.familyChanges),
    basketChanges: normalizeChangeMap(raw.basketChanges),
    trend,
    cardCount: numeric(raw.metadata?.cardCount),
    setCount: numeric(raw.metadata?.setCount),
  };
}

/**
 * Normalize the published `cardSegments` collection into comparable series.
 *
 * Both parent universes are read through the same path, so activating Top Chase
 * rarity segments later needs no new normalization — only a payload that
 * carries them.
 */
export function resolveCardSegmentSeries(payload) {
  const overview = payload?.marketOverview && typeof payload.marketOverview === "object"
    ? payload.marketOverview
    : payload;
  const published = overview?.cardSegments && typeof overview.cardSegments === "object"
    ? overview.cardSegments
    : null;
  if (!published) return [];
  const output = [];
  for (const parentMarket of ["raw", "topChase"]) {
    const collection = published[parentMarket];
    if (!collection || typeof collection !== "object") continue;
    const segments = collection.segments && typeof collection.segments === "object" ? collection.segments : {};
    const definitions = Array.isArray(collection.definitions?.segments) ? collection.definitions.segments : [];
    const definitionByKey = new Map(definitions.map((entry) => [String(entry.key), entry]));
    for (const identity of CARD_SEGMENT_SERIES) {
      const raw = segments[identity.backendKey];
      if (!raw || typeof raw !== "object") continue;
      output.push(normalizeCardSegment(
        identity, raw, definitionByKey.get(identity.backendKey) || {}, parentMarket
      ));
    }
  }
  return output;
}

/** Raw-card reconciliation metadata, so the UI can state the residual. */
export function resolveCardSegmentReconciliation(payload) {
  const overview = payload?.marketOverview && typeof payload.marketOverview === "object"
    ? payload.marketOverview
    : payload;
  const reconciliation = overview?.cardSegments?.raw?.reconciliation;
  if (!reconciliation || typeof reconciliation !== "object") return null;
  return {
    parentBasketValue: numeric(reconciliation.parentBasketValue),
    publishedSegmentBasketValue: numeric(reconciliation.publishedSegmentBasketValue),
    residualLabel: String(reconciliation.residual?.label || "Other Cards"),
    residualBasketValue: numeric(reconciliation.residual?.basketValue),
    residualCardCount: numeric(reconciliation.residual?.cardCount),
  };
}

/** Why Top Chase rarity submarkets are not offered, straight from the payload. */
export function resolveTopChaseSegmentStatus(payload) {
  const overview = payload?.marketOverview && typeof payload.marketOverview === "object"
    ? payload.marketOverview
    : payload;
  const collection = overview?.cardSegments?.topChase;
  if (!collection || typeof collection !== "object") return null;
  return {
    available: collection.available === true,
    reason: String(collection.unavailableReason || ""),
  };
}
