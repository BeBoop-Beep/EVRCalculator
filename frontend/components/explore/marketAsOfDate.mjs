import { getHistoryDateKey } from "./historyDateFormatting.mjs";

// ---------------------------------------------------------------------------
// Canonical market as-of date resolution for the set-detail page.
//
// Every market-driven surface (hero sparkline, Set Value Trend, Opening
// Profit vs Cost, Top Chase, Market Movers, Cards movement values) should be
// published from ONE coordinated snapshot generation. During a broken or
// partially completed publication, however, a secondary module can temporarily
// belong to an older generation.
//
// The primary Overview generation is authoritative for the page cutoff. A stale
// Market Movers or Cards response must be quarantined rather than allowed to
// roll current Overview / Top Chase charts backward. When Overview is not loaded,
// Top Chase is the next authority, followed by Market Movers and Cards.
// ---------------------------------------------------------------------------

const MARKET_SOURCE_PRIORITY = ["overview", "topChase", "marketMovers", "cards"];

function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function sourcePriority(source) {
  const index = MARKET_SOURCE_PRIORITY.indexOf(source?.key);
  return index >= 0 ? index : MARKET_SOURCE_PRIORITY.length;
}

function sourceCohortKey(source) {
  if (source?.generationId) {
    return `generation:${source.generationId}`;
  }
  // Legacy snapshots cannot prove common generation identity. Treat only
  // legacy sources that advertise the same market date as compatible.
  return `legacy-date:${source?.marketAsOfDate || "unknown"}`;
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
 * Client-hydration freshness guard.
 *
 * Given a server-provided seed payload and a client/API-fetched live payload for
 * the same surface, return whichever carries the newer market as-of date. A
 * stale server seed (e.g. a cached /overview response ending an older market
 * date) must never win over a newer live response. On ties, or when either date
 * is unknown, the freshly-fetched live payload wins because it is the
 * authoritative just-fetched value. Pure: never mutates its inputs.
 */
export function chooseFresherMarketPayload(seedPayload, livePayload) {
  if (!livePayload) {
    return seedPayload || null;
  }
  if (!seedPayload) {
    return livePayload;
  }
  const seedDate = getMarketDateSourceFromPayload("seed", seedPayload)?.marketAsOfDate || null;
  const liveDate = getMarketDateSourceFromPayload("live", livePayload)?.marketAsOfDate || null;
  if (seedDate && liveDate && seedDate > liveDate) {
    return seedPayload;
  }
  return livePayload;
}

/**
 * True when a server seed is strictly older (by market as-of date) than a live
 * payload — i.e. the seed must be rejected in favor of the newer response.
 */
export function isServerSeedStale(seedPayload, livePayload) {
  const seedDate = getMarketDateSourceFromPayload("seed", seedPayload)?.marketAsOfDate || null;
  const liveDate = getMarketDateSourceFromPayload("live", livePayload)?.marketAsOfDate || null;
  if (!seedDate || !liveDate) {
    return false;
  }
  return seedDate < liveDate;
}

/**
 * Resolve the canonical market date from loaded market datasets.
 *
 * The highest-priority loaded source establishes the active publication cohort:
 * Overview -> Top Chase -> Market Movers -> Cards. Sources from the same
 * generation are compatible. Legacy sources with no generation id are only
 * compatible when they report the same market date.
 *
 * Sources outside the active cohort are returned in excludedSources and must
 * not downgrade the shared page cutoff. This prevents a stale Cards-derived
 * Market Movers response from rolling a current Overview back several days.
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
      selectedSourceKey: null,
      selectedGenerationId: null,
      isMixedGenerations: false,
      isMixedDates: false,
      sources: [],
      compatibleSources: [],
      excludedSources: [],
    };
  }

  const selectedSource = [...accepted].sort((left, right) => sourcePriority(left) - sourcePriority(right))[0];
  const selectedCohort = sourceCohortKey(selectedSource);
  const compatibleSources = accepted.filter((source) => sourceCohortKey(source) === selectedCohort);
  const excludedSources = accepted
    .filter((source) => sourceCohortKey(source) !== selectedCohort)
    .map((source) => ({
      ...source,
      reason:
        source.generationId !== selectedSource.generationId
          ? "generation_mismatch"
          : "legacy_market_date_mismatch",
    }));

  const compatibleDates = [...new Set(compatibleSources.map((source) => source.marketAsOfDate))].sort();
  const distinctDates = [...new Set(accepted.map((source) => source.marketAsOfDate))].sort();

  return {
    // Same-generation sources should agree. Keep the conservative minimum only
    // inside the selected cohort; mismatched cohorts never control this cutoff.
    marketAsOfDate: compatibleDates[0] || selectedSource.marketAsOfDate,
    selectedSourceKey: selectedSource.key,
    selectedGenerationId: selectedSource.generationId,
    isMixedGenerations: excludedSources.some(
      (source) => source.generationId !== selectedSource.generationId
    ),
    isMixedDates: distinctDates.length > 1,
    sources: accepted,
    compatibleSources,
    excludedSources,
  };
}

/** Return true when a source key belongs to the active publication cohort. */
export function isMarketDateSourceCompatible(resolution, sourceKey) {
  const key = toOptionalString(sourceKey);
  if (!key || !resolution) {
    return false;
  }
  return (resolution.compatibleSources || []).some((source) => source.key === key);
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
    selectedSourceKey: resolution.selectedSourceKey,
    selectedGenerationId: resolution.selectedGenerationId,
    sharedCutoff: resolution.marketAsOfDate,
    excludedSources: resolution.excludedSources || [],
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
