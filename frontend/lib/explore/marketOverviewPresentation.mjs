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
// ---------------------------------------------------------------------------

/** Series identity colors. Identity only — never gain/loss semantics. */
export const MARKET_SERIES_DEFINITIONS = [
  { key: "raw", label: "Raw Card Market", color: "rgba(167,139,250,0.95)", softColor: "rgba(167,139,250,0.16)" },
  { key: "topChase", label: "Top 10 Chase Market", color: "rgba(56,189,248,0.95)", softColor: "rgba(56,189,248,0.16)" },
];

/**
 * Chart / summary windows. `changeKey` is the key the backend publishes inside
 * `changes`; "All" is the display name for Since Tracking.
 */
export const MARKET_OVERVIEW_WINDOWS = [
  { key: "1D", changeKey: "1D", label: "1D", ariaLabel: "1 day" },
  { key: "7D", changeKey: "7D", label: "7D", ariaLabel: "7 days" },
  { key: "30D", changeKey: "30D", label: "30D", ariaLabel: "30 days" },
  { key: "3M", changeKey: "3M", label: "3M", ariaLabel: "3 months" },
  { key: "6M", changeKey: "6M", label: "6M", ariaLabel: "6 months" },
  { key: "1Y", changeKey: "1Y", label: "1Y", ariaLabel: "1 year" },
  { key: "All", changeKey: "SinceTracking", label: "All", ariaLabel: "Since tracking began" },
];

/** The change columns the desktop Market Overview table reports. */
export const MARKET_OVERVIEW_SUMMARY_WINDOWS = [
  { key: "1D", changeKey: "1D", label: "1D" },
  { key: "7D", changeKey: "7D", label: "7D" },
  { key: "30D", changeKey: "30D", label: "30D" },
  { key: "All", changeKey: "SinceTracking", label: "Since Tracking" },
];

export const MARKET_OVERVIEW_HELP = {
  basketValue:
    "Dollar sum of the tracked card basket at current Near Mint values. This is not market capitalization.",
  index: "Normalized market-performance index. Tracking begins at a base value of 100.",
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
  const changes = {};
  for (const [key, value] of Object.entries(raw.changes && typeof raw.changes === "object" ? raw.changes : {})) {
    changes[key] = normalizeChange(value);
  }
  return { ...definition, basketValue, indexValue, historyStartDate: dateKey(raw.historyStartDate), changes, trend };
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
  return {
    contractVersion: String(overview.contractVersion || ""),
    marketDate: dateKey(overview.marketDate),
    coverage: {
      eligibleSetCount: numeric(coverage.eligibleSetCount),
      rawCardCount: numeric(coverage.rawCardCount),
      chaseCardCount: numeric(coverage.chaseCardCount),
    },
    families,
  };
}

/** Backend change object for one family and one display window, or null. */
export function getMarketChange(family, windowKey) {
  const definition = MARKET_OVERVIEW_WINDOWS.find((entry) => entry.key === windowKey)
    || MARKET_OVERVIEW_SUMMARY_WINDOWS.find((entry) => entry.key === windowKey);
  if (!definition) return null;
  return family?.changes?.[definition.changeKey] || null;
}

/**
 * A window is offered only when EVERY published family reports it available.
 * Half a market is not a market, and a partially available window would invite
 * a chart whose two lines cover different spans.
 */
export function isMarketWindowAvailable(overview, windowKey) {
  const families = overview?.families || [];
  if (families.length === 0) return false;
  return families.every((family) => getMarketChange(family, windowKey)?.available === true);
}

/** Window descriptors with `available` resolved, for the timeframe selector. */
export function buildMarketWindowOptions(overview) {
  return MARKET_OVERVIEW_WINDOWS.map((entry) => ({
    ...entry,
    available: isMarketWindowAvailable(overview, entry.key),
  }));
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
 * The visible span is clipped to the BACKEND-provided start/end dates of that
 * window's change object — never to a locally derived cutoff — so the chart and
 * the reported percentage describe the same interval.
 */
export function buildMarketPerformanceSeries(overview, windowKey) {
  const families = overview?.families || [];
  const available = isMarketWindowAvailable(overview, windowKey);
  if (!available) {
    return { windowKey, available: false, startDate: null, endDate: null, dates: [], series: [] };
  }
  const clipped = families.map((family) => {
    const change = getMarketChange(family, windowKey);
    const points = family.trend.filter(
      (point) => (!change?.startDate || point.date >= change.startDate) && (!change?.endDate || point.date <= change.endDate)
    );
    return { family, change, points };
  });
  const dates = [...new Set(clipped.flatMap(({ points }) => points.map((point) => point.date)))].sort();
  const starts = clipped.map(({ change }) => change?.startDate).filter(Boolean).sort();
  const ends = clipped.map(({ change }) => change?.endDate).filter(Boolean).sort();
  return {
    windowKey,
    available: true,
    startDate: starts[0] || dates[0] || null,
    endDate: ends[ends.length - 1] || dates[dates.length - 1] || null,
    dates,
    series: clipped.map(({ family, change, points }) => {
      const byDate = new Map(points.map((point) => [point.date, point.value]));
      return {
        key: family.key,
        label: family.label,
        color: family.color,
        softColor: family.softColor,
        change,
        values: dates.map((date) => (byDate.has(date) ? byDate.get(date) : null)),
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
 * color alone.
 */
export function describeChange(marketLabel, windowLabel, change) {
  if (!change?.available || change.percent === null) {
    return `${marketLabel}, ${windowLabel}: not enough history.`;
  }
  const direction = change.percent > 0 ? "up" : change.percent < 0 ? "down" : "unchanged";
  const magnitude = `${Math.abs(change.percent).toFixed(2)} percent`;
  return change.percent === 0
    ? `${marketLabel}, ${windowLabel}: unchanged.`
    : `${marketLabel}, ${windowLabel}: ${direction} ${magnitude}.`;
}

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
