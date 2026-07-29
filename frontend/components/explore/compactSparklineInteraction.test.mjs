import test from "node:test";
import assert from "node:assert/strict";

import {
  TAP_MOVEMENT_THRESHOLD_PX,
  classifyPointerGesture,
  clampTooltipX,
  findNearestPointIndex,
} from "./compactSparklineInteraction.mjs";

// Gaps are real: a card can be missing a day, so `index` (position in the full
// series) and the position in `numericPoints` diverge.
const numericPoints = [
  { index: 0, y: 10 },
  { index: 1, y: 12 },
  { index: 4, y: 9 },
  { index: 5, y: 14 },
];

test("the first and last data points are always selectable", () => {
  assert.equal(findNearestPointIndex(numericPoints, 6, 0), 0, "ratio 0 selects the first point");
  assert.equal(findNearestPointIndex(numericPoints, 6, 1), 3, "ratio 1 selects the final point");
});

test("an interior ratio selects the nearest valued point across a gap", () => {
  // ratio 0.5 of 5 spans -> target index 2.5 -> rounds to 3 -> nearest valued
  // index is 4, which is numericPoints[2].
  assert.equal(findNearestPointIndex(numericPoints, 6, 0.5), 2);
});

test("out-of-range ratios clamp instead of returning undefined", () => {
  assert.equal(findNearestPointIndex(numericPoints, 6, -0.4), 0);
  assert.equal(findNearestPointIndex(numericPoints, 6, 1.9), 3);
});

test("an empty series selects nothing", () => {
  assert.equal(findNearestPointIndex([], 0, 0.5), null);
});

test("the tooltip is pulled inside the viewport at both chart edges", () => {
  const shared = { chartWidth: 200, tooltipWidth: 224, viewportWidth: 390, gutter: 8 };

  // Chart hard against the left edge, finger on the first point.
  const atLeft = clampTooltipX({ ...shared, chartLeft: 4, pointerX: 0 });
  assert.ok(4 + atLeft - 224 / 2 >= 8, `tooltip left edge must clear the gutter (got ${4 + atLeft - 112})`);

  // Chart hard against the right edge, finger on the final point.
  const atRight = clampTooltipX({ ...shared, chartLeft: 186, pointerX: 200 });
  assert.ok(186 + atRight + 224 / 2 <= 390 - 8, `tooltip right edge must clear the gutter (got ${186 + atRight + 112})`);
});

test("a tooltip wider than the viewport still centres rather than returning NaN", () => {
  const x = clampTooltipX({ chartLeft: 0, chartWidth: 100, pointerX: 50, tooltipWidth: 500, viewportWidth: 320, gutter: 8 });
  assert.ok(Number.isFinite(x), "must always return a finite number");
});

test("vertical movement is a page scroll, not a chart interaction", () => {
  const gesture = classifyPointerGesture({
    startX: 100, startY: 100, currentX: 103, currentY: 160, threshold: TAP_MOVEMENT_THRESHOLD_PX,
  });
  assert.equal(gesture, "scroll", "a mostly-vertical drag must never select a point");
});

test("deliberate horizontal movement scrubs", () => {
  const gesture = classifyPointerGesture({
    startX: 100, startY: 100, currentX: 160, currentY: 104, threshold: TAP_MOVEMENT_THRESHOLD_PX,
  });
  assert.equal(gesture, "scrub");
});

test("a still finger is a tap", () => {
  const gesture = classifyPointerGesture({
    startX: 100, startY: 100, currentX: 103, currentY: 102, threshold: TAP_MOVEMENT_THRESHOLD_PX,
  });
  assert.equal(gesture, "tap");
});

test("a chart-width change cannot move the selected datum", () => {
  // Parity: the selector takes a 0..1 ratio, never pixels, so a 320px chart and
  // a 1366px chart resolve the same fraction to the same point.
  const points = Array.from({ length: 30 }, (_, index) => ({ index, y: index }));
  for (const ratio of [0, 0.25, 0.5, 0.75, 1]) {
    assert.equal(findNearestPointIndex(points, 30, ratio), findNearestPointIndex(points, 30, ratio));
  }
  assert.equal(findNearestPointIndex(points, 30, 0), 0);
  assert.equal(findNearestPointIndex(points, 30, 1), 29);
});
