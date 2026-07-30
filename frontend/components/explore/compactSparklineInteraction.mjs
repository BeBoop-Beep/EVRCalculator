// Pure geometry and gesture logic for CompactSparkline. Kept out of the
// component so it can be tested without a DOM — the frontend suite runs on
// node:test with react-test-renderer and has no jsdom.

// Below this much movement a touch is a tap, not a drag.
export const TAP_MOVEMENT_THRESHOLD_PX = 8;

// Takes a 0..1 ratio rather than pixels, so the same fraction of a 320px chart
// and a 1366px chart resolves to the same datum. Returns an index *into
// numericPoints*, which is not the same as the point's index in the full series
// once a day is missing.
export function findNearestPointIndex(numericPoints, chartPointCount, ratio) {
  if (!Array.isArray(numericPoints) || numericPoints.length === 0) {
    return null;
  }
  const clampedRatio = Math.max(0, Math.min(1, Number.isFinite(ratio) ? ratio : 0));
  const spans = Math.max((Number(chartPointCount) || numericPoints.length) - 1, 1);
  const targetIndex = Math.round(clampedRatio * spans);

  let nearestIndex = 0;
  let nearestDistance = Infinity;
  numericPoints.forEach((point, index) => {
    const distance = Math.abs(point.index - targetIndex);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = index;
    }
  });
  return nearestIndex;
}

// Returns a chart-local x (px from the chart's left edge) for a tooltip that is
// centred on that x via translateX(-50%). The result keeps the tooltip's own
// box inside the viewport, so a chart at either screen edge still reads.
export function clampTooltipX({ chartLeft, chartWidth, pointerX, tooltipWidth, viewportWidth, gutter = 8 }) {
  const width = Number(chartWidth) || 0;
  const half = (Number(tooltipWidth) || 0) / 2;
  const left = Number(chartLeft) || 0;
  const viewport = Number(viewportWidth) || 0;
  const rawX = Number.isFinite(pointerX) ? pointerX : width / 2;

  // Convert the viewport-space allowed range for the tooltip centre into
  // chart-local coordinates.
  const minCentre = gutter + half - left;
  const maxCentre = viewport - gutter - half - left;

  if (!(maxCentre > minCentre)) {
    // Tooltip is wider than the space available; centre it on the viewport.
    return viewport / 2 - left;
  }
  return Math.max(minCentre, Math.min(maxCentre, rawX));
}

export function classifyPointerGesture({ startX, startY, currentX, currentY, threshold = TAP_MOVEMENT_THRESHOLD_PX }) {
  const dx = Math.abs((Number(currentX) || 0) - (Number(startX) || 0));
  const dy = Math.abs((Number(currentY) || 0) - (Number(startY) || 0));
  if (dx <= threshold && dy <= threshold) {
    return "tap";
  }
  // Vertical intent belongs to the page, never to the chart.
  return dx > dy ? "scrub" : "scroll";
}
