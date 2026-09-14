import test from "node:test";
import assert from "node:assert/strict";
import { positionMarketPerformanceTooltip } from "./marketPerformanceTooltipPosition.mjs";

const chart = { left: 100, top: 80, right: 700, bottom: 380, width: 600, height: 300 };
const base = { chartBounds: chart, tooltipWidth: 220, tooltipHeight: 110, viewportWidth: 900, viewportHeight: 600 };

function contained(result, bounds = chart, gutter = 10) {
  assert.ok(result.left >= bounds.left + gutter - 0.001);
  assert.ok(result.left + result.width <= bounds.right - gutter + 0.001);
  assert.ok(result.top >= bounds.top + gutter - 0.001);
  assert.ok(result.top + Math.min(result.maxHeight, 110) <= bounds.bottom - gutter + 0.001);
}

test("left and right crosshairs choose the open side", () => {
  const left = positionMarketPerformanceTooltip({ ...base, crosshairX: 70, pointerY: 240 });
  const right = positionMarketPerformanceTooltip({ ...base, crosshairX: 530, pointerY: 240 });
  assert.equal(left.horizontalPlacement, "right");
  assert.equal(right.horizontalPlacement, "left");
  assert.ok(left.left > chart.left + 70);
  assert.ok(right.left + right.width < chart.left + 530);
  contained(left);
  contained(right);
});

test("pointer vertical placement flips and clamps inside the plot", () => {
  const nearTop = positionMarketPerformanceTooltip({ ...base, crosshairX: 300, pointerY: 90 });
  const middle = positionMarketPerformanceTooltip({ ...base, crosshairX: 300, pointerY: 245 });
  const nearBottom = positionMarketPerformanceTooltip({ ...base, crosshairX: 300, pointerY: 370 });
  assert.equal(nearTop.verticalPlacement, "below");
  assert.equal(middle.verticalPlacement, "above");
  assert.equal(nearBottom.verticalPlacement, "above");
  for (const result of [nearTop, middle, nearBottom]) contained(result);
});

test("viewport edges further constrain chart-contained placement", () => {
  const edgeChart = { left: -20, top: -10, right: 330, bottom: 260, width: 350, height: 270 };
  const result = positionMarketPerformanceTooltip({
    chartBounds: edgeChart,
    crosshairX: 25,
    pointerY: 20,
    tooltipWidth: 240,
    tooltipHeight: 130,
    viewportWidth: 320,
    viewportHeight: 240,
  });
  assert.ok(result.left >= 10);
  assert.ok(result.left + result.width <= 310);
  assert.ok(result.top >= 10);
  assert.ok(result.top + Math.min(result.maxHeight, 130) <= 230);
});

test("narrow mobile and oversized dense tooltips remain bounded", () => {
  const mobile = { left: 8, top: 100, right: 382, bottom: 300, width: 374, height: 200 };
  const result = positionMarketPerformanceTooltip({
    chartBounds: mobile,
    crosshairX: 180,
    pointerY: 190,
    tooltipWidth: 500,
    tooltipHeight: 420,
    viewportWidth: 390,
    viewportHeight: 844,
  });
  assert.equal(result.width, 354);
  assert.equal(result.maxHeight, 180);
  assert.equal(result.top, 110);
  assert.ok(result.left >= 18 && result.left + result.width <= 372);
  assert.ok(result.top + result.maxHeight <= 290);
});

test("keyboard placement is stable and chart-contained on either side", () => {
  const left = positionMarketPerformanceTooltip({ ...base, interactionSource: "keyboard", crosshairX: 80 });
  const right = positionMarketPerformanceTooltip({ ...base, interactionSource: "keyboard", crosshairX: 520 });
  assert.equal(left.horizontalPlacement, "right");
  assert.equal(right.horizontalPlacement, "left");
  assert.equal(left.top, right.top);
  contained(left);
  contained(right);
});
