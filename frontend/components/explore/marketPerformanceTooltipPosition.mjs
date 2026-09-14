const numberOr = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));

/**
 * Fixed-position tooltip geometry for the shared Market comparison chart.
 * Chart containment is primary; viewport edges further narrow the usable box.
 */
export function positionMarketPerformanceTooltip({
  chartBounds,
  crosshairX,
  pointerY = null,
  tooltipWidth,
  tooltipHeight,
  viewportWidth,
  viewportHeight,
  interactionSource = "pointer",
  gutter = 10,
  offset = 12,
}) {
  const chartLeft = numberOr(chartBounds?.left);
  const chartTop = numberOr(chartBounds?.top);
  const chartWidth = Math.max(0, numberOr(chartBounds?.width, numberOr(chartBounds?.right) - chartLeft));
  const chartHeight = Math.max(0, numberOr(chartBounds?.height, numberOr(chartBounds?.bottom) - chartTop));
  const chartRight = numberOr(chartBounds?.right, chartLeft + chartWidth);
  const chartBottom = numberOr(chartBounds?.bottom, chartTop + chartHeight);
  const viewportRight = Math.max(0, numberOr(viewportWidth, chartRight));
  const viewportBottom = Math.max(0, numberOr(viewportHeight, chartBottom));

  const minLeft = Math.max(chartLeft + gutter, gutter);
  const maxRight = Math.min(chartRight - gutter, viewportRight - gutter);
  const minTop = Math.max(chartTop + gutter, gutter);
  const maxBottom = Math.min(chartBottom - gutter, viewportBottom - gutter);
  const availableWidth = Math.max(1, maxRight - minLeft);
  const availableHeight = Math.max(1, maxBottom - minTop);
  const width = Math.min(Math.max(1, numberOr(tooltipWidth, 248)), availableWidth);
  const height = Math.min(Math.max(1, numberOr(tooltipHeight, 160)), availableHeight);
  const guideX = clamp(chartLeft + numberOr(crosshairX, chartWidth / 2), minLeft, maxRight);

  const rightLeft = guideX + offset;
  const leftLeft = guideX - offset - width;
  const preferRight = guideX <= chartLeft + chartWidth / 2;
  const rightFits = rightLeft + width <= maxRight;
  const leftFits = leftLeft >= minLeft;
  let horizontalPlacement = preferRight ? "right" : "left";
  let left = preferRight ? rightLeft : leftLeft;
  if (preferRight && !rightFits && leftFits) {
    horizontalPlacement = "left";
    left = leftLeft;
  } else if (!preferRight && !leftFits && rightFits) {
    horizontalPlacement = "right";
    left = rightLeft;
  }
  left = clamp(left, minLeft, Math.max(minLeft, maxRight - width));

  const anchorY = interactionSource === "keyboard"
    ? chartTop + chartHeight * 0.42
    : clamp(numberOr(pointerY, chartTop + chartHeight / 2), chartTop, chartBottom);
  const aboveTop = anchorY - offset - height;
  const belowTop = anchorY + offset;
  const aboveFits = aboveTop >= minTop;
  const belowFits = belowTop + height <= maxBottom;
  let verticalPlacement = "above";
  let top = aboveTop;
  if (!aboveFits && belowFits) {
    verticalPlacement = "below";
    top = belowTop;
  } else if (!aboveFits && !belowFits) {
    verticalPlacement = "clamped";
    top = clamp(aboveTop, minTop, Math.max(minTop, maxBottom - height));
  }
  top = clamp(top, minTop, Math.max(minTop, maxBottom - height));

  return { left, top, width, maxHeight: availableHeight, horizontalPlacement, verticalPlacement };
}
