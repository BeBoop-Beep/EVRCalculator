import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
// RipStatisticsPageClient.jsx has mixed CRLF/LF endings; normalise before any
// multi-line anchor.
const source = fs
  .readFileSync(path.resolve(here, "MarketSparkline.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

const sparkline = source;

test("the sparkline listens on pointer events, not mouse-only events", () => {
  assert.ok(sparkline.includes("function MarketSparkline"), "MarketSparkline must be locatable");
  assert.ok(sparkline.includes("onPointerDown="));
  assert.ok(sparkline.includes("onPointerMove={handlePointerMove}"));
  assert.ok(sparkline.includes("onPointerUp={handlePointerUp}"));
  assert.ok(sparkline.includes("onPointerCancel="), "a cancelled gesture must drop its tracking state");
  assert.ok(!sparkline.includes("onMouseMove="), "the mouse-only handler is replaced");
  assert.ok(!sparkline.includes("onMouseLeave="), "the mouse-only handler is replaced");
});

test("vertical page scrolling is handed back to the browser", () => {
  assert.ok(sparkline.includes("touch-pan-y"), "touch-action: pan-y keeps vertical scroll native");
});

test("desktop hover is untouched", () => {
  // The mouse branch selects on move exactly as before and still clears on leave.
  assert.ok(sparkline.includes('event.pointerType === "mouse"'));
  assert.ok(sparkline.includes('pointerMode !== POINTER_MODE_COARSE'));
});

test("a touch selection survives the finger leaving the screen", () => {
  assert.ok(sparkline.includes('if (event.pointerType === "mouse" || pointerMode !== POINTER_MODE_COARSE) clearSelection()'));
});

test("keyboard inspection is preserved and extended", () => {
  assert.ok(sparkline.includes("tabIndex={0}"));
  assert.ok(sparkline.includes('event.key === "ArrowRight"'));
  assert.ok(sparkline.includes('event.key === "Escape"'));
});

test("the first and final points stay reachable by every input", () => {
  // findNearestPointIndex clamps the ratio, and its own unit test proves ratio
  // 0 and 1 hit the ends. This locks the component to that selector rather than
  // to a hand-rolled index calculation that could drift.
  assert.ok(sparkline.includes("findNearestPointIndex(numericPoints, chartPoints.length, ratio)"));
  assert.ok(
    !/Math\.round\(Math\.max\(0, Math\.min\(1, ratio\)\)/.test(sparkline),
    "the inline index maths must be gone so there is one selection rule"
  );
});

test("edge tooltips are clamped against the viewport, not the chart", () => {
  assert.ok(sparkline.includes("clampTooltipX({"), "the shared clamp is used");
  assert.ok(sparkline.includes("viewportWidth: typeof window === \"undefined\" ? bounds.width : window.innerWidth"));
  assert.ok(!sparkline.includes("const getLocalTooltipX ="), "the old chart-relative clamp is gone");
});

test("no synthetic mouse events are dispatched", () => {
  assert.ok(!sparkline.includes("new MouseEvent"), "hover must not be simulated");
  assert.ok(!sparkline.includes("dispatchEvent"), "hover must not be simulated");
});
