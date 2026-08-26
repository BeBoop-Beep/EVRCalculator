// ---------------------------------------------------------------------------
// Pokémon Market Overview presentation.
//
// Pure read/format helpers over the published `marketOverview` object of the
// global Set Value Market snapshot (contract `pokemon-market-overview-v1`).
//
// NOTHING here computes a market number. Basket values, index values and every
// percentage change are read verbatim from the backend payload; this module
// only selects, clips and formats. The backend change object is authoritative
// for percent / startDate / endDate / availability, so an unavailable window
// stays unavailable rather than falling back to a neighbouring window.
//
// TWO DIMENSIONS, published separately by the backend and never derived here:
//
//   Tracked Value     — `basketChanges`, the literal dollar movement of the
//                       complete tracked basket. Deliberately INCLUDES sets
//                       entering or leaving the tracked universe.
//   Price Performance — `familyChanges`, the chain-linked common-cohort index
//                       over THIS market's own history. Cohort entry/exit is
//                       neutralized at the transition. `changes`, the shared
//                       cross-market comparison domain, is still published and
//                       still read — but only through
//                       getSharedComparisonChange, and never under a timeframe
//                       button.
//
// They legitimately disagree, which is the whole reason both are shown. Writing
// `current / first - 1` anywhere in this file (or in a component) would be a
// frontend re-derivation of a published figure and is forbidden.
// ---------------------------------------------------------------------------

import { resolveSeriesIdentityColor, softSeriesColor } from "./marketExplorerSeriesColors.mjs";

/**
 * Series identity colors. Identity only — never gain/loss semantics.
 *
 * The color values come from the ONE registry
 * (`marketExplorerSeriesColors.mjs`) rather than being written here, so the
 * Market Overview table, the Explorer rail and the comparison chart cannot
 * drift into three opinions about what color the Raw Card Market is.
 */
export const MARKET_SERIES_DEFINITIONS = [
  { key: "raw", label: "Raw Card Market" },
  { key: "topChase", label: "Top 10 Chase Market" },
  { key: "sealedMarket", label: "Sealed Market" },
].map((entry) => {
  const color = resolveSeriesIdentityColor(entry.key);
  return { ...entry, color, softColor: softSeriesColor(color) };
});

/**
 * Chart / summary windows. `changeKey` is the key the backend publishes.
 *
 * THE USER-FACING TIMEFRAME CONTRACT. Every one of these windows reads the
 * series' OWN published history (`familyChanges`):
 *
 *   1D  — the previous canonical market close
 *   7D  — market date minus 7 elapsed calendar days
 *   30D — minus 30 · 3M — minus 90 · 6M — minus 180 · 1Y — minus 365
 *   All — this series' own complete tracked history / current chain segment
 *
 * "All" USED TO MEAN THE SHARED COMPARABLE START — the longest span every
 * compared market has in common. That is a real analytic, but it is not what a
 * reader means by "All": it let a market whose index read 105.87 report "ALL
 * +3.76%", because the shared span began after that market did. Both numbers
 * were true; only one answers the question the button asks. The shared series
 * survives as `changes`, reachable through getSharedComparisonChange, and is
 * never labelled "All".
 */
export const MARKET_OVERVIEW_WINDOWS = [
  { key: "1D", changeKey: "1D", label: "1D", ariaLabel: "1 day" },
  { key: "7D", changeKey: "7D", label: "7D", ariaLabel: "7 days" },
  { key: "30D", changeKey: "30D", label: "30D", ariaLabel: "30 days" },
  { key: "3M", changeKey: "3M", label: "3M", ariaLabel: "3 months" },
  { key: "6M", changeKey: "6M", label: "6M", ariaLabel: "6 months" },
  { key: "1Y", changeKey: "1Y", label: "1Y", ariaLabel: "1 year" },
  // "All" is each series' OWN full tracked history. Two selected markets may
  // therefore span different dates under one button, which is truthful: they
  // did not begin tracking on the same day.
  { key: "All", changeKey: "SinceTracking", label: "All", ariaLabel: "Since this market began tracking" },
];

/** What the shared "All" window is called wherever it needs naming in prose. */
export const SHARED_COMPARISON_WINDOW_LABEL = "Since Comparable Start";

/** What a market's OWN tracking-start movement is called. */
export const FAMILY_SINCE_TRACKING_LABEL = "Since Tracking";

/** The change columns the desktop Market Overview table reports. */
export const MARKET_OVERVIEW_SUMMARY_WINDOWS = [
  { key: "1D", changeKey: "1D", label: "1D" },
  { key: "7D", changeKey: "7D", label: "7D" },
  { key: "30D", changeKey: "30D", label: "30D" },
  { key: "All", changeKey: "SinceTracking", label: FAMILY_SINCE_TRACKING_LABEL },
];

// THREE DISTINCT STATEMENTS, and the copy must keep them distinct. They are
// frequently different numbers about the same market, all of them true:
//
//   Market Index          — the index LEVEL against this market's own base 100.
//   Since Tracking        — movement from THIS market's own tracking start.
//   All / Comparable Start— movement over the span shared by the compared
//                           markets, which usually begins later.
export const MARKET_OVERVIEW_HELP = {
  trackedValue:
    "Current dollar value of all cards in this tracked basket. It can change because card prices move and because sets enter or leave the tracked universe. This is not market capitalization.",
  trackedValueChange:
    "Price performance since this market's own tracking start — the beginning of its current continuous tracking segment.",
  selectedPeriod:
    "Chain-linked price performance over the selected timeframe, measured from this market's own history. All means since this market began tracking, so it reconciles with its Market Index above.",
  index:
    "Price-performance index, base 100 — not a score. An index of 106.18 means this market is 6.18% above its own index base. It does not mean every card or product in it rose 6.18%. Chain-linking prevents newly added or removed constituents from creating an artificial jump; after one enters, its later price movement affects the index.",
  sinceTracking:
    "Movement since this market's own tracking start. Each market began tracking on its own date, so this is not directly comparable across markets.",
  sharedComparison:
    "Movement over the longest span every compared market shares — the common comparable start. It usually begins later than any single market's own tracking start, and it is NOT what the All timeframe shows.",
};

/** Column-group headings for the two published dimensions. */
export const MARKET_OVERVIEW_GROUPS = {
  trackedValue: "Tracked Market Value",
  pricePerformance: "Price Performance",
};

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
    isSinceFirstAvailable: raw.isSinceFirstAvailable === true,
    isCarriedForwardBaseline: raw.isCarriedForwardBaseline === true,
    baselineSourceDate: dateKey(raw.baselineSourceDate),
  };
}

function normalizeComparisonWindow(raw) {
  if (!raw || typeof raw !== "object") return null;
  const displayStartDate = dateKey(raw.displayStartDate);
  const displayEndDate = dateKey(raw.displayEndDate);
  if (!displayStartDate || !displayEndDate || displayStartDate > displayEndDate) return null;
  return {
    targetStartDate: dateKey(raw.targetStartDate),
    displayStartDate,
    displayEndDate,
    available: raw.available === true,
    coverage: String(raw.coverage || (raw.available === true ? "full" : "unavailable")),
    isSinceFirstAvailable: raw.isSinceFirstAvailable === true,
  };
}

function normalizeFamily(definition, raw) {
  if (!raw || typeof raw !== "object") return null;
  const basketValue = numeric(raw.basketValue);
  const indexValue = numeric(raw.indexValue);
  if (basketValue === null && indexValue === null) return null;
  const trend = (Array.isArray(raw.trend) ? raw.trend : [])
    .map((point) => {
      if (Array.isArray(point)) return { date: dateKey(point[0]), value: numeric(point[1]) };
      return { date: dateKey(point?.date), value: numeric(point?.value) };
    })
    .filter((point) => point.date && point.value !== null)
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const oneDayComparisonTrend = (Array.isArray(raw.oneDayComparison?.comparisonTrend)
    ? raw.oneDayComparison.comparisonTrend : [])
    .map((point) => ({
      date: dateKey(point?.date),
      value: numeric(point?.value),
      isObserved: point?.isObserved === true,
      isCarriedForward: point?.isCarriedForward === true,
      sourceDate: dateKey(point?.sourceDate),
    }))
    .filter((point) => point.date && point.value !== null)
    .sort((a, b) => a.date.localeCompare(b.date));
  const normalizeChangeMap = (source) => {
    const result = {};
    for (const [key, value] of Object.entries(source && typeof source === "object" ? source : {})) {
      result[key] = normalizeChange(value);
    }
    return result;
  };
  return {
    ...definition,
    basketValue,
    // Additive contract field. A snapshot published before the extension
    // simply carries no basketChanges, and the Tracked Value change reads as
    // unavailable rather than being invented here.
    basketChanges: normalizeChangeMap(raw.basketChanges),
    indexValue,
    historyStartDate: dateKey(raw.historyStartDate),
    // TWO price-performance window series, deliberately not merged:
    //   changes       — the SHARED comparison domain (what the chart draws).
    //   familyChanges — this market's OWN history from its own tracking start.
    // A snapshot published before the backend split them carries no
    // familyChanges; the family-specific read then reports unavailable rather
    // than quietly falling back to the shared number under the wrong label.
    changes: normalizeChangeMap(raw.changes),
    familyChanges: normalizeChangeMap(raw.familyChanges),
    // Carried through verbatim so a parent market can be inspected like a
    // prepared segment. Only Total Sealed publishes one: its product roster is
    // short enough to list, and it is the ONLY surface showing the `otherSealed`
    // residual products, which belong to no child market. The raw-card parents
    // deliberately publish none — that universe is a summary, not a table — so
    // this is null for them and the panel says so rather than inventing
    // composition.
    currentConstituents: raw.currentConstituents || null,
    trend,
    oneDayComparisonTrend,
  };
}

/**
 * Normalize the published `marketOverview` for presentation, or return null
 * when the snapshot did not carry one. Never fabricates a family or a change.
 */
export function resolveMarketOverview(payload) {
  const overview = payload && typeof payload === "object"
    ? (payload.marketOverview && typeof payload.marketOverview === "object" ? payload.marketOverview : null)
    : null;
  if (!overview) return null;
  const families = MARKET_SERIES_DEFINITIONS
    .map((definition) => normalizeFamily(definition, overview[definition.key]))
    .filter(Boolean);
  if (families.length === 0) return null;
  const coverage = overview.coverage && typeof overview.coverage === "object" ? overview.coverage : {};
  const comparisonWindows = {};
  for (const [key, value] of Object.entries(overview.comparisonWindows || {})) {
    const normalized = normalizeComparisonWindow(value);
    if (normalized) comparisonWindows[key] = normalized;
  }
  return {
    contractVersion: String(overview.contractVersion || ""),
    marketDate: dateKey(overview.marketDate),
    coverage: {
      eligibleSetCount: numeric(coverage.eligibleSetCount),
      rawCardCount: numeric(coverage.rawCardCount),
      chaseCardCount: numeric(coverage.chaseCardCount),
      sealedProductCount: numeric(coverage.sealedProductCount),
    },
    comparisonWindows,
    families,
  };
}

function resolveWindowDefinition(windowKey) {
  return MARKET_OVERVIEW_WINDOWS.find((entry) => entry.key === windowKey)
    || MARKET_OVERVIEW_SUMMARY_WINDOWS.find((entry) => entry.key === windowKey)
    || null;
}

/**
 * Chain-linked PRICE PERFORMANCE change for one family and display window.
 *
 * `getMarketChange` is the original name and stays as the alias every existing
 * caller (chart legend, summary columns) already uses.
 */
export function getPricePerformanceChange(family, windowKey) {
  const definition = resolveWindowDefinition(windowKey);
  if (!definition) return null;
  return family?.familyChanges?.[definition.changeKey] || null;
}

export const getMarketChange = getPricePerformanceChange;

/**
 * The SHARED cross-market comparison series (`changes`) — the same window key
 * measured over the one span every compared market has in common.
 *
 * PRESERVED, AND DELIBERATELY NOT WIRED TO ANY TIMEFRAME BUTTON. It answers
 * "over the period we can all be measured across, who moved more?", which is a
 * legitimate question and a different one from "how has this market done?".
 * Anything surfacing it must name it "Since Comparable Start" /
 * "Comparable Period" — never "All", and never "Since Tracking".
 */
export function getSharedComparisonChange(family, windowKey) {
  const definition = resolveWindowDefinition(windowKey);
  if (!definition) return null;
  return family?.changes?.[definition.changeKey] || null;
}

/**
 * This market's movement from ITS OWN history — the backend's `familyChanges`.
 *
 * Now the same series `getPricePerformanceChange` reads; kept as a named
 * export because callers that specifically mean "this market's own history"
 * should say so at the call site rather than rely on the default.
 */
export const getFamilyChange = getPricePerformanceChange;

/** The family-specific Since Tracking movement. */
export function getFamilySinceTrackingChange(family) {
  return getFamilyChange(family, "All");
}

/**
 * Literal TRACKED VALUE change — the backend's `basketChanges`, a different
 * published series from `changes`, never computed from basket values here.
 */
export function getTrackedValueChange(family, windowKey) {
  const definition = resolveWindowDefinition(windowKey);
  if (!definition) return null;
  return family?.basketChanges?.[definition.changeKey] || null;
}

/**
 * A selector is useful when at least one published family can render the
 * backend-owned domain. Family availability remains independent.
 */
export function isMarketWindowAvailable(overview, windowKey) {
  const families = overview?.families || [];
  const definition = resolveWindowDefinition(windowKey);
  // AVAILABILITY IS NOW PER-SERIES, not gated on the shared domain. A window
  // the shared calendar cannot support may still be a real, truthful window
  // for an individual market, and under the own-history contract that market
  // is entitled to show it.
  return Boolean(definition)
    && families.length > 0
    && families.some((family) => getMarketChange(family, windowKey)?.available === true);
}

/**
 * The available family changes for one window, and the earliest real start
 * among them. The chart's x-domain and the "since first available" disclosure
 * both come from here, so a window's span and its reported returns cannot be
 * derived from two different places.
 */
function resolveWindowFamilyCoverage(overview, windowKey) {
  const entries = (overview?.families || [])
    .map((family) => ({ family, change: getMarketChange(family, windowKey) }))
    .filter((entry) => entry.change?.available === true && entry.change.startDate && entry.change.endDate);
  if (entries.length === 0) return { entries, startDate: null, endDate: null, isSinceFirstAvailable: false };
  return {
    entries,
    startDate: entries.reduce((earliest, entry) => (
      earliest === null || entry.change.startDate < earliest ? entry.change.startDate : earliest
    ), null),
    endDate: entries.reduce((latest, entry) => (
      latest === null || entry.change.endDate > latest ? entry.change.endDate : latest
    ), null),
    // Published by the backend when a long window could not reach its nominal
    // target and fell back to that series' first observation.
    isSinceFirstAvailable: entries.some((entry) => entry.change.isSinceFirstAvailable === true),
  };
}

/** Window descriptors with `available` resolved, for the timeframe selector. */
export function buildMarketWindowOptions(overview) {
  return MARKET_OVERVIEW_WINDOWS.map((entry) => {
    const coverage = resolveWindowFamilyCoverage(overview, entry.key);
    const available = coverage.entries.length > 0;
    const isSinceFirstAvailable = available && coverage.isSinceFirstAvailable;
    return {
      ...entry,
      ariaLabel: isSinceFirstAvailable
        ? `${entry.ariaLabel}, shown since first available history`
        : entry.ariaLabel,
      available,
      coverage: !available ? "unavailable" : isSinceFirstAvailable ? "partial" : "full",
      isSinceFirstAvailable,
      displayStartDate: coverage.startDate,
    };
  });
}

export const MARKET_PAGE_FAMILY_KEYS = Object.freeze(["raw", "sealedMarket"]);

/**
 * Asset classes the Market Overview ACKNOWLEDGES but cannot yet report.
 *
 * Graded is a real part of the Pokémon market and its absence from this table
 * read as an oversight rather than a roadmap. It is listed so the page states
 * the shape of the market honestly — and listed HERE, as a placeholder with no
 * numeric fields at all, rather than as a family with zeroed values. A row
 * showing $0 / Index 100 / 0.00% would be indistinguishable from a real market
 * that had collapsed, and every consumer that averages or charts families would
 * silently ingest it.
 *
 * `status` is what the row prints where a real market prints an action.
 */
export const MARKET_PAGE_PLACEHOLDER_FAMILIES = Object.freeze([
  Object.freeze({
    key: "graded",
    label: "Graded Market",
    status: "Unavailable",
    // Said in the row's own ⓘ, so "Unavailable" is never a dead end.
    reason: "Graded card prices are not tracked yet, so no Graded index is published. This row is here to show what the tracked market does and does not cover.",
  }),
]);

/** Project the canonical publication into the broad-market /Market summary. */
export function projectMarketPageOverview(overview) {
  if (!overview || typeof overview !== "object") return overview;
  const visibleKeys = new Set(MARKET_PAGE_FAMILY_KEYS);
  return {
    ...overview,
    families: Array.isArray(overview.families)
      ? overview.families.filter((family) => visibleKeys.has(family?.key))
      : [],
  };
}

/** First available window, preferring `preferred`. Null when none are. */
export function resolveDefaultMarketWindow(overview, preferred = "30D") {
  const options = buildMarketWindowOptions(overview);
  if (options.find((entry) => entry.key === preferred)?.available) return preferred;
  return options.find((entry) => entry.available)?.key || null;
}

/**
 * Dual-series chart model for one window.
 *
 * EACH SERIES IS CLIPPED TO ITS OWN backend-published start/end — never to a
 * locally derived cutoff, and never to a start shared with the other series —
 * so every line describes exactly the interval its own legend percentage
 * reports. The x-domain spans the EARLIEST start among the visible series to
 * the latest market date; a series whose history begins later renders null
 * before its first observation rather than being clipped forward to make the
 * lines equal length. Under "All" the lines legitimately begin on different
 * days, because the markets began tracking on different days.
 */
export function buildMarketPerformanceSeries(overview, windowKey) {
  const definition = resolveWindowDefinition(windowKey);
  const coverage = definition ? resolveWindowFamilyCoverage(overview, windowKey) : null;
  if (!coverage?.entries.length) {
    return { windowKey, available: false, startDate: null, endDate: null, dates: [], series: [] };
  }
  const startDate = coverage.startDate;
  const endDate = coverage.endDate;
  const dates = [];
  for (let cursor = new Date(`${startDate}T00:00:00Z`), end = new Date(`${endDate}T00:00:00Z`); cursor <= end; cursor.setUTCDate(cursor.getUTCDate() + 1)) {
    dates.push(cursor.toISOString().slice(0, 10));
  }
  return {
    windowKey,
    available: true,
    startDate,
    endDate,
    dates,
    series: (overview?.families || []).map((family) => {
      const change = getMarketChange(family, windowKey);
      const sourceTrend = windowKey === "1D" && family.oneDayComparisonTrend?.length
        ? family.oneDayComparisonTrend : family.trend;
      const points = change?.available && change.startDate
        ? (sourceTrend || []).filter(
          (point) => point.date >= change.startDate && point.date <= change.endDate
        )
        : [];
      const byDate = new Map(points.map((point) => [point.date, point.value]));
      const pointByDate = new Map(points.map((point) => [point.date, point]));
      return {
        key: family.key,
        label: family.label,
        color: family.color,
        softColor: family.softColor,
        change,
        values: dates.map((date) => (byDate.has(date) ? byDate.get(date) : null)),
        pointMeta: dates.map((date) => pointByDate.get(date) || null),
        points,
      };
    }),
  };
}

// --- formatting -----------------------------------------------------------

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const indexFormat = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const countFormat = new Intl.NumberFormat("en-US");

export function formatBasketValue(value) {
  const parsed = numeric(value);
  return parsed === null ? "—" : currency.format(parsed);
}

export function formatIndexValue(value) {
  const parsed = numeric(value);
  return parsed === null ? "—" : indexFormat.format(parsed);
}

export function formatCount(value) {
  const parsed = numeric(value);
  return parsed === null ? null : countFormat.format(parsed);
}

export function formatMarketDate(value) {
  const key = dateKey(value);
  if (!key) return null;
  return new Date(`${key}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function formatShortDate(value) {
  const key = dateKey(value);
  if (!key) return "";
  return new Date(`${key}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Signed percentage text for a backend change, or an explicit unavailable dash. */
export function formatChangePercent(change) {
  if (!change?.available || change.percent === null) return "—";
  const sign = change.percent > 0 ? "+" : change.percent < 0 ? "−" : "";
  return `${sign}${Math.abs(change.percent).toFixed(2)}%`;
}

export function changeDirection(change) {
  if (!change?.available || change.percent === null) return "unavailable";
  if (change.percent > 0) return "positive";
  if (change.percent < 0) return "negative";
  return "neutral";
}

/**
 * Screen-reader text for a change cell. Direction is spoken, never implied by
 * color alone, and `dimension` keeps the two published series distinguishable —
 * "Tracked Value, Since Tracking: up 7.16 percent" is a different statement
 * from "Price Performance, Since Tracking: up 1.95 percent".
 */
export function describeChange(marketLabel, windowLabel, change, { dimension = null } = {}) {
  const subject = [marketLabel, dimension, windowLabel].filter(Boolean).join(", ");
  if (!change?.available || change.percent === null) {
    return `${subject}: not enough history.`;
  }
  const direction = change.percent > 0 ? "up" : change.percent < 0 ? "down" : "unchanged";
  const magnitude = `${Math.abs(change.percent).toFixed(2)} percent`;
  return change.percent === 0
    ? `${subject}: unchanged.`
    : `${subject}: ${direction} ${magnitude}.`;
}

/** Spoken names for the two dimensions, used by describeChange callers. */
export const MARKET_DIMENSION_LABELS = {
  trackedValue: "Tracked Value",
  pricePerformance: "Price Performance",
};

/** Accessible label for an unavailable timeframe button. */
export function describeUnavailableWindow(windowLabel) {
  return `${windowLabel} — not enough history`;
}

/** Quiet header metadata line parts. Omits anything the snapshot lacks. */
export function buildCoverageSummary(overview) {
  if (!overview) return [];
  const parts = [];
  const asOf = formatMarketDate(overview.marketDate);
  if (asOf) parts.push(`As of ${asOf}`);
  const sets = formatCount(overview.coverage?.eligibleSetCount);
  if (sets) parts.push(`${sets} tracked ${overview.coverage.eligibleSetCount === 1 ? "set" : "sets"}`);
  const rawCards = formatCount(overview.coverage?.rawCardCount);
  if (rawCards) parts.push(`${rawCards} raw cards`);
  const chaseCards = formatCount(overview.coverage?.chaseCardCount);
  if (chaseCards) parts.push(`${chaseCards} chase cards`);
  return parts;
}
