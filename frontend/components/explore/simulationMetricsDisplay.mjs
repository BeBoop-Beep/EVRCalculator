// Pure display helpers for the Simulation Results → Metrics tab redesign:
// the shared value formatter, odds phrasing, the log-scale percentile strip
// model, the computed takeaway sentence, and the expert judgment tags.
// Framework-free so every rule here is unit-testable.

import { formatAbbreviatedCurrency } from "./rankedBarChartFormatting.mjs";

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

// ─── Shared metric formatter ─────────────────────────────────────────────────
// Every number the Metrics tab displays passes through one of these:
//   currency >= $1,000 -> "$1.4K" / "$8.74M" (same abbreviation style as the
//   Value Structure chart's right column); currency < $1,000 -> 2 decimals;
//   ratios -> 2 decimals + "x"; percentages -> 1 decimal + "%"; unitless
//   statistics (CV, HHI) -> fixed decimals as-is. Missing data stays "—".

export function formatMetricCurrency(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) {
    return "—";
  }
  if (Math.abs(parsed) >= 1000) {
    return formatAbbreviatedCurrency(parsed);
  }
  const sign = parsed < 0 ? "-" : "";
  return `${sign}$${Math.abs(parsed).toFixed(2)}`;
}

export function formatMetricRatio(value) {
  const parsed = toFiniteNumber(value);
  return parsed === null ? "—" : `${parsed.toFixed(2)}x`;
}

export function formatMetricPercent(value) {
  const parsed = toFiniteNumber(value);
  return parsed === null ? "—" : `${parsed.toFixed(1)}%`;
}

// For 0-1 probabilities (prob_profit, prob_big_hit, *_share fields).
export function formatMetricProbability(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) {
    return "—";
  }
  const normalized = Math.abs(parsed) <= 1 ? parsed * 100 : parsed;
  return `${normalized.toFixed(1)}%`;
}

export function formatMetricSignedPercent(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) {
    return "—";
  }
  return `${parsed >= 0 ? "+" : ""}${parsed.toFixed(1)}%`;
}

export function formatMetricNumber(value, decimals = 2) {
  const parsed = toFiniteNumber(value);
  return parsed === null ? "—" : parsed.toFixed(decimals);
}

export function formatMetricCount(value) {
  const parsed = toFiniteNumber(value);
  return parsed === null ? "—" : Math.round(parsed).toLocaleString("en-US");
}

// "Chance to profit" verdict card sub-label: percentage → odds phrasing.
// N = round(100 / pct); guards zero/negative/unusable chances (and a
// degenerate N < 2, where odds phrasing reads as noise) by returning null so
// the caller can omit the line entirely.
export function formatOddsFromPercent(percent) {
  const parsed = toFiniteNumber(percent);
  if (parsed === null || parsed <= 0) {
    return null;
  }
  const odds = Math.round(100 / parsed);
  if (!Number.isFinite(odds) || odds < 2) {
    return null;
  }
  return `1 in ${odds.toLocaleString("en-US")} packs`;
}

// ─── Percentile strip (log scale) ────────────────────────────────────────────

// Position of a value on a log10 axis, clamped to [0, 1].
export function getLogScalePosition(value, domainMin, domainMax) {
  const parsed = toFiniteNumber(value);
  const lo = toFiniteNumber(domainMin);
  const hi = toFiniteNumber(domainMax);
  if (parsed === null || lo === null || hi === null || lo <= 0 || hi <= lo) {
    return null;
  }
  const clamped = Math.min(Math.max(parsed, lo), hi);
  return (Math.log10(clamped) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo));
}

// Build everything the strip renders from live values. Major markers carry
// staggered labels (alternating above/below the baseline in position order);
// minor markers (P25/P75 band edges, P90) are hover/focus-only so the strip
// replaces the old 9-row table without losing any percentile.
export function buildPercentileStripModel({
  min = null,
  p5 = null,
  p25 = null,
  p50 = null,
  p75 = null,
  p90 = null,
  p95 = null,
  p99 = null,
  max = null,
  packCost = null,
} = {}) {
  const entries = [
    { key: "min", label: "Min", value: toFiniteNumber(min), major: true },
    { key: "p5", label: "P5", value: toFiniteNumber(p5), major: true },
    { key: "p25", label: "P25", value: toFiniteNumber(p25), major: false },
    { key: "p50", label: "P50", value: toFiniteNumber(p50), major: true },
    { key: "p75", label: "P75", value: toFiniteNumber(p75), major: false },
    { key: "p90", label: "P90", value: toFiniteNumber(p90), major: false },
    { key: "p95", label: "P95", value: toFiniteNumber(p95), major: true },
    { key: "p99", label: "P99", value: toFiniteNumber(p99), major: true },
    { key: "max", label: "Max", value: toFiniteNumber(max), major: true },
  ];
  const cost = toFiniteNumber(packCost);

  const positiveValues = entries
    .map((entry) => entry.value)
    .concat(cost === null ? [] : [cost])
    .filter((value) => value !== null && value > 0);
  if (positiveValues.length < 2) {
    return null;
  }

  // Log axis needs a strictly positive domain; a $0 floor clamps to the
  // domain minimum instead of collapsing the scale.
  const smallestPositive = Math.min(...positiveValues);
  const largestPositive = Math.max(...positiveValues);
  const domainMin = Math.max(smallestPositive * 0.85, 0.05);
  const domainMax = largestPositive * 1.12;
  if (domainMax <= domainMin) {
    return null;
  }

  const markers = entries
    .filter((entry) => entry.value !== null)
    .map((entry) => ({
      ...entry,
      position: getLogScalePosition(Math.max(entry.value, domainMin), domainMin, domainMax),
      aboveCost: cost !== null && entry.value >= cost,
    }))
    .filter((entry) => entry.position !== null)
    .sort((left, right) => left.position - right.position);

  // Stagger major labels above/below the baseline in position order so
  // neighbors never collide.
  let side = "above";
  for (const marker of markers) {
    if (!marker.major) {
      continue;
    }
    marker.labelSide = side;
    side = side === "above" ? "below" : "above";
  }

  const bandFrom = toFiniteNumber(p25);
  const bandTo = toFiniteNumber(p75);
  const band =
    bandFrom !== null && bandTo !== null && bandTo >= bandFrom
      ? {
          from: bandFrom,
          to: bandTo,
          fromPosition: getLogScalePosition(Math.max(bandFrom, domainMin), domainMin, domainMax),
          toPosition: getLogScalePosition(Math.max(bandTo, domainMin), domainMin, domainMax),
          belowCost: cost !== null && bandTo < cost,
        }
      : null;

  return {
    domainMin,
    domainMax,
    markers,
    band,
    cost:
      cost !== null
        ? { value: cost, position: getLogScalePosition(Math.max(cost, domainMin), domainMin, domainMax) }
        : null,
  };
}

// One-sentence computed takeaway under the strip — phrased from live values,
// never hardcoded numbers. probProfitPercent is the 0-100 chance to beat cost.
export function buildPercentileTakeaway({ p50 = null, p95 = null, packCost = null, probProfitPercent = null } = {}) {
  const median = toFiniteNumber(p50);
  const upper = toFiniteNumber(p95);
  const cost = toFiniteNumber(packCost);
  const chance = toFiniteNumber(probProfitPercent);
  if (cost === null) {
    return null;
  }
  if (median !== null && median >= cost) {
    return "The median pack opens at or above cost — more than half of simulated packs beat the pack price.";
  }
  if (upper !== null && upper < cost && chance !== null) {
    return `P95 of packs open below cost — profit is concentrated in the top ${formatMetricPercent(chance)} of outcomes.`;
  }
  if (chance !== null) {
    return `Most packs open below cost — roughly ${formatMetricPercent(chance)} of simulated packs beat the pack price.`;
  }
  return null;
}

// ─── Expert judgment tags ────────────────────────────────────────────────────
// Named thresholds so they are tunable in one place.
// Coefficient of Variation: < LOW_MAX "low", LOW_MAX..HIGH_MAX "high", above "extreme".
export const COEFFICIENT_OF_VARIATION_TAG_THRESHOLDS = { LOW_MAX: 1, HIGH_MAX: 3 };
// HHI EV Concentration: < DIFFUSE_MAX "diffuse", DIFFUSE_MAX..MODERATE_MAX "moderate", above "concentrated".
export const HHI_CONCENTRATION_TAG_THRESHOLDS = { DIFFUSE_MAX: 0.1, MODERATE_MAX: 0.25 };

export function getCoefficientOfVariationTag(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) {
    return null;
  }
  if (parsed < COEFFICIENT_OF_VARIATION_TAG_THRESHOLDS.LOW_MAX) {
    return { label: "low", tone: "success" };
  }
  if (parsed <= COEFFICIENT_OF_VARIATION_TAG_THRESHOLDS.HIGH_MAX) {
    return { label: "high", tone: "warning" };
  }
  return { label: "extreme", tone: "danger" };
}

export function getHhiConcentrationTag(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) {
    return null;
  }
  if (parsed < HHI_CONCENTRATION_TAG_THRESHOLDS.DIFFUSE_MAX) {
    return { label: "diffuse", tone: "success" };
  }
  if (parsed <= HHI_CONCENTRATION_TAG_THRESHOLDS.MODERATE_MAX) {
    return { label: "moderate", tone: "neutral" };
  }
  return { label: "concentrated", tone: "danger" };
}

// Loss Fraction (Avg) and (Typical) collapse into one row when they are equal
// after display rounding.
export function shouldMergeLossFractionRows(averageFraction, typicalFraction) {
  const averageText = formatMetricPercent(averageFraction);
  const typicalText = formatMetricPercent(typicalFraction);
  return averageText !== "—" && averageText === typicalText;
}
