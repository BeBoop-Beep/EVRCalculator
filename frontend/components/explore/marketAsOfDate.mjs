import { getHistoryDateKey } from "./historyDateFormatting.mjs";

// ---------------------------------------------------------------------------
// Canonical market as-of date resolution for the set-detail page.
//
// Every market-driven surface (hero sparkline, Set Value Trend, Opening
// Profit vs Cost, Top Chase, Market Movers, Cards movement values) must end
// on ONE canonical marketAsOfDate that comes from the coordinated snapshot
// generation's own market observations — never from the browser's calendar
// date, the server's UTC "today", request time, or snapshot updated_at.
//
// When mixed snapshot generations are temporarily loaded (older rows still
// being replaced by a coordinated rebuild), the shared display cutoff is the
// MINIMUM authoritative market date among the loaded market datasets, so no
// section can display a day its siblings do not have. That is a
// compatibility safeguard only; the normal state is one generation and one
// marketAsOfDate.
// ---------------------------------------------------------------------------

function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

/**
 * Extract { generationId, marketAsOfDate } from a slim endpoint payload.
 * Reads only snapshot-generation metadata (meta.snapshot / latestMarketDate),
 * never runtime clock values.
 */
export function getMarketDateSourceFromPayload(key, payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const snapshot = payload?.meta?.snapshot && typeof payload.meta.snapshot === "object" ? payload.meta.snapshot : {};
  const marketAsOfDate =
    getHistoryDateKey(snapshot.marketAsOfDate) ||
    getHistoryDateKey(snapshot.movementAsOfDate) ||
    getHistoryDateKey(payload?.latestMarketDate ?? payload?.latest_market_date) ||
    getHistoryDateKey(snapshot.latestMarketDate) ||
    null;
  if (!marketAsOfDate) {
    return null;
  }
  return {
    key: toOptionalString(key) || "unknown",
    generationId: toOptionalString(snapshot.generationId),
    marketAsOfDate,
  };
}

/**
 * Resolve the shared canonical market as-of date from the loaded market
 * datasets. `sources` is an array of { key, generationId, marketAsOfDate }
 * (null entries are ignored).
 *
 * Returns:
 *   marketAsOfDate — the shared display cutoff (null when nothing loaded);
 *   isMixedGenerations — more than one distinct generationId was seen;
 *   isMixedDates — sources disagree on their market date;
 *   sources — the accepted sources (for diagnostics).
 *
 * With a single coordinated generation every source reports the same date and
 * that date is returned. With mixed generations/dates the minimum date wins.
 */
export function resolveMarketAsOfDate(sources = []) {
  const accepted = (Array.isArray(sources) ? sources : [])
    .filter((source) => source && getHistoryDateKey(source.marketAsOfDate))
    .map((source) => ({
      key: toOptionalString(source.key) || "unknown",
      generationId: toOptionalString(source.generationId),
      marketAsOfDate: getHistoryDateKey(source.marketAsOfDate),
    }));

  if (accepted.length === 0) {
    return {
      marketAsOfDate: null,
      isMixedGenerations: false,
      isMixedDates: false,
      sources: [],
    };
  }

  const distinctDates = [...new Set(accepted.map((source) => source.marketAsOfDate))].sort();
  const distinctGenerations = [
    ...new Set(accepted.map((source) => source.generationId).filter(Boolean)),
  ];

  return {
    // Shared compatibility cutoff: minimum authoritative market date.
    marketAsOfDate: distinctDates[0],
    isMixedGenerations: distinctGenerations.length > 1,
    isMixedDates: distinctDates.length > 1,
    sources: accepted,
  };
}

/**
 * Development-only warning when mixed snapshot generations (or disagreeing
 * market dates) are loaded for one set page. Silent in production and when
 * everything agrees.
 */
export function warnOnMixedMarketDates(setId, resolution) {
  if (process.env.NODE_ENV === "production") {
    return;
  }
  if (!resolution || (!resolution.isMixedDates && !resolution.isMixedGenerations)) {
    return;
  }
  console.warn("[pokemon-market-date] mixed snapshot generations/market dates on set page", {
    setId: toOptionalString(setId),
    generationIds: Object.fromEntries(
      (resolution.sources || []).map((source) => [source.key, source.generationId])
    ),
    marketDates: Object.fromEntries(
      (resolution.sources || []).map((source) => [source.key, source.marketAsOfDate])
    ),
    sharedCutoff: resolution.marketAsOfDate,
  });
}

/**
 * Clamp history points so no point exceeds the canonical end date. Returns
 * the original array when no clamping is needed; never mutates the input.
 */
export function clampHistoryPointsToDate(points, endDateKey, { dateKey = "date" } = {}) {
  const rows = Array.isArray(points) ? points : [];
  const endDate = getHistoryDateKey(endDateKey);
  if (!endDate) {
    return rows;
  }
  const needsClamp = rows.some((point) => {
    const date = getHistoryDateKey(point?.[dateKey]);
    return date && date > endDate;
  });
  if (!needsClamp) {
    return rows;
  }
  return rows.filter((point) => {
    const date = getHistoryDateKey(point?.[dateKey]);
    return !date || date <= endDate;
  });
}
