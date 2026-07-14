import { getHistoryDateKey } from "./historyDateFormatting.mjs";

// ---------------------------------------------------------------------------
// Development-only diagnostics for each set-page load: one compact object
// summarizing the canonical marketAsOfDate, every market surface's end date,
// the canonical Cards/Market Movers totals, and banner↔Cards parity — plus
// targeted warnings when they disagree. Never logs complete card payloads or
// price histories.
// ---------------------------------------------------------------------------

function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function getHistoryPointsEndDate(points, { dateKey = "date" } = {}) {
  let latest = null;
  (Array.isArray(points) ? points : []).forEach((point) => {
    const date = getHistoryDateKey(point?.[dateKey]);
    if (date && (!latest || date > latest)) {
      latest = date;
    }
  });
  return latest;
}

function idsEqual(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
    return false;
  }
  return left.every((value, index) => String(value) === String(right[index]));
}

/**
 * Build the per-load diagnostics object and its warnings. Pure — safe to unit
 * test; the caller decides whether/where to log (see
 * reportSetPageMarketDiagnostics).
 */
export function buildSetPageMarketDiagnostics({
  setId = null,
  generationId = null,
  marketAsOfDate = null,
  titleCardEndDate = null,
  setValueEndDate = null,
  openingProfitEndDate = null,
  topChaseEndDate = null,
  cardsSnapshotEndDate = null,
  totalCards = null,
  cardsWith7dMovement = null,
  nonzero7dMovers = null,
  marketMoversFilteredTotal = null,
  bannerCount = null,
  bannerFirstTenIds = [],
  cardsFirstTenIds = null,
  usedLegacyMoverList = false,
  isMixedGenerations = false,
  moversMovementFilter = "all",
} = {}) {
  const canonicalDate = getHistoryDateKey(marketAsOfDate);
  const endDates = {
    titleCardEndDate: getHistoryDateKey(titleCardEndDate),
    setValueEndDate: getHistoryDateKey(setValueEndDate),
    openingProfitEndDate: getHistoryDateKey(openingProfitEndDate),
    topChaseEndDate: getHistoryDateKey(topChaseEndDate),
    cardsSnapshotEndDate: getHistoryDateKey(cardsSnapshotEndDate),
  };
  const presentEndDates = Object.entries(endDates).filter(([, date]) => Boolean(date));
  const datesAligned = canonicalDate
    ? presentEndDates.every(([, date]) => date === canonicalDate)
    : presentEndDates.every(([, date]) => date === presentEndDates[0]?.[1]);

  const normalizedBannerIds = (Array.isArray(bannerFirstTenIds) ? bannerFirstTenIds : [])
    .map(toOptionalString)
    .filter(Boolean);
  const normalizedCardsIds = Array.isArray(cardsFirstTenIds)
    ? cardsFirstTenIds.map(toOptionalString).filter(Boolean)
    : null;
  // Banner parity is only assertable when the Cards Market Movers first page
  // is loaded under the same query (window=7D, movement=all, default sort).
  const bannerComparable = normalizedCardsIds !== null && moversMovementFilter === "all";
  const bannerMatchesCards = bannerComparable
    ? idsEqual(normalizedBannerIds, normalizedCardsIds.slice(0, normalizedBannerIds.length))
    : null;

  const diagnostics = {
    setId: toOptionalString(setId),
    generationId: toOptionalString(generationId),
    marketAsOfDate: canonicalDate,
    ...endDates,
    datesAligned,
    totalCards: toOptionalNumber(totalCards),
    cardsWith7dMovement: toOptionalNumber(cardsWith7dMovement),
    nonzero7dMovers: toOptionalNumber(nonzero7dMovers),
    marketMoversFilteredTotal: toOptionalNumber(marketMoversFilteredTotal),
    bannerCount: toOptionalNumber(bannerCount),
    bannerFirstTenIds: normalizedBannerIds,
    cardsFirstTenIds: normalizedCardsIds,
    bannerMatchesCards,
  };

  const warnings = [];
  if (canonicalDate) {
    presentEndDates.forEach(([key, date]) => {
      if (date !== canonicalDate) {
        warnings.push(
          date > canonicalDate
            ? `${key} (${date}) exceeds marketAsOfDate (${canonicalDate})`
            : `${key} (${date}) ends before marketAsOfDate (${canonicalDate})`
        );
      }
    });
  }
  if (
    diagnostics.marketMoversFilteredTotal !== null &&
    diagnostics.nonzero7dMovers !== null &&
    moversMovementFilter === "all" &&
    diagnostics.marketMoversFilteredTotal !== diagnostics.nonzero7dMovers
  ) {
    warnings.push(
      `Market Movers total (${diagnostics.marketMoversFilteredTotal}) differs from the canonical nonzero 7D movement filter (${diagnostics.nonzero7dMovers})`
    );
  }
  if (bannerComparable && bannerMatchesCards === false) {
    warnings.push("Overview banner first ten differ from Cards Market Movers first ten");
  }
  if (usedLegacyMoverList) {
    warnings.push("Market Movers served from a legacy mover list instead of the canonical Cards filter");
  }
  if (isMixedGenerations) {
    warnings.push("Mixed snapshot generations are loaded for this set page");
  }

  return { diagnostics, warnings };
}

/**
 * Log the diagnostics (development only). Split from the builder so the
 * builder stays pure/testable.
 */
export function reportSetPageMarketDiagnostics({ diagnostics, warnings }) {
  if (process.env.NODE_ENV === "production") {
    return;
  }
  console.debug("[pokemon-set-market] set-page market diagnostics", diagnostics);
  warnings.forEach((warning) => {
    console.warn(`[pokemon-set-market] ${warning}`, { setId: diagnostics.setId });
  });
}
