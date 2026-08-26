// ---------------------------------------------------------------------------
// Presentation model for the DESKTOP Set Market overview (Section 2).
//
// The Market page reads the set through three LENSES — Cards, Sealed, Graded —
// and this module is the one place that decides, per lens, whether there is
// anything honest to show. The rule the whole surface rests on:
//
//   a lens with no authoritative history is UNAVAILABLE, never $0.
//
// Zero is a real price. Publishing it for a market nobody has priced would tell
// the reader the set's graded market is worthless, which is a different and
// false claim from "we do not track this yet". Every builder here returns an
// explicit `available: false` with a reason instead of a number.
//
// Nothing in this file re-derives a canonical figure. Window selection and
// delta math come from lib/explore/marketDeltaWindows.mjs — the same helpers
// the Set Value trend already uses — so a 30D move reads identically here and
// everywhere else on the page.
// ---------------------------------------------------------------------------

import {
  getSelectedDeltaWindowFromHistory,
  getVisibleHistoryWindowMetrics,
} from "../../../../lib/explore/marketDeltaWindows.mjs";
import { getHistoryDateKey } from "../../../explore/historyDateFormatting.mjs";

export const MARKET_SEGMENT_KEYS = ["cards", "sealed", "graded"];

export const MARKET_SEGMENT_LABELS = {
  cards: "Cards",
  sealed: "Sealed",
  graded: "Graded",
};

/** The single string the UI prints wherever a lens has no history. */
export const SEGMENT_UNAVAILABLE_TEXT = "Not enough market data";

export function toPreparedMovementKey(windowKey) {
  return String(windowKey || "").toLowerCase() === "lifetime" ? "SinceTracking" : String(windowKey || "");
}

export function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Fold any published market history into the one shape the chart reads.
 *
 * Cards history speaks `setValue`, the sealed snapshot speaks `marketPrice`.
 * Both are a dollar figure on a date, so they are normalized once here rather
 * than teaching the chart two vocabularies.
 */
export function normalizeSegmentHistory(history) {
  return (Array.isArray(history) ? history : [])
    .map((point) => {
      const date = getHistoryDateKey(point?.date);
      const setValue = toFiniteNumber(
        point?.setValue ?? point?.set_value ?? point?.marketPrice ?? point?.market_price ?? point?.value
      );
      return date ? { ...point, date, setValue } : null;
    })
    .filter(Boolean)
    .sort((left, right) => (left.date < right.date ? -1 : left.date > right.date ? 1 : 0));
}

/**
 * Everything the left panel and one Set Signals row need for a single lens at a
 * single timeframe.
 *
 * `available` is false whenever the lens cannot produce a current value. The
 * caller renders an em dash for those; it must not substitute a zero.
 */
export function selectSegmentTrend({
  history,
  selectedWindowKey = null,
  // Site-wide market convention: 7D is the initial timeframe everywhere a
  // reader hasn't made an explicit choice. Callers that DO have an explicit
  // selection (a click, a URL param) pass it as `selectedWindowKey`, which
  // always wins — this default only governs the very first render.
  preferredWindowKey = "7D",
  trackedItemCount = null,
  trackedItemNoun = "Cards",
} = {}) {
  const points = normalizeSegmentHistory(history);
  const valuedPoints = points.filter((point) => point.setValue !== null);

  const { windows, effectiveKey, selectedWindow } = getSelectedDeltaWindowFromHistory(valuedPoints, {
    selectedKey: selectedWindowKey,
    preferredKey: preferredWindowKey,
    dateKey: "date",
    valueKey: "setValue",
    preferObservedPoints: true,
  });
  const metrics = getVisibleHistoryWindowMetrics(points, selectedWindow, {
    dateKey: "date",
    valueKey: "setValue",
    preferObservedPoints: true,
  });

  // Period high/low are read from the points actually on screen, so the two
  // figures always bracket the line the reader is looking at.
  const windowValues = metrics.valuedPoints.map((point) => toFiniteNumber(point.setValue)).filter((value) => value !== null);

  return {
    available: metrics.currentValue !== null,
    points,
    series: metrics.points,
    currentValue: metrics.currentValue,
    deltaAmount: metrics.deltaAmount,
    deltaPercent: metrics.deltaPercent,
    periodHigh: windowValues.length ? Math.max(...windowValues) : null,
    periodLow: windowValues.length ? Math.min(...windowValues) : null,
    firstPoint: metrics.firstPoint,
    lastPoint: metrics.latestPoint,
    // "Tracking since" is the first date the lens has ANY observation, not the
    // first date inside the selected window — it answers "how long have you
    // watched this", which does not change when the reader picks 7D.
    trackingSinceDate: valuedPoints[0]?.date || null,
    trackedItemCount: toFiniteNumber(trackedItemCount),
    trackedItemNoun,
    availableDeltaWindows: windows,
    effectiveWindowKey: effectiveKey,
    hasTrend: metrics.deltaAmount !== null,
  };
}

/**
 * Overlay the prepared market-index contract on a dollar-value trend.
 * Dollar amounts/highs/lows remain Set Value readings; percentage movement is
 * the canonical index movement so constituent churn cannot masquerade as
 * market performance.
 */
export function selectPreparedSegmentTrend({
  valueHistory,
  marketIndex,
  selectedWindowKey = "7D",
  trackedItemCount = null,
  trackedItemNoun = "Cards",
} = {}) {
  const valueTrend = selectSegmentTrend({
    history: valueHistory,
    selectedWindowKey,
    trackedItemCount,
    trackedItemNoun,
  });
  const indexHistory = normalizeSegmentHistory(
    (marketIndex?.history || []).map((point) => ({
      ...point,
      setValue: point?.indexValue ?? point?.index_value,
    }))
  );
  const indexTrend = selectSegmentTrend({ history: indexHistory, selectedWindowKey });
  const movementKey = toPreparedMovementKey(selectedWindowKey);
  const movement = marketIndex?.movements?.[movementKey] || marketIndex?.movements?.[String(movementKey).toLowerCase()] || null;
  const movementPercent = toFiniteNumber(movement?.percent);

  if (!valueTrend.available || !indexTrend.available) {
    return unavailableSegmentTrend({ trackedItemNoun });
  }

  return {
    ...valueTrend,
    deltaPercent: movement?.available === false ? null : movementPercent ?? indexTrend.deltaPercent,
    marketIndexValue: toFiniteNumber(marketIndex?.currentValue ?? marketIndex?.current_value) ?? indexTrend.currentValue,
    marketIndexBaseValue: toFiniteNumber(marketIndex?.baseValue ?? marketIndex?.base_value),
    marketIndexTrackingSinceDate:
      getHistoryDateKey(marketIndex?.trackingSince ?? marketIndex?.tracking_since) || indexTrend.trackingSinceDate,
    indexSeries: indexTrend.series,
    indexMovement: movement,
    trackingSinceDate:
      getHistoryDateKey(marketIndex?.trackingSince ?? marketIndex?.tracking_since) || indexTrend.trackingSinceDate,
    availableDeltaWindows: valueTrend.availableDeltaWindows.map((window) =>
      window.key === "lifetime" ? { ...window, label: "All" } : window
    ),
  };
}

/** The unavailable lens. One shape, so callers never branch on null. */
export function unavailableSegmentTrend({ reason = SEGMENT_UNAVAILABLE_TEXT, trackedItemNoun = "Items" } = {}) {
  return {
    available: false,
    unavailableReason: reason,
    points: [],
    series: [],
    currentValue: null,
    deltaAmount: null,
    deltaPercent: null,
    periodHigh: null,
    periodLow: null,
    firstPoint: null,
    lastPoint: null,
    trackingSinceDate: null,
    trackedItemCount: null,
    trackedItemNoun,
    availableDeltaWindows: [],
    effectiveWindowKey: null,
    hasTrend: false,
  };
}

/**
 * The MARKET SEGMENTS rows on the right rail.
 *
 * An unavailable segment still gets a row — the reader is told the lens exists
 * and is empty — but it is not selectable, because switching the chart to a
 * series that does not exist is a dead end.
 */
export function buildMarketSegmentRows(trendsByKey = {}) {
  return MARKET_SEGMENT_KEYS.map((key) => {
    const trend = trendsByKey[key] || unavailableSegmentTrend();
    return {
      key,
      label: MARKET_SEGMENT_LABELS[key],
      available: Boolean(trend.available),
      selectable: Boolean(trend.available),
      currentValue: trend.currentValue,
      deltaAmount: trend.deltaAmount,
      deltaPercent: trend.deltaPercent,
      marketIndexValue: trend.marketIndexValue,
      unavailableReason: trend.available ? null : trend.unavailableReason || SEGMENT_UNAVAILABLE_TEXT,
    };
  });
}

/**
 * The lens the page opens on.
 *
 * Cards is the approved default and wins whenever it has data. The fallbacks
 * exist only so a set with no card history does not open on a dead panel.
 */
export function resolveDefaultSegmentKey(trendsByKey = {}) {
  if (trendsByKey.cards?.available) return "cards";
  return MARKET_SEGMENT_KEYS.find((key) => trendsByKey[key]?.available) || "cards";
}

/** Never let a selection strand the chart on an unavailable lens. */
export function resolveActiveSegmentKey(requestedKey, trendsByKey = {}) {
  const requested = String(requestedKey || "").trim();
  if (MARKET_SEGMENT_KEYS.includes(requested) && trendsByKey[requested]?.available) {
    return requested;
  }
  return resolveDefaultSegmentKey(trendsByKey);
}

// --- Market Breadth ---------------------------------------------------------

/** Maps a Breadth entry's backend `status` to an honest, reader-facing reason. */
const BREADTH_STATUS_REASONS = {
  insufficient_history: "Not enough tracked history for this period yet",
  no_common_cohort: "No common comparable cohort for this period",
  baseline_unavailable: "No prior comparison point for this period",
};

function breadthReasonForStatus(status) {
  return BREADTH_STATUS_REASONS[status] || SEGMENT_UNAVAILABLE_TEXT;
}

/**
 * Reads the canonical cardsMarket.marketBreadth entry for the selected window.
 *
 * Breadth is its own analytical contract, published for every window the
 * Cards Market Index publishes (1D/7D/30D/3M/6M/1Y/SinceTracking) — it is not
 * derived from the Movers ticker and is not restricted to Movers' 1D/7D/30D.
 * The window key is normalized through the SAME `toPreparedMovementKey`
 * mapper the Cards Market Index uses, so "lifetime" resolves to
 * "SinceTracking" identically for both surfaces.
 */
export function selectPreparedMarketBreadth({ marketBreadth, windowKey } = {}) {
  const movementKey = toPreparedMovementKey(windowKey);
  const entry = marketBreadth?.[movementKey] || marketBreadth?.[String(movementKey).toLowerCase()] || null;
  if (!entry) {
    return { available: false, reason: SEGMENT_UNAVAILABLE_TEXT, windowKey: movementKey || null };
  }
  if (entry.available === false) {
    return { available: false, reason: breadthReasonForStatus(entry.status), windowKey: movementKey || null };
  }
  const advancing = toFiniteNumber(entry.advancingCount ?? entry.advancing_count);
  const declining = toFiniteNumber(entry.decliningCount ?? entry.declining_count);
  const flat = toFiniteNumber(entry.unchangedCount ?? entry.unchanged_count);
  const total = toFiniteNumber(entry.eligibleCount ?? entry.eligible_count);
  const advancingPercent = toFiniteNumber(entry.advancingPercent ?? entry.advancing_percent);
  const decliningPercent = toFiniteNumber(entry.decliningPercent ?? entry.declining_percent);
  const unchangedPercent = toFiniteNumber(entry.unchangedPercent ?? entry.unchanged_percent);
  if (total === null || advancingPercent === null || decliningPercent === null) {
    return { available: false, reason: SEGMENT_UNAVAILABLE_TEXT, windowKey: movementKey || null };
  }
  const isSinceFirstAvailable = Boolean(entry.isSinceFirstAvailable ?? entry.is_since_first_available);
  return {
    available: true,
    windowKey: movementKey,
    advancing,
    declining,
    flat,
    total,
    advancingPercent,
    decliningPercent,
    unchangedPercent: unchangedPercent ?? Math.max(0, Math.round((100 - advancingPercent - decliningPercent) * 10) / 10),
    coverage: entry.coverage ?? null,
    isSinceFirstAvailable,
    partialLabel: isSinceFirstAvailable ? "Since first available" : null,
  };
}

// --- Chase Concentration ----------------------------------------------------

/**
 * The Top 10 chase cards as a share of the set's card market.
 *
 * Both figures are canonical set-value scopes the page already fetches —
 * `top10` over `standard` — compared on the same date. This module does not sum
 * the Top 10 list's prices to get there: that list is price-descending at
 * today's prices, while the published scopes are the values the set-value
 * builder actually recorded, and only the latter two are guaranteed to be the
 * same measurement taken the same way.
 *
 * No Low/Medium/High banding is applied. No such thresholds are defined
 * anywhere in the product, so inventing them here would present an opinion as a
 * published classification.
 */
export function selectChaseConcentration({ top10Value, cardsValue } = {}) {
  const top10 = toFiniteNumber(top10Value);
  const cards = toFiniteNumber(cardsValue);
  if (top10 === null || cards === null || cards <= 0) {
    return { available: false, reason: SEGMENT_UNAVAILABLE_TEXT, top10Value: top10, sharePercent: null };
  }
  return {
    available: true,
    top10Value: top10,
    cardsValue: cards,
    sharePercent: Math.round((top10 / cards) * 1000) / 10,
  };
}

// --- Supporting details -----------------------------------------------------

/**
 * The four-field block under the graph. Market Index is intentionally absent:
 * it is a primary-summary KPI, while these are supporting diagnostics.
 * A field with no value is returned as null and printed as an em dash.
 */
export function buildSupportingDetails(trend = {}) {
  const count = toFiniteNumber(trend.trackedItemCount);
  return [
    { key: "periodHigh", label: "Period High", value: trend.periodHigh ?? null },
    { key: "periodLow", label: "Period Low", value: trend.periodLow ?? null },
    { key: "trackingSince", label: "Tracking Since", date: trend.trackingSinceDate ?? null },
    { key: "trackedItems", label: "Tracked Items", count, noun: trend.trackedItemNoun || "Items", secondary: true },
  ];
}
