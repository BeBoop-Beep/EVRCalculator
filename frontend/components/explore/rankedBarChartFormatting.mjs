// Pure, framework-free helpers for CompactRankedBarChart (Simulation Results →
// Value Structure and Pack Paths → Normal State Distribution). Everything here
// is display math/formatting only — no row is ever dropped or mutated, so the
// exact underlying values stay available to tooltips unchanged.

// Compact geometry: ~23px row pitch keeps 10 rarity groups near 246px and 17
// normal states near 407px, instead of the old multi-line row list's 600-800px.
export const COMPACT_BAR_ROW_HEIGHT = 23;
export const COMPACT_BAR_CHART_PADDING = 16;

// Readable "nice" axis ceilings for share-of-total (0-100%) bars. Using the
// first ceiling >= the actual maximum keeps bars using most of the plot width
// without normalizing the largest category to a misleading 100%.
export const NICE_SHARE_DOMAIN_CEILINGS = [1, 2, 5, 10, 15, 20, 25, 30, 40, 50, 60, 75, 100];

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function getNiceShareDomainMaximum(maxPercent) {
  const parsed = toFiniteNumber(maxPercent);
  if (parsed === null || parsed <= 0) {
    return NICE_SHARE_DOMAIN_CEILINGS[0];
  }
  for (const ceiling of NICE_SHARE_DOMAIN_CEILINGS) {
    if (ceiling >= parsed) {
      return ceiling;
    }
  }
  return 100;
}

// Non-mutating descending sort; returns the SAME row objects (identity is what
// lets tooltips read exact untouched source data) and always all of them.
export function sortRowsByValueDescending(rows, valueKey = "value") {
  const list = Array.isArray(rows) ? rows : [];
  return [...list].sort(
    (left, right) => (toFiniteNumber(right?.[valueKey]) ?? 0) - (toFiniteNumber(left?.[valueKey]) ?? 0)
  );
}

export function getCompactChartHeight(
  rowCount,
  { rowHeight = COMPACT_BAR_ROW_HEIGHT, padding = COMPACT_BAR_CHART_PADDING } = {}
) {
  const count = Math.max(1, toFiniteNumber(rowCount) ?? 1);
  return Math.round(count * rowHeight + padding);
}

// One-line ellipsis truncation for the fixed label column. The input string is
// never modified — the full name stays on the row for the tooltip.
export function truncateChartLabel(label, maxChars = 26) {
  const text = String(label ?? "");
  if (maxChars <= 1 || text.length <= maxChars) {
    return text;
  }
  return `${text.slice(0, maxChars - 1).trimEnd()}…`;
}

// Abbreviated count for the fixed right value column: full en-US grouping up to
// six digits (463,196 stays exact per design), then 1.0M / 1.2B style.
export function formatAbbreviatedCount(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) {
    return "—";
  }
  const abs = Math.abs(parsed);
  if (abs >= 1e9) {
    return `${(parsed / 1e9).toFixed(1)}B`;
  }
  if (abs >= 1e6) {
    return `${(parsed / 1e6).toFixed(1)}M`;
  }
  return Math.round(parsed).toLocaleString("en-US");
}

// Abbreviated currency for the fixed right value column:
//   $6,255,870.74 -> $6.26M     $8,742.03 -> $8.7K     $845.20 -> $845
export function formatAbbreviatedCurrency(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) {
    return "—";
  }
  const sign = parsed < 0 ? "-" : "";
  const abs = Math.abs(parsed);
  if (abs >= 1e9) {
    return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  }
  if (abs >= 1e6) {
    return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  }
  if (abs >= 1e3) {
    return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  }
  return `${sign}$${Math.round(abs).toLocaleString("en-US")}`;
}
