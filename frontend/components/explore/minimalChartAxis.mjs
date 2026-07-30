// Shared minimal-axis configuration for the set page's time-series charts.
//
// Set Value Trend and Opening Profit vs Cost now use ONE axis treatment at every
// width: no y-axis tick labels, no y-axis gutter, and an x-axis that carries
// only the first and last date of the visible series. This started as the
// below-1200px presentation; it reads more cleanly than the labelled version at
// every size, so it is now the shared direction rather than a mobile special
// case.
//
// Nothing here touches a scale, a domain, a value or a tooltip. The y domain is
// still computed by each chart from its own data and still passed to <YAxis>;
// only the printed labels and the width they reserved are gone, and exact
// values remain reachable through hover (mouse) and tap/scrub (touch).
//
// This module is deliberately data-free and dependency-free so both charts —
// and the Overview and Insights renderings of Opening Profit vs Cost — cannot
// drift into separately tuned versions.

/**
 * The first and last date in a series, as an explicit Recharts `ticks` array.
 * Returns a single entry when the series has one date (or when first and last
 * coincide), and undefined when there is nothing to place.
 */
export function buildEdgeDateTicks(rows, dateKey) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return undefined;
  }
  const first = rows[0]?.[dateKey];
  const last = rows[rows.length - 1]?.[dateKey];
  if (!first) {
    return undefined;
  }
  return last && last !== first ? [first, last] : [first];
}

/**
 * Y-axis props that hide the labels and reserve no horizontal gutter. Spread
 * these onto <YAxis>; each chart still supplies its own `domain`, and may still
 * supply `ticks`/`tickCount` to control gridline placement.
 */
export const MINIMAL_Y_AXIS_PROPS = Object.freeze({
  tick: false,
  width: 0,
  tickLine: false,
  axisLine: false,
});

/**
 * Horizontal plot insets. With the y-axis reserving no width, a zero left
 * margin puts the first data point exactly on x=0, where the SVG clips half of
 * its stroke (and all of its glow). These few pixels keep both line caps whole.
 * Edge date labels are handled separately by ChartEdgeDateTick, so this stays
 * far smaller than a label-sized gutter.
 *
 * `rightExtra` exists for charts that park inline end-of-series labels in the
 * right margin; it is added to, never substituted for, the shared inset.
 */
export function getMinimalPlotMargin({ top = 10, bottom = 6, rightExtra = 0 } = {}) {
  return {
    top,
    right: MINIMAL_PLOT_INSET_RIGHT + rightExtra,
    left: MINIMAL_PLOT_INSET_LEFT,
    bottom,
  };
}

export const MINIMAL_PLOT_INSET_LEFT = 6;
export const MINIMAL_PLOT_INSET_RIGHT = 8;
