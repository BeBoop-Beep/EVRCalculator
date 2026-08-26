// ---------------------------------------------------------------------------
// Market Explorer — workspace state model.
//
// Market Explorer is the deep-dive counterpart to /Market. It answers "WHICH
// part of the market is driving performance", by putting several canonical
// market series on one comparison chart at once.
//
// SCOPE. The Explore Segments rail is organised as one always-visible group
// plus four collapsed ones:
//   Asset Market          - the published ASSET CLASSES (Raw, Sealed) plus the
//                           declared-unavailable Graded placeholder.
//   Card Rarities         - the published card-rarity submarkets, grouped by
//                           the parent market each one measures.
//   Sealed Product Families - the published Sealed submarkets.
//   Era & Sets            - canonical era -> set navigation, which sets a SCOPE
//                           rather than charting a line, because no backend
//                           publishes an era index.
//   Benchmarks            - canonical reference markets (Per-Set Chase today).
// Every option in every group is whatever the backend published; nothing here
// invents a segment, a rarity, an era or a set.
//
// SERIES IDS. Selection is expressed in the namespaced ids from
// marketExplorerSeries.mjs (`raw`, `sealed:boosterBox`, `card:raw:ultraRare`).
// Parent selection lives in `assetUniverse` because the three parents are the
// page top-level cards; submarket selection lives in `sealedFamilyIds` and
// `segmentIds`. The chart, the legend and the detail table consume the union.
//
// NOTHING HERE COMPUTES A MARKET NUMBER. Every basket value, index value and
// percentage on the page is read verbatim from the published snapshot. This
// module only decides which published series are selected, over which
// published window.
// ---------------------------------------------------------------------------

import {
  FAMILY_SINCE_TRACKING_LABEL,
  MARKET_OVERVIEW_WINDOWS,
  MARKET_SERIES_DEFINITIONS,
  buildMarketWindowOptions,
  resolveDefaultMarketWindow,
} from "./marketOverviewPresentation.mjs";
import {
  RAW_PARENT_SERIES_ID,
  TOP_CHASE_PARENT_SERIES_ID,
  isCardSegmentSeriesId,
  isSealedSegmentSeriesId,
} from "./marketExplorerSeries.mjs";

/** The parent markets. Order is the display order. */
export const MARKET_EXPLORER_ASSET_KEYS = MARKET_SERIES_DEFINITIONS.map((entry) => entry.key);

// ---------------------------------------------------------------------------
// ASSET MARKET vs BENCHMARK.
//
// An asset market is an ASSET CLASS: the thing itself, held in a particular
// form. Raw cards, sealed product, graded slabs. "Per-Set Chase" is none of
// those — it is a MODE (rank a filtered universe, keep the top of it) applied
// to the card asset class, so it sits under Benchmarks with the other
// canonical reference markets rather than pretending to be a fourth asset.
//
// Chase deliberately does NOT get a top-level card either: the Explorer's
// general expression of "chase" is Build a Market's Top N mode over whatever
// universe the user filtered, and the published per-set basket is one specific
// benchmark rather than the concept.
// ---------------------------------------------------------------------------

/** Published parent markets that are genuinely asset classes. */
export const MARKET_EXPLORER_ASSET_MARKET_KEYS = ["raw", "sealedMarket"];

/** Published parent markets that are reference benchmarks, not asset classes. */
export const MARKET_EXPLORER_BENCHMARK_KEYS = ["topChase"];

/** Explorer-facing label + definition for the relocated per-set chase basket. */
export const PER_SET_CHASE_LABEL = "Per-Set Chase Market";
export const PER_SET_CHASE_DEFINITION =
  "Tracks the combined chase-card baskets from each eligible Set. This differs from custom Top 10 queries, which rank the entire filtered universe after applying your filters.";

/**
 * Graded is declared, visible and explicitly unavailable.
 *
 * A third asset class the product intends to publish must occupy its real
 * architectural position rather than appearing later as a surprise. It carries
 * NO basket value, NO index and NO trend: a fabricated $0 line would be a
 * claim, and the whole point of showing it disabled is that no such claim
 * exists yet.
 */
export const GRADED_MARKET_KEY = "gradedMarket";
export const GRADED_MARKET_PLACEHOLDER = {
  key: GRADED_MARKET_KEY,
  label: "Graded Market",
  color: "rgba(148,163,184,0.95)",
  softColor: "rgba(148,163,184,0.16)",
  family: null,
  available: false,
  selected: false,
  unavailableReason:
    "No canonical graded analytics are published yet. Graded market history requires per-grade population and price authority that the tracked universe does not yet carry, so no index is computed and none is shown.",
};

/** The Asset Market group: published asset classes, plus the graded placeholder. */
export function buildAssetMarketModel(overview, selectedKeys) {
  const published = buildAssetUniverseModel(overview, selectedKeys)
    .filter((entry) => MARKET_EXPLORER_ASSET_MARKET_KEYS.includes(entry.key));
  return [...published, { ...GRADED_MARKET_PLACEHOLDER }];
}

/** The Benchmarks group: canonical reference markets. Extensible by design. */
export function buildBenchmarkModel(overview, selectedKeys) {
  return buildAssetUniverseModel(overview, selectedKeys)
    .filter((entry) => MARKET_EXPLORER_BENCHMARK_KEYS.includes(entry.key))
    .map((entry) => (entry.key === "topChase"
      ? { ...entry, label: PER_SET_CHASE_LABEL, definition: PER_SET_CHASE_DEFINITION }
      : entry));
}

/** Page-wide default window, per the Market Explorer product spec. */
export const MARKET_EXPLORER_DEFAULT_TIMEFRAME = "7D";

/**
 * The detail strip's fixed column set. Deliberately a SUBSET of the chart
 * windows: the strip is a scan row, not a second timeframe control.
 *
 * `dimension` is the semantic lock. "comparison" columns read the shared
 * cross-market domain (`changes`); the final column reads the market's OWN
 * tracking-start movement (`familyChanges`) and is the only one allowed to be
 * labelled "Since Tracking". The shared long window has a different name —
 * "Since Comparable Start" — and lives on the timeframe control as "All".
 */
export const MARKET_EXPLORER_DETAIL_WINDOWS = [
  { key: "1D", label: "1D", dimension: "comparison" },
  { key: "7D", label: "7D", dimension: "comparison" },
  { key: "30D", label: "30D", dimension: "comparison" },
  { key: "3M", label: "3M", dimension: "comparison" },
  { key: "All", label: FAMILY_SINCE_TRACKING_LABEL, dimension: "family" },
];

/**
 * Filter axes the workspace is built to hold.
 *
 * `dynamic: true` means the axis has no compile-time option list at all — its
 * options are resolved from the published payload at runtime, so a segment the
 * backend does not publish can never appear as selectable.
 */
export const MARKET_EXPLORER_FILTER_AXES = [
  {
    id: "assetMarket",
    stateKey: "assetUniverse",
    label: "Asset Market",
    available: true,
    dynamic: false,
    options: MARKET_SERIES_DEFINITIONS
      .filter(({ key }) => MARKET_EXPLORER_ASSET_MARKET_KEYS.includes(key))
      .map(({ key, label, color }) => ({ id: key, label, color })),
  },
  {
    // Canonical reference markets. Extensible: a future benchmark is a new
    // entry here, never a fourth asset class.
    id: "benchmark",
    stateKey: "assetUniverse",
    label: "Benchmarks",
    available: true,
    dynamic: false,
    options: MARKET_SERIES_DEFINITIONS
      .filter(({ key }) => MARKET_EXPLORER_BENCHMARK_KEYS.includes(key))
      .map(({ key, color }) => ({ id: key, label: PER_SET_CHASE_LABEL, color })),
  },
  {
    id: "sealedFamily",
    stateKey: "sealedFamilyIds",
    label: "Sealed Product Family",
    available: true,
    dynamic: true,
    placeholderLabel: "All Sealed Products",
    options: [],
  },
  {
    // LIVE as a NAVIGATION axis. Its options — eras and their sets — come from
    // the canonical filter-options service, never from a list written here.
    // It does not by itself produce a series: no backend publishes an era
    // index, so selecting an era sets a SCOPE the advanced builder can resolve
    // into a real queried market. See MarketExplorerEraSets.
    id: "era",
    stateKey: "eraIds",
    label: "Era & Sets",
    available: true,
    dynamic: true,
    placeholderLabel: "All Eras",
    options: [],
  },
  {
    // LIVE as of Phase 3, and dynamic like the sealed axis: options come from
    // the published `cardSegments` collection, grouped by which parent market
    // each rarity index describes.
    id: "cardSegment",
    stateKey: "segmentIds",
    label: "Card Segment",
    available: true,
    dynamic: true,
    grouped: true,
    placeholderLabel: "All Card Segments",
    options: [],
  },
];

/** Display grouping for the Card Segment axis, so a user is never left to
 *  guess which universe a rarity index measures. */
export const CARD_SEGMENT_GROUPS = [
  { parentMarket: "raw", parentSeriesId: RAW_PARENT_SERIES_ID, label: "Raw Card Segments" },
  { parentMarket: "topChase", parentSeriesId: TOP_CHASE_PARENT_SERIES_ID, label: "Chase Segments" },
];

/** The parent market keys the snapshot actually published, in canonical order. */
export function resolveAvailableAssetKeys(overview) {
  const published = new Set((overview?.families || []).map((family) => family.key));
  return MARKET_EXPLORER_ASSET_KEYS.filter((key) => published.has(key));
}

/** The Sealed submarket series ids the snapshot published as available. */
export function resolveAvailableSealedFamilyIds(sealedSegments = []) {
  return sealedSegments.filter((series) => series.available === true).map((series) => series.key);
}

/** The card-rarity submarket series ids the snapshot published as available. */
export function resolveAvailableCardSegmentIds(cardSegments = []) {
  return cardSegments.filter((series) => series.available === true).map((series) => series.key);
}

/** Card submarket descriptors grouped by parent market, for the filter list. */
export function buildCardSegmentModel(cardSegments = [], selectedIds) {
  const selected = selectedIds instanceof Set ? selectedIds : new Set(selectedIds || []);
  return CARD_SEGMENT_GROUPS.map((group) => ({
    ...group,
    entries: cardSegments
      .filter((series) => series.parentMarket === group.parentMarket)
      .map((series) => ({
        ...series,
        selected: series.available === true && selected.has(series.key),
      })),
  })).filter((group) => group.entries.length > 0);
}

/**
 * A descriptor per canonical parent market — including any the snapshot did NOT
 * publish, which render as an explicit "unavailable" card rather than silently
 * disappearing. An older snapshot without `sealedMarket` still shows Raw and
 * Top Chase, and the page does not crash.
 */
export function buildAssetUniverseModel(overview, selectedKeys) {
  const byKey = new Map((overview?.families || []).map((family) => [family.key, family]));
  const selected = selectedKeys instanceof Set ? selectedKeys : new Set(selectedKeys || []);
  return MARKET_SERIES_DEFINITIONS.map((definition) => {
    const family = byKey.get(definition.key) || null;
    return {
      key: definition.key,
      label: definition.label,
      color: definition.color,
      softColor: definition.softColor,
      family,
      available: Boolean(family),
      selected: Boolean(family) && selected.has(definition.key),
    };
  });
}

/** Sealed submarket descriptors with selection resolved, for the filter list. */
export function buildSealedFamilyModel(sealedSegments = [], selectedIds) {
  const selected = selectedIds instanceof Set ? selectedIds : new Set(selectedIds || []);
  return sealedSegments.map((series) => ({
    ...series,
    selected: series.available === true && selected.has(series.key),
  }));
}

// --- query state ----------------------------------------------------------

const asList = (value) => {
  if (Array.isArray(value)) return value;
  if (value === null || value === undefined) return [];
  return [value];
};

const splitValues = (values) => values
  .flatMap((value) => String(value).split(","))
  .map((value) => value.trim())
  .filter(Boolean);

/**
 * THE single place Market Explorer reads the URL, and the single place it
 * serializes back.
 *
 * Supported:
 *   ?market=raw            ?markets=raw,sealedMarket
 *   ?segments=sealed:boosterBox,sealed:etb
 *
 * Unknown values are dropped rather than creating a phantom series. Era and
 * Card Segment deliberately have NO query representation: publishing a link
 * that names a filter no backend can honour would be a broken promise.
 */
export function parseMarketExplorerQuery(
  searchParams,
  { availableSealedFamilyIds = null, availableCardSegmentIds = null } = {},
) {
  const read = (name) => {
    if (!searchParams) return [];
    if (typeof searchParams.getAll === "function") return searchParams.getAll(name);
    return asList(searchParams[name]);
  };
  const requestedMarkets = splitValues([...read("market"), ...read("markets")]);
  const knownMarkets = requestedMarkets.filter((value) => MARKET_EXPLORER_ASSET_KEYS.includes(value));

  const allSegments = splitValues(read("segments"));
  const requestedSegments = allSegments.filter(isSealedSegmentSeriesId);
  const knownSegments = availableSealedFamilyIds === null
    ? requestedSegments
    : requestedSegments.filter((value) => availableSealedFamilyIds.includes(value));

  const requestedCards = allSegments.filter(isCardSegmentSeriesId);
  const knownCards = availableCardSegmentIds === null
    ? requestedCards
    : requestedCards.filter((value) => availableCardSegmentIds.includes(value));

  return {
    requestedCardSegmentIds: (availableCardSegmentIds || requestedCards)
      .filter((id) => knownCards.includes(id)),
    hasCardSegmentRequest: knownCards.length > 0,
    // Deduped, and re-ordered into canonical order so ?markets=sealedMarket,raw
    // and ?markets=raw,sealedMarket produce the same workspace.
    requestedAssetKeys: MARKET_EXPLORER_ASSET_KEYS.filter((key) => knownMarkets.includes(key)),
    hasAssetRequest: knownMarkets.length > 0,
    requestedSealedFamilyIds: (availableSealedFamilyIds || requestedSegments)
      .filter((id) => knownSegments.includes(id)),
    hasSealedFamilyRequest: knownSegments.length > 0,
  };
}

/** Serialize a selection back into a shareable query string (no leading "?"). */
export function serializeMarketExplorerQuery({
  assetUniverse = [], sealedFamilyIds = [], segmentIds = [],
} = {}) {
  const parts = [];
  if (assetUniverse.length) parts.push(`markets=${assetUniverse.join(",")}`);
  // ONE `segments` parameter carries every submarket axis; the namespaced ids
  // already say which axis each belongs to, so a second parameter would only
  // create two ways to express the same selection.
  const segments = [...sealedFamilyIds, ...segmentIds];
  if (segments.length) parts.push(`segments=${segments.join(",")}`);
  return parts.join("&");
}

/**
 * The initial workspace state.
 *
 * Default is ALL published parent markets and NO submarkets: the page opens on
 * the cross-market comparison, and submarkets are what the researcher adds. A
 * `?market=` / `?segments=` request narrows or extends that, but only to series
 * the snapshot actually published; a request for nothing available falls back
 * rather than producing an empty chart.
 */
export function resolveInitialExplorerState(
  overview, searchParams, sealedSegments = [], cardSegments = [],
) {
  const availableKeys = resolveAvailableAssetKeys(overview);
  const availableSealedFamilyIds = resolveAvailableSealedFamilyIds(sealedSegments);
  const availableCardSegmentIds = resolveAvailableCardSegmentIds(cardSegments);
  const parsed = parseMarketExplorerQuery(searchParams, {
    availableSealedFamilyIds, availableCardSegmentIds,
  });
  const requestedAvailable = parsed.requestedAssetKeys.filter((key) => availableKeys.includes(key));
  const sealedFamilyIds = parsed.hasSealedFamilyRequest ? parsed.requestedSealedFamilyIds : [];
  const segmentIds = parsed.hasCardSegmentRequest ? parsed.requestedCardSegmentIds : [];

  let assetUniverse;
  if (parsed.hasAssetRequest && requestedAvailable.length > 0) {
    assetUniverse = requestedAvailable;
  } else if (sealedFamilyIds.length > 0 || segmentIds.length > 0) {
    // A link that asks only for submarkets charts EXACTLY those submarkets.
    // It used to also resolve each one's parent onto the chart; that is the
    // same automatic-parent behaviour the toggles dropped, and a shared link
    // must reproduce what the sharer was looking at, not add to it.
    assetUniverse = [];
  } else {
    // The opening view is the ASSET CLASSES — the cross-asset comparison a
    // researcher starts from. Per-Set Chase is a benchmark now and lives in a
    // collapsed group, so selecting it by default would put a line on the
    // chart whose control the user cannot see.
    assetUniverse = availableKeys.filter((key) => MARKET_EXPLORER_ASSET_MARKET_KEYS.includes(key));
  }

  return {
    assetUniverse,
    sealedFamilyIds,
    segmentIds,
    // Declared now so future phases extend the state rather than reshaping it.
    eraIds: [],
    timeframe: resolveDefaultMarketWindow(overview, MARKET_EXPLORER_DEFAULT_TIMEFRAME),
  };
}

/** The union the chart, legend and detail table consume, in display order. */
export function resolveSelectedSeriesIds({
  assetUniverse = [], sealedFamilyIds = [], segmentIds = [],
} = {}) {
  return [...assetUniverse, ...sealedFamilyIds, ...segmentIds];
}

/**
 * Toggle one parent market.
 *
 * AT LEAST ONE SERIES MUST REMAIN ON THE CHART. Deselecting the last parent is
 * allowed only while a submarket is still selected — the constraint is about
 * the chart never being empty, not about parents specifically.
 */
export function toggleAssetUniverseKey(
  assetUniverse, key, availableKeys, { sealedFamilyIds = [], segmentIds = [] } = {},
) {
  const allowed = Array.isArray(availableKeys) ? availableKeys : MARKET_EXPLORER_ASSET_KEYS;
  if (!allowed.includes(key)) return assetUniverse;
  const current = new Set(assetUniverse || []);
  const otherSeriesCount = (sealedFamilyIds || []).length + (segmentIds || []).length;
  if (current.has(key)) {
    if (current.size <= 1 && otherSeriesCount === 0) return assetUniverse;
    current.delete(key);
  } else {
    current.add(key);
  }
  return MARKET_EXPLORER_ASSET_KEYS.filter((entry) => current.has(entry));
}

/**
 * Toggle one Sealed submarket.
 *
 * NO AUTOMATIC PARENT. A quick-segment click means exactly what was clicked.
 * This used to also switch Total Sealed on, reasoning that a child index needs
 * its parent to be read against — but in use that produced a line the user
 * never asked for, in a near-identical colour, that reappeared every time they
 * removed it. Comparison is the USER'S statement to make: clicking ETBs charts
 * ETBs, and ETBs-vs-Sealed is two deliberate clicks.
 *
 * The advanced builder is different and still supplies a same-filter benchmark
 * (see resolveBenchmarkSpec) — there the user has explicitly composed a narrow
 * custom universe, and its own All-mode counterpart is the only thing that can
 * interpret it. The distinction is deliberate: fast lane is literal, advanced
 * lane is analytic.
 *
 * The return shape keeps `assetUniverse` so the reducer stays one atomic step;
 * it is now always returned unchanged.
 */
export function toggleSealedFamilyId(
  sealedFamilyIds,
  seriesId,
  availableSealedFamilyIds,
  { assetUniverse = [], availableAssetKeys = [], segmentIds = [] } = {},
) {
  const allowed = Array.isArray(availableSealedFamilyIds) ? availableSealedFamilyIds : [];
  if (!allowed.includes(seriesId)) {
    return { sealedFamilyIds, assetUniverse };
  }
  const current = new Set(sealedFamilyIds || []);
  const parents = new Set(assetUniverse || []);
  if (current.has(seriesId)) {
    if (current.size <= 1 && parents.size === 0 && (segmentIds || []).length === 0) {
      return { sealedFamilyIds, assetUniverse };
    }
    current.delete(seriesId);
  } else {
    current.add(seriesId);
  }
  return {
    sealedFamilyIds: allowed.filter((id) => current.has(id)),
    assetUniverse: MARKET_EXPLORER_ASSET_KEYS.filter((key) => parents.has(key)),
  };
}

/**
 * Reconcile a selection against a (re-published) snapshot: drop series that
 * vanished, and never end up with nothing selected.
 */
export function reconcileAssetUniverse(assetUniverse, availableKeys, { hasOtherSeries = false } = {}) {
  const allowed = Array.isArray(availableKeys) ? availableKeys : [];
  const kept = (assetUniverse || []).filter((key) => allowed.includes(key));
  // An EMPTY parent selection is now legitimate — a user charting SIR alone
  // asked for exactly one line. Only fall back to the asset classes when there
  // is nothing else on the chart at all, so reconciliation can never leave the
  // workspace blank.
  if (kept.length > 0 || hasOtherSeries) return kept;
  return allowed.filter((key) => MARKET_EXPLORER_ASSET_MARKET_KEYS.includes(key));
}

export function reconcileSealedFamilyIds(sealedFamilyIds, availableSealedFamilyIds) {
  const allowed = Array.isArray(availableSealedFamilyIds) ? availableSealedFamilyIds : [];
  return (sealedFamilyIds || []).filter((id) => allowed.includes(id));
}

export function reconcileCardSegmentIds(segmentIds, availableCardSegmentIds) {
  const allowed = Array.isArray(availableCardSegmentIds) ? availableCardSegmentIds : [];
  return (segmentIds || []).filter((id) => allowed.includes(id));
}

/**
 * Toggle one card-rarity submarket.
 *
 * Same rule as Sealed: NO automatic parent. Clicking SIR charts SIR. Reading
 * it against Raw Card Market is a second, deliberate click.
 */
export function toggleCardSegmentId(
  segmentIds,
  seriesId,
  availableCardSegmentIds,
  { assetUniverse = [], availableAssetKeys = [], sealedFamilyIds = [] } = {},
) {
  const allowed = Array.isArray(availableCardSegmentIds) ? availableCardSegmentIds : [];
  if (!allowed.includes(seriesId)) {
    return { segmentIds, assetUniverse };
  }
  const current = new Set(segmentIds || []);
  const parents = new Set(assetUniverse || []);
  if (current.has(seriesId)) {
    if (current.size <= 1 && parents.size === 0 && (sealedFamilyIds || []).length === 0) {
      return { segmentIds, assetUniverse };
    }
    current.delete(seriesId);
  } else {
    current.add(seriesId);
  }
  return {
    segmentIds: allowed.filter((id) => current.has(id)),
    assetUniverse: MARKET_EXPLORER_ASSET_KEYS.filter((key) => parents.has(key)),
  };
}

// ---------------------------------------------------------------------------
// ONE ATOMIC SELECTION REDUCER.
//
// WHY A REDUCER AND NOT THREE SETTERS. Toggling a submarket moves TWO pieces of
// state at once: the submarket itself, and the parent benchmark it drags onto
// the chart with it. Expressing that as `setSegmentIds` called from inside the
// `setAssetUniverse` updater looks equivalent and is not: React may invoke an
// updater more than once (StrictMode double-invocation, and replaying the
// update queue from a base state on a later render). The nested setter is then
// QUEUED TWICE, the second application toggles the segment straight back off,
// and every quick-segment click is a silent no-op.
//
// A reducer moves the whole selection in one pure step, so replaying it any
// number of times from the same base state yields the same result.
// ---------------------------------------------------------------------------

export const EXPLORER_SELECTION_ACTIONS = {
  toggleMarket: "toggleMarket",
  toggleSealedFamily: "toggleSealedFamily",
  toggleCardSegment: "toggleCardSegment",
  reconcile: "reconcile",
};

const sameList = (left, right) =>
  left.length === right.length && left.every((value, index) => value === right[index]);

/** Preserve identity when nothing moved, so downstream memos do not churn. */
function settle(previous, next) {
  const assetUniverse = sameList(previous.assetUniverse, next.assetUniverse)
    ? previous.assetUniverse : next.assetUniverse;
  const sealedFamilyIds = sameList(previous.sealedFamilyIds, next.sealedFamilyIds)
    ? previous.sealedFamilyIds : next.sealedFamilyIds;
  const segmentIds = sameList(previous.segmentIds, next.segmentIds)
    ? previous.segmentIds : next.segmentIds;
  return (assetUniverse === previous.assetUniverse
    && sealedFamilyIds === previous.sealedFamilyIds
    && segmentIds === previous.segmentIds)
    ? previous
    : { ...previous, assetUniverse, sealedFamilyIds, segmentIds };
}

/**
 * The whole Explorer selection, moved atomically.
 *
 * `state`   { assetUniverse, sealedFamilyIds, segmentIds }
 * `action`  { type, seriesId?, available? }
 * `available` carries the currently published ids:
 *            { assetKeys, sealedFamilyIds, cardSegmentIds }
 */
export function reduceExplorerSelection(state, action) {
  const available = action?.available || {};
  const assetKeys = Array.isArray(available.assetKeys) ? available.assetKeys : [];
  const sealedIds = Array.isArray(available.sealedFamilyIds) ? available.sealedFamilyIds : [];
  const cardIds = Array.isArray(available.cardSegmentIds) ? available.cardSegmentIds : [];

  switch (action?.type) {
    case EXPLORER_SELECTION_ACTIONS.toggleMarket: {
      return settle(state, {
        ...state,
        assetUniverse: toggleAssetUniverseKey(state.assetUniverse, action.seriesId, assetKeys, {
          sealedFamilyIds: state.sealedFamilyIds,
          segmentIds: state.segmentIds,
        }),
      });
    }
    case EXPLORER_SELECTION_ACTIONS.toggleSealedFamily: {
      const result = toggleSealedFamilyId(state.sealedFamilyIds, action.seriesId, sealedIds, {
        assetUniverse: state.assetUniverse,
        availableAssetKeys: assetKeys,
        segmentIds: state.segmentIds,
      });
      return settle(state, { ...state, ...result });
    }
    case EXPLORER_SELECTION_ACTIONS.toggleCardSegment: {
      const result = toggleCardSegmentId(state.segmentIds, action.seriesId, cardIds, {
        assetUniverse: state.assetUniverse,
        availableAssetKeys: assetKeys,
        sealedFamilyIds: state.sealedFamilyIds,
      });
      return settle(state, { ...state, ...result });
    }
    case EXPLORER_SELECTION_ACTIONS.reconcile: {
      // A re-published snapshot can add or drop a market. Selection follows it
      // rather than pointing at a series that no longer exists.
      return settle(state, {
        ...state,
        assetUniverse: reconcileAssetUniverse(state.assetUniverse, assetKeys, {
          hasOtherSeries: reconcileSealedFamilyIds(state.sealedFamilyIds, sealedIds).length > 0
            || reconcileCardSegmentIds(state.segmentIds, cardIds).length > 0,
        }),
        sealedFamilyIds: reconcileSealedFamilyIds(state.sealedFamilyIds, sealedIds),
        segmentIds: reconcileCardSegmentIds(state.segmentIds, cardIds),
      });
    }
    default:
      return state;
  }
}

/** Timeframe options, availability decided by the backend upstream. */
export function buildExplorerTimeframeOptions(overview) {
  return buildMarketWindowOptions(overview);
}

/** Resolve a requested timeframe against what the snapshot supports. */
export function resolveExplorerTimeframe(overview, requested) {
  const options = buildExplorerTimeframeOptions(overview);
  if (options.find((entry) => entry.key === requested && entry.available)) return requested;
  return resolveDefaultMarketWindow(overview, MARKET_EXPLORER_DEFAULT_TIMEFRAME);
}

export { MARKET_OVERVIEW_WINDOWS as MARKET_EXPLORER_TIMEFRAMES };
