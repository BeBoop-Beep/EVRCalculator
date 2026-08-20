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

/** Breadth is only defined for the windows the movers contract publishes. */
export const BREADTH_SUPPORTED_WINDOW_KEYS = ["1D", "7D", "30D"];

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
  preferredWindowKey = "30D",
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

/**
 * How much of the set is advancing versus declining over the selected window.
 *
 * Counted from `marketMovers.all`, which is the COMPLETE mover-eligible
 * movement list for a window — not the truncated heatingUp/coolingOff lists the
 * ticker draws from. Counting the ticker's ten rows would report a breadth of
 * whatever the page happened to display.
 *
 * The denominator is deliberately named to the reader as mover-eligible cards
 * rather than "all cards": the backend applies price and history-span
 * guardrails before a card is eligible to move, so this is a share of the
 * cards whose movement is measurable, and the surface says so.
 *
 * The movers contract publishes 1D, 7D and 30D only. Longer timeframes have no
 * authoritative breadth reading, so they return `available: false` and the
 * module renders as unavailable rather than reusing a shorter window's answer.
 */
export function selectMarketBreadth({ moversByWindow, windowKey } = {}) {
  const normalized = String(windowKey || "").trim().toUpperCase();
  if (!BREADTH_SUPPORTED_WINDOW_KEYS.includes(normalized)) {
    return {
      available: false,
      reason: "Breadth is published for 1D, 7D and 30D only.",
      windowKey: normalized || null,
    };
  }

  const entry = moversByWindow?.[normalized] || moversByWindow?.[normalized.toLowerCase()] || null;
  const movements =
    entry?.marketMovers?.all ||
    entry?.market_movers?.all ||
    entry?.marketMovers?.All ||
    (Array.isArray(entry?.all) ? entry.all : null);

  if (!Array.isArray(movements) || movements.length === 0) {
    return { available: false, reason: SEGMENT_UNAVAILABLE_TEXT, windowKey: normalized };
  }

  let advancing = 0;
  let declining = 0;
  let flat = 0;
  for (const movement of movements) {
    const amount = toFiniteNumber(movement?.changeAmount ?? movement?.change_amount);
    if (amount === null) continue;
    if (amount > 0) advancing += 1;
    else if (amount < 0) declining += 1;
    else flat += 1;
  }

  const total = advancing + declining + flat;
  if (total === 0) {
    return { available: false, reason: SEGMENT_UNAVAILABLE_TEXT, windowKey: normalized };
  }

  return {
    available: true,
    windowKey: normalized,
    advancing,
    declining,
    flat,
    total,
    advancingPercent: Math.round((advancing / total) * 1000) / 10,
    decliningPercent: Math.round((declining / total) * 1000) / 10,
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
 * The six-field block under the graph. Every field is derived from the ACTIVE
 * lens at the ACTIVE timeframe, so switching either recomputes all six.
 * A field with no value is returned as null and printed as an em dash.
 */
export function buildSupportingDetails(trend = {}) {
  const count = toFiniteNumber(trend.trackedItemCount);
  return [
    { key: "periodChange", label: "Period Change", amount: trend.deltaAmount ?? null },
    { key: "periodReturn", label: "Period Return", percent: trend.deltaPercent ?? null },
    { key: "periodHigh", label: "Period High", value: trend.periodHigh ?? null },
    { key: "periodLow", label: "Period Low", value: trend.periodLow ?? null },
    { key: "trackingSince", label: "Tracking Since", date: trend.trackingSinceDate ?? null },
    {
      key: "trackedItems",
      label: "Tracked Items",
      count,
      noun: trend.trackedItemNoun || "Items",
    },
  ];
}
