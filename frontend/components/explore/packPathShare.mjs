// Pure, framework-free share/percentage formatting for the Simulation Results
// → Pack Paths donut. ONE adaptive formatter keeps every renderer (donut
// center, legend, tooltip, and the Dominant/Special path chips) on a single
// rounding rule, so a rare path like a 1-in-2,000 God Pack (0.0464%) never
// collapses to "0.0%" and a 99.9536% Normal share never rounds up to a
// misleading "100.0%".
//
// Input contract: `formatPackPathShare` takes a RATIO in [0, 1] (count / total),
// NOT a 0-100 percentage. Renderers that hold raw counts should prefer
// `formatShareFromCounts(count, total)` so they never have to divide (and
// mis-scale) themselves.

// Any path whose share is below this ratio is treated as a "micro" slice for
// the donut's padding/stroke/marker decisions. Shared so the renderer and the
// formatter agree on what "sub-pixel rare" means.
export const RARE_PATH_VISIBILITY_RATIO = 0.005; // 0.5%

function toFiniteNumber(value) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

// Adaptive percentage for a ratio in [0, 1]. Decimal precision is driven by the
// distance to whichever edge (0% or 100%) is nearer, so a tiny share AND a tiny
// remainder-from-100% both keep enough digits to read as non-trivial:
//   0            -> "0.0%"
//   1            -> "100.0%"
//   0.0464%..99% -> 1 decimal where sufficient
//   0.001..0.01  -> 2 decimals   (0.1%..1%)
//   0.0001..0.001-> 3 decimals   (0.01%..0.1%)
//   0 < r, sub-precision -> "<0.01%" (or ">99.99%" near the top edge)
export function formatPackPathShare(ratio) {
  const r = toFiniteNumber(ratio);
  if (r === null || r <= 0) {
    return "0.0%";
  }
  if (r >= 1) {
    return "100.0%";
  }

  const pct = r * 100; // e.g. 0.0464
  const remainderPct = (1 - r) * 100; // distance from 100%, e.g. 0.0464 for 99.9536%
  const edge = Math.min(pct, remainderPct);

  let decimals;
  if (edge >= 1) {
    decimals = 1;
  } else if (edge >= 0.1) {
    decimals = 2;
  } else if (edge >= 0.01) {
    decimals = 3;
  } else {
    // Smaller than 3-decimal display precision: keep the reader honest about
    // which edge we are hugging rather than rounding to a false 0% / 100%.
    return pct < remainderPct ? "<0.01%" : ">99.99%";
  }

  return `${pct.toFixed(decimals)}%`;
}

// Convenience for renderers that hold raw pack counts. Guards a zero/absent
// total to "0.0%" (matching the donut's empty-state expectations).
export function formatShareFromCounts(count, total) {
  const c = toFiniteNumber(count);
  const t = toFiniteNumber(total);
  if (c === null || t === null || t <= 0) {
    return "0.0%";
  }
  return formatPackPathShare(c / t);
}

// Implied odds line for the tooltip, e.g. "About 1 in 2,155 packs". Only
// meaningful when both count and total are positive — returns null otherwise so
// callers can omit it entirely for zero-count paths. Also omitted for a
// dominant path where the odds round to "1 in 1", which reads as noise.
export function formatImpliedOdds(count, total) {
  const c = toFiniteNumber(count);
  const t = toFiniteNumber(total);
  if (c === null || t === null || c <= 0 || t <= 0) {
    return null;
  }
  const odds = Math.round(t / c);
  if (odds < 2) {
    return null;
  }
  return `About 1 in ${odds.toLocaleString("en-US")} packs`;
}

// True when a path share is nonzero but below the visibility threshold, i.e. it
// needs a rare-path marker instead of relying on its (sub-pixel) true wedge.
export function isRarePathShare(ratio) {
  const r = toFiniteNumber(ratio);
  return r !== null && r > 0 && r < RARE_PATH_VISIBILITY_RATIO;
}

// Display-only slice weights for the Pack Paths donut.
//
// Product decision: the donut is NOT required to be visually proportional. Its
// job is to make the *existence* of each pack path recognizable. An extremely
// rare nonzero special path (e.g. a 0.0464% God Pack) has a sub-pixel true
// wedge, so `buildPackPathDisplayRows` rescales ONLY the drawn slice weights so
// every nonzero special path occupies a recognizable share of the ring (~7%,
// within the 5-10% band). Real counts and real percentages are left untouched on
// each row, so the legend/tooltip/center/chips stay truthful — only the Pie's
// `dataKey="displayWeight"` reads these rescaled weights.
export const SPECIAL_PATH_MIN_DISPLAY_SHARE = 0.07; // ~7%, mid 5-10% band
const SPECIAL_PATH_MAX_TOTAL_DISPLAY_SHARE = 0.9; // keep non-special paths a visible majority

export function buildPackPathDisplayRows(rows = []) {
  const list = Array.isArray(rows) ? rows : [];
  const entries = list.map((row) => ({
    row,
    count: Math.max(0, toFiniteNumber(row?.count) ?? 0),
    isSpecial: Boolean(row?.isSpecial),
    displayShare: 0,
  }));
  const totalCount = entries.reduce((sum, entry) => sum + entry.count, 0);

  if (totalCount <= 0) {
    // No usable counts — nothing to draw; every weight is zero.
    return list.map((row) => ({ ...row, displayWeight: 0 }));
  }

  // Boost each nonzero special path up to at least the target visual share.
  let specialShareSum = 0;
  for (const entry of entries) {
    if (entry.count > 0 && entry.isSpecial) {
      entry.displayShare = Math.max(entry.count / totalCount, SPECIAL_PATH_MIN_DISPLAY_SHARE);
      specialShareSum += entry.displayShare;
    }
  }

  // Never let boosted special paths crowd out the non-special majority.
  if (specialShareSum > SPECIAL_PATH_MAX_TOTAL_DISPLAY_SHARE) {
    const scale = SPECIAL_PATH_MAX_TOTAL_DISPLAY_SHARE / specialShareSum;
    for (const entry of entries) {
      if (entry.count > 0 && entry.isSpecial) {
        entry.displayShare *= scale;
      }
    }
    specialShareSum = SPECIAL_PATH_MAX_TOTAL_DISPLAY_SHARE;
  }

  const nonSpecialCount = entries.reduce(
    (sum, entry) => sum + (!entry.isSpecial && entry.count > 0 ? entry.count : 0),
    0
  );

  if (nonSpecialCount <= 0) {
    // No non-special path to hold the remainder — normalize specials to fill
    // the ring so the drawn slices still sum to the full circle.
    const sum = specialShareSum || 1;
    for (const entry of entries) {
      if (entry.count > 0 && entry.isSpecial) {
        entry.displayShare /= sum;
      }
    }
  } else {
    // Non-special nonzero paths split whatever display share remains, in
    // proportion to their real counts.
    const remaining = Math.max(0, 1 - specialShareSum);
    for (const entry of entries) {
      if (entry.count > 0 && !entry.isSpecial) {
        entry.displayShare = (entry.count / nonSpecialCount) * remaining;
      }
    }
  }

  return entries.map((entry) => ({
    ...entry.row,
    displayWeight: entry.count > 0 ? entry.displayShare : 0,
  }));
}
