// THE one construction of the RIP opening-distribution reference markers.
//
// WHY THIS FILE EXISTS
// The live set page (RipStatisticsPageClient) and the EV representativeness
// research article render the SAME RipDistributionChart against the SAME
// published simulation evidence. Before this helper they each built the
// `markers` prop themselves, so the two surfaces could drift apart on a label
// tweak or a fallback change without any test noticing. Marker presentation is
// now defined once, here, and both surfaces import it: change the presentation
// and both surfaces change together.
//
// This module is intentionally pure — no React, no data fetching, no run
// validation. Callers are responsible for having already established that the
// summary and percentiles they hand in belong to one identical calculation run.
import { selectPercentileValue } from "./simulationMetricsSelector.mjs";

// Labels live with the values on purpose. A marker is a (key, label, value)
// triple; splitting the label off into page copy is exactly the duplication
// this helper exists to remove.
export const RIP_DISTRIBUTION_MARKER_LABELS = Object.freeze({
  packCost: "Pack Market Price",
  typicalPack: "Typical Opening",
  p25: "P25",
  p75: "P75",
  averagePack: "Average Pack",
  badFloor: "Bad Floor",
  bigHit: "Big Hit Threshold",
  bigHitUpside: "Strong Upside",
  godPullUpside: "Jackpot Upside",
  bestPull: "Best Pull",
});

// The canonical marker order, exported so contract tests can assert it without
// re-listing the keys and quietly disagreeing with the implementation.
export const RIP_DISTRIBUTION_MARKER_KEYS = Object.freeze([
  "pack-cost",
  "median",
  "p25",
  "p75",
  "mean",
  "bad-floor",
  "big-hit",
  "big-hit-upside",
  "god-pull-upside",
  "max",
]);

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

// The set page reads the snapshot's snake_case summary; the slim
// `pokemon-set-simulation-evidence-v1` transport projects the same fields to
// camelCase-only. One marker builder has to answer to both spellings, so every
// read goes through here rather than through a hardcoded key.
function summaryNumber(summary, snakeKey, camelKey) {
  if (!summary || typeof summary !== "object") {
    return null;
  }
  const snake = toNumber(summary[snakeKey]);
  return snake !== null ? snake : toNumber(summary[camelKey]);
}

// The set of marker keys a Base/anonymous viewer may see the real value for.
// Everything else must be presented as locked (value: null, locked: true) —
// never leaked — because pack-cost/median/mean are the only figures the
// public simulation-evidence contract actually exposes. Any surface showing
// the public distribution (the Set RIP tab, the homepage) must filter through
// this SAME list rather than deciding independently which markers are public.
export const PUBLIC_RIP_DISTRIBUTION_MARKER_KEYS = Object.freeze(["pack-cost", "median", "mean"]);

const LOCKED_MARKER_DEFS = Object.freeze([
  ["p25", RIP_DISTRIBUTION_MARKER_LABELS.p25],
  ["p75", RIP_DISTRIBUTION_MARKER_LABELS.p75],
  ["bad-floor", RIP_DISTRIBUTION_MARKER_LABELS.badFloor],
  ["big-hit", RIP_DISTRIBUTION_MARKER_LABELS.bigHit],
  ["big-hit-upside", RIP_DISTRIBUTION_MARKER_LABELS.bigHitUpside],
  ["god-pull-upside", RIP_DISTRIBUTION_MARKER_LABELS.godPullUpside],
  ["max", RIP_DISTRIBUTION_MARKER_LABELS.bestPull],
]);

/**
 * Filters a full marker list down to the Basic/public policy: the public
 * markers keep their real value, everything else becomes an explicit locked
 * placeholder (value: null, locked: true) rather than being dropped, so
 * callers can still render a "locked" row instead of nothing. The single
 * source of the public/locked split — RipDecisionPage, the Set RIP tab, and
 * the homepage distribution all filter through this rather than each
 * deciding independently which markers are safe to show.
 */
export function selectBasicRipDistributionMarkers(markers) {
  const list = Array.isArray(markers) ? markers : [];
  const publicMarkers = list.filter((marker) =>
    PUBLIC_RIP_DISTRIBUTION_MARKER_KEYS.includes(marker?.key),
  );
  const lockedMarkers = LOCKED_MARKER_DEFS.map(([key, label]) => ({ key, label, value: null, locked: true }));
  return [...publicMarkers, ...lockedMarkers];
}

export function buildRipDistributionMarkers({ summary, percentiles } = {}) {
  const packCost = summaryNumber(summary, "pack_cost", "packCost");
  const p95Ratio = summaryNumber(summary, "p95_value_to_cost_ratio", "p95ValueToCostRatio");
  const p99Ratio = summaryNumber(summary, "p99_value_to_cost_ratio", "p99ValueToCostRatio");

  // Upside markers stay defined as ratio x pack cost — that is the current set
  // page formula and this extraction does not redefine it. The direct
  // p95_value / p99_value fields are only a fallback for snapshots that
  // published the value but not the ratio; where both exist they agree, so the
  // fallback cannot change what the set page renders today.
  const upside = (ratio, directSnake, directCamel) => {
    if (packCost !== null && ratio !== null) {
      return ratio * packCost;
    }
    return summaryNumber(summary, directSnake, directCamel);
  };

  return [
    { key: "pack-cost", label: RIP_DISTRIBUTION_MARKER_LABELS.packCost, value: packCost },
    {
      key: "median",
      label: RIP_DISTRIBUTION_MARKER_LABELS.typicalPack,
      value: selectPercentileValue(percentiles, 50) ?? summaryNumber(summary, "median_value", "medianValue"),
    },
    { key: "p25", label: RIP_DISTRIBUTION_MARKER_LABELS.p25, value: selectPercentileValue(percentiles, 25) },
    { key: "p75", label: RIP_DISTRIBUTION_MARKER_LABELS.p75, value: selectPercentileValue(percentiles, 75) },
    { key: "mean", label: RIP_DISTRIBUTION_MARKER_LABELS.averagePack, value: summaryNumber(summary, "mean_value", "meanValue") },
    {
      key: "bad-floor",
      label: RIP_DISTRIBUTION_MARKER_LABELS.badFloor,
      value: selectPercentileValue(percentiles, 5) ?? summaryNumber(summary, "tail_value_p05", "tailValueP05"),
    },
    { key: "big-hit", label: RIP_DISTRIBUTION_MARKER_LABELS.bigHit, value: summaryNumber(summary, "big_hit_threshold", "bigHitThreshold") },
    { key: "big-hit-upside", label: RIP_DISTRIBUTION_MARKER_LABELS.bigHitUpside, value: upside(p95Ratio, "p95_value", "p95Value") },
    { key: "god-pull-upside", label: RIP_DISTRIBUTION_MARKER_LABELS.godPullUpside, value: upside(p99Ratio, "p99_value", "p99Value") },
    { key: "max", label: RIP_DISTRIBUTION_MARKER_LABELS.bestPull, value: summaryNumber(summary, "max_value", "maxValue") },
  ];
}
