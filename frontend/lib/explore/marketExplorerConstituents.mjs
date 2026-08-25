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
// NOTHING IS COMPUTED HERE. No price, no rank and no total is derived; every
// value is read from whichever authority published it. When an authority has
// published nothing, this says so rather than filling the gap.
// ---------------------------------------------------------------------------

import { QUERY_ASSET_CARDS, QUERY_ASSET_SEALED } from "./marketExplorerQuery.mjs";

export const CONSTITUENTS_AVAILABLE = "available";
/** The series exists and is analysable, but its composition is not published. */
export const CONSTITUENTS_PENDING_PUBLICATION = "pendingPublication";
/** Enumerating this market is deliberately not offered. */
export const CONSTITUENTS_NOT_APPLICABLE = "notApplicable";

export const PENDING_PUBLICATION_MESSAGE =
  "Constituent detail will be available after the next market publication.";

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

/** A series' asset, from whichever of its shapes declares one. */
export function resolveSeriesAsset(series) {
  if (!series) return QUERY_ASSET_CARDS;
  if (series.asset) return series.asset;
  if (series.spec?.asset) return series.spec.asset;
  // Prepared series declare themselves through their id namespace.
  if (String(series.key || "").startsWith("sealed:")) return QUERY_ASSET_SEALED;
  if (series.group === "sealed") return QUERY_ASSET_SEALED;
  return QUERY_ASSET_CARDS;
}

/** Parent markets are the whole universe and are not enumerated. */
export function isEnumerableSeries(series) {
  return Boolean(series) && series.isParent !== true;
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
export function resolveSeriesConstituents(series, { previewLimit = 25 } = {}) {
  const asset = resolveSeriesAsset(series);
  const idField = idFieldFor(asset);
  const base = { asset, idField, columns: CONSTITUENT_COLUMNS[asset], rows: [], totalCount: 0 };

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
