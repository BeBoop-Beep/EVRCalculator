// ---------------------------------------------------------------------------
// Market Explorer — what is inside a selected market.
//
// ONE RESOLVER, TWO ASSETS, THREE SOURCES. A series on the chart can be:
//
//   * a DYNAMIC query, which carries its own `currentConstituents` computed by
//     the engine that built it;
//   * a PREPARED quick segment, whose composition rides in the published
//     snapshot under the prepared constituent-summary contract;
//   * a PARENT market, which deliberately does not enumerate (the Raw Card
//     Market is the whole tracked card universe, and a table of it is not a
//     research tool).
//
// This module turns any of them into ONE view model so the panel never has to
// ask which kind of series it is holding.
//
// ROW SHAPES ARE NOT FORCED TOGETHER. A card row carries rarity, a sealed row
// carries product family. Inventing a shared field name for two different facts
// would make the table lie about one of them, so the asset selects the columns
// and the rows keep their own keys.
//
// MOVEMENT IS READ, NEVER RECONSTRUCTED. Each row may carry a compact
// `changes` map — 1D/7D/30D/3M — published by the same canonical authority that
// published its price. The browser never subtracts one price from another, and
// never falls back to the market's aggregate return: an aggregate printed on
// every row would look like data and mean nothing.
//
// ONE MOVEMENT COLUMN, NOT FOUR. Four simultaneous change columns make the
// table too wide to read at any width, so the window is a local control and the
// column is whichever one the user picked.
//
// NOTHING IS COMPUTED HERE. No price, no rank, no total and no percentage is
// derived; every value is read from whichever authority published it. When an
// authority has published nothing, this says so rather than filling the gap.
// ---------------------------------------------------------------------------

import { QUERY_ASSET_CARDS, QUERY_ASSET_SEALED } from "./marketExplorerQuery.mjs";

/** The Sealed Market parent's series id. Not `sealed:`-prefixed, unlike its children. */
const SEALED_PARENT_SERIES_ID = "sealedMarket";

export const CONSTITUENTS_AVAILABLE = "available";
/** The series exists and is analysable, but its composition is not published. */
export const CONSTITUENTS_PENDING_PUBLICATION = "pendingPublication";
/** Enumerating this market is deliberately not offered. */
export const CONSTITUENTS_NOT_APPLICABLE = "notApplicable";

export const PENDING_PUBLICATION_MESSAGE =
  "Constituent detail will be available after the next market publication.";

/**
 * The movement windows the table offers, and the default.
 *
 * Mirrors the backend's CONSTITUENT_MOVEMENT_WINDOWS exactly. 7D is the default
 * because 1D on a daily-observed market is mostly noise and 30D is too slow to
 * show what changed this week.
 */
export const CONSTITUENT_MOVEMENT_WINDOWS = Object.freeze(["1D", "7D", "30D", "3M"]);
export const DEFAULT_CONSTITUENT_MOVEMENT_WINDOW = "7D";

export function normalizeConstituentMovementWindow(requested) {
  return CONSTITUENT_MOVEMENT_WINDOWS.includes(requested)
    ? requested
    : DEFAULT_CONSTITUENT_MOVEMENT_WINDOW;
}

/**
 * One row's movement percentage over one window, or null.
 *
 * NULL MEANS "DO NOT PRINT A NUMBER". The table renders an em dash for it —
 * never 0.00%, which would claim the price held steady when the truth is that
 * this constituent has no comparable observation at the window's start. A real
 * zero is a Number and prints as 0.00%; the two must never collapse.
 *
 * The published shape is a bare number per window, because the boundary DATES
 * are a property of the market and are published once beside the roster rather
 * than repeated on every row.
 */
export function getConstituentChange(row, window) {
  const raw = row?.changes?.[window];
  // Guarded EXPLICITLY, because `Number(null)` is 0 and `Number("")` is 0:
  // coercing first would turn "no comparable observation" into a confident
  // 0.00%, which is the single most misleading thing this column could print.
  if (typeof raw !== "number") return null;
  return Number.isFinite(raw) ? raw : null;
}

/** Does ANY row in this basket carry movement for this window? */
export function hasAnyConstituentMovement(rows, window) {
  return (rows || []).some((row) => getConstituentChange(row, window) !== null);
}

/**
 * The published boundary dates for one window of one market, or null.
 *
 * Read from the MARKET rather than from a row, which is where they now live.
 */
export function getMovementWindowMeta(series, window) {
  const summary = series?.currentConstituents;
  const windows = Array.isArray(summary) ? series?.movementWindows : summary?.movementWindows;
  const meta = windows?.[window];
  return meta && typeof meta === "object" ? meta : null;
}

/** Column contract per asset. The panel renders from this, never from a guess. */
export const CONSTITUENT_COLUMNS = {
  [QUERY_ASSET_CARDS]: [
    { key: "rank", label: "Rank", align: "left", numeric: true },
    { key: "cardName", label: "Card", align: "left", primary: true },
    { key: "setName", label: "Set", align: "left" },
    { key: "rarity", label: "Rarity", align: "left" },
    { key: "marketPrice", label: "Price", align: "right", price: true },
  ],
  [QUERY_ASSET_SEALED]: [
    { key: "rank", label: "Rank", align: "left", numeric: true },
    { key: "productName", label: "Product", align: "left", primary: true },
    { key: "setName", label: "Set", align: "left" },
    { key: "productFamilyLabel", label: "Family", align: "left" },
    { key: "marketPrice", label: "Price", align: "right", price: true },
  ],
};

const idFieldFor = (asset) =>
  (asset === QUERY_ASSET_SEALED ? "sealedProductId" : "canonicalCardId");

/**
 * The asset's columns plus the ONE movement column for the selected window.
 *
 * Appended rather than baked into CONSTITUENT_COLUMNS so the label always
 * matches the control the user just used — a "7D Change" header above 30D
 * numbers is worse than no movement column at all.
 */
export function buildConstituentColumns(asset, movementWindow) {
  const base = CONSTITUENT_COLUMNS[asset] || CONSTITUENT_COLUMNS[QUERY_ASSET_CARDS];
  const window = normalizeConstituentMovementWindow(movementWindow);
  return [
    ...base,
    { key: "changes", label: `${window} Change`, align: "right", change: true, window },
  ];
}

/**
 * A series' asset, from whichever of its shapes declares one.
 *
 * THE PUBLISHED ROSTER IS CONSULTED FIRST, because it is the only source that
 * states the asset as a FACT rather than by convention: the prepared summary
 * carries the `idField` its rows are actually keyed by. Everything below it is
 * inference from a naming convention, and inference lost here once already —
 * the Sealed Market PARENT is keyed `sealedMarket`, which does not match the
 * `sealed:` child prefix, so its roster of products was being resolved as
 * cards and would have rendered under Card / Rarity column headings.
 */
export function resolveSeriesAsset(series) {
  if (!series) return QUERY_ASSET_CARDS;
  const declaredIdField = series.currentConstituents && !Array.isArray(series.currentConstituents)
    ? series.currentConstituents.idField
    : null;
  if (declaredIdField === "sealedProductId") return QUERY_ASSET_SEALED;
  if (declaredIdField === "canonicalCardId") return QUERY_ASSET_CARDS;
  if (series.asset) return series.asset;
  if (series.spec?.asset) return series.spec.asset;
  // Prepared series otherwise declare themselves through their id namespace.
  if (String(series.key || "").startsWith("sealed:")) return QUERY_ASSET_SEALED;
  if (series.key === SEALED_PARENT_SERIES_ID) return QUERY_ASSET_SEALED;
  if (series.group === "sealed") return QUERY_ASSET_SEALED;
  return QUERY_ASSET_CARDS;
}

/**
 * Can this market's composition be listed?
 *
 * Parent markets are normally the whole tracked universe and are summarised
 * rather than enumerated — Raw Card Market is 4,372 cards and a table of them
 * helps nobody. But "parent" is not the same as "unlistable": Total Sealed is a
 * parent whose 139 products ARE a roster worth reading, and it is the only
 * surface that shows the ten `otherSealed` residual products, which belong to
 * no child market. So enumerability follows the published composition, not the
 * isParent flag: a parent that publishes `currentConstituents` can be inspected,
 * and one that does not still reports the parent-market reason.
 */
export function isEnumerableSeries(series) {
  if (!series) return false;
  if (series.isParent !== true) return true;
  return Boolean(series.currentConstituents);
}

const numericOrNull = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/**
 * Stable price-descending order with an id tie-break.
 *
 * Applied to prepared rows because a published preview is already ordered but a
 * consumer must not depend on that; applied to All-mode dynamic rows because
 * price order is what makes a long list scannable. Top-N rows arrive in rank
 * order and keep it.
 */
export function sortConstituentRows(rows, idField) {
  return [...rows].sort((left, right) => {
    const byPrice = (numericOrNull(right.marketPrice) ?? -Infinity)
      - (numericOrNull(left.marketPrice) ?? -Infinity);
    if (byPrice !== 0) return byPrice;
    return String(left[idField] ?? "").localeCompare(String(right[idField] ?? ""));
  });
}

/**
 * The composition view model for one series.
 *
 * `bounded` means the rows are a PREVIEW of a larger universe. It is reported
 * from the publisher's own `isComplete` flag or from the dynamic engine's
 * `eligibleUniverseCount`, never inferred by comparing lengths — a preview that
 * happened to equal its limit would otherwise read as complete.
 */
export function resolveSeriesConstituents(
  series,
  { previewLimit = 25, movementWindow = DEFAULT_CONSTITUENT_MOVEMENT_WINDOW } = {}
) {
  const asset = resolveSeriesAsset(series);
  const idField = idFieldFor(asset);
  const window = normalizeConstituentMovementWindow(movementWindow);
  const base = {
    asset,
    idField,
    movementWindow: window,
    columns: buildConstituentColumns(asset, window),
    rows: [],
    totalCount: 0,
  };

  if (!series) return { ...base, availability: CONSTITUENTS_NOT_APPLICABLE };
  if (!isEnumerableSeries(series)) {
    return {
      ...base,
      availability: CONSTITUENTS_NOT_APPLICABLE,
      reason: `${series.label || "This market"} is a parent market covering the whole tracked universe.`,
    };
  }

  // 1. A dynamic query carries its own roster.
  const dynamicRows = Array.isArray(series.currentConstituents) ? series.currentConstituents : null;
  if (dynamicRows && dynamicRows.length) {
    const isTopMode = series.spec?.mode === "chase";
    const eligible = numericOrNull(series.reconciliation?.eligibleUniverseCount);
    const totalCount = isTopMode
      ? (numericOrNull(series.reconciliation?.actualConstituentCount) ?? dynamicRows.length)
      : (eligible ?? dynamicRows.length);
    const ordered = isTopMode ? dynamicRows : sortConstituentRows(dynamicRows, idField);
    const rows = isTopMode ? ordered : ordered.slice(0, previewLimit);
    return {
      ...base,
      availability: CONSTITUENTS_AVAILABLE,
      rows,
      totalCount,
      asOf: series.asOf || dynamicRows[0]?.asOf || null,
      // A Top N basket is complete by construction; an All-mode market is
      // previewed because it can hold thousands.
      bounded: !isTopMode && totalCount > rows.length,
      source: "query",
      // Stated so the panel can explain an all-dash column as "this
      // publication predates movement" rather than leaving it a mystery.
      hasMovement: hasAnyConstituentMovement(rows, window),
      movementWindowMeta: getMovementWindowMeta(series, window),
      belowRequestedTopN: series.reconciliation?.belowRequestedTopN === true,
      requestedTopN: numericOrNull(series.reconciliation?.requestedTopN),
    };
  }

  // 2. A prepared quick segment carries the published summary.
  const prepared = series.currentConstituents && !Array.isArray(series.currentConstituents)
    ? series.currentConstituents
    : null;
  const preparedRows = Array.isArray(prepared?.topConstituents) ? prepared.topConstituents : null;
  if (preparedRows && preparedRows.length) {
    const totalCount = numericOrNull(prepared.totalCount) ?? preparedRows.length;
    return {
      ...base,
      availability: CONSTITUENTS_AVAILABLE,
      rows: sortConstituentRows(preparedRows, prepared.idField || idField).slice(0, previewLimit),
      totalCount,
      asOf: prepared.asOf || null,
      // The publisher states this; it is never inferred from the row count.
      bounded: prepared.isComplete === false || totalCount > Math.min(preparedRows.length, previewLimit),
      source: "prepared",
      hasMovement: hasAnyConstituentMovement(preparedRows, window),
      movementWindowMeta: getMovementWindowMeta(series, window),
    };
  }

  // 3. Published analytics, unpublished composition. Say so.
  return {
    ...base,
    availability: CONSTITUENTS_PENDING_PUBLICATION,
    reason: PENDING_PUBLICATION_MESSAGE,
  };
}

/**
 * The series the detail panel should target when the selection changes.
 *
 * Keeps the user's choice while it is still on the chart, so adding a market
 * never yanks the panel away from what they were reading. Falls back to the
 * first enumerable series, so the panel is useful before anything is clicked.
 */
export function resolveActiveDetailSeriesId(selectedSeries, requestedId) {
  const enumerable = (selectedSeries || []).filter(
    (series) => series && series.available !== false && isEnumerableSeries(series)
  );
  if (requestedId && enumerable.some((series) => series.key === requestedId)) return requestedId;
  return enumerable[0]?.key || null;
}
