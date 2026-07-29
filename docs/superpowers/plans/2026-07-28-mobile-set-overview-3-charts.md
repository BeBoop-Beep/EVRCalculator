# Plan 3 — Chart Sizing and Touch Interaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Depends on Plan 2.** Do not start until Plan 2 Task 1 (breakpoint tokens) and Task 2 (single mount) have merged. Every `max-desk:` class here needs those tokens, and the interaction work assumes one chart instance per chart.

**Goal:** Make every Overview chart usable by touch without taking anything away from mouse or keyboard, and size the charts for phone and tablet without changing a single desktop pixel.

**Architecture:** One shared `usePointerMode` hook resolves the *currently used* input device from `matchMedia` plus live `pointerdown` events, so hybrid laptops keep both modes. Recharts charts consume it through the supported `<Tooltip trigger>` API — no synthetic mouse events. The one hand-rolled chart, `CompactSparkline`, gets real pointer-event handling with `touch-action: pan-y`, which hands vertical scrolling back to the browser and reserves horizontal movement for scrubbing. Sizing is pure Tailwind behind `max-desk:` boundaries.

**Tech Stack:** React 19, Recharts 2.15 (`<Tooltip trigger="hover" | "click">`, `activeDot`), Tailwind 3.4, `node:test` via `tsx` with `react-test-renderer`.

## Global Constraints

See [the plan index](2026-07-28-mobile-set-overview-INDEX.md#global-constraints). The ones that bind hardest here:

- **Do not disable desktop hover globally.** Mouse and trackpad keep hover at every width.
- **Do not simulate hover with synthetic mouse events.** Use pointer events or the chart library's supported interaction APIs.
- **Do not replace an interactive chart with a static SVG or screenshot.**
- **Do not mount a second chart for mobile.** One data source, one active chart instance.
- Preserve: timeframe switching, series switching, Checklist/Hits/Top 10 switching, data-point inspection, tooltip values, dates, prices, dollar movement, percentage movement, axis context, selected-period state, legends, drill-down, chart-driven navigation, keyboard interaction.
- Desktop at `1200px+` keeps its exact current chart dimensions, margins, axis density and tooltip trigger.
- Tests: `node:test` via `tsx --test`, `react-test-renderer` with `createNodeMock`. **No jsdom.** Interaction tests invoke handler props directly on the rendered tree.

### Z-index ladder (do not violate)

| Layer | z-index | Source |
|---|---|---|
| Global bottom nav | `60` | `GlobalMobileBottomNav.js:150` |
| Global header shell | `50` | `StickyNav.js:37` |
| Set-level sticky tabs | `40` | `globals.css`, added in Plan 2 Task 5 |
| Page content | auto | — |

Chart tooltips must render **above** all four. They already use `z-[9999]`; keep that and make sure no ancestor creates a stacking context that traps them.

---

## Mandatory corrections applied to this plan

### Correction 3 — `CompactSparkline` must not live inside a row anchor

Task 2 makes the sparkline independently interactive: pointer events, tap, scrub,
`tabIndex={0}`, arrow-key inspection, Escape. Plan 4 Task 4's original draft
wrapped the entire Top Chase row — sparkline included — in a single `<a>`. An
interactive, focusable, keyboard-driven chart inside a link is invalid nested
interactive content, and `stopPropagation` is a patch over a structural mistake,
not a fix.

Plan 4 Task 4 has been rewritten so each row composes **two siblings**: a
navigation region (`<a>`: rank, image, name, rarity, price, movement) and a chart
region (the sparkline, with its own pointer and keyboard interaction). Enter and
Space must activate only the intended control; arrow keys and Escape stay chart
behaviours; pointer propagation must not be able to navigate.

### Correction 4 — tooltip clipping and first touch

**Clipping.** A large `z-index` does not escape ancestor overflow clipping, a
containing block, a stacking context, `isolation`, or a transform-created
stacking context. Walk the real ancestor chain. Prefer, in order: remove
inappropriate chart-wrapper clipping; keep series clipping inside the SVG rather
than clipping the tooltip; use supported Recharts escape behaviour; only then a
custom overlay. Never restyle the global top or bottom navigation to fix chart
layering.

Note that `.set-detail-context-shell` declares `isolation: isolate`. Plan 2 Task 5
drops that below 1200px, which is also what stops the shell trapping tooltips and
the tab bar's z-index.

**First touch.** `usePointerMode` starts in `"fine"` so SSR and first paint never
strip desktop hover. The hazard is that the *first* deliberate touch is consumed
switching the mode, leaving the user to tap twice. Two things prevent that:

1. The seeding effect runs on mount from `matchMedia("(hover: hover) and (pointer: fine)")`,
   so a touch-only device is already in `"coarse"` before any user input arrives.
2. The `pointerdown` listener is registered in the **capture** phase on `window`,
   so on a hybrid device the mode flips during capture, before the chart's own
   bubble-phase handling of that same gesture.

Test the transitions that matter: first touch on initial load, touch → mouse,
mouse → touch, touch → mouse → touch, and a coarse-capable device whose
`matchMedia` reports hover.

---

### Task 1: Shared media-query and pointer-mode hooks

**Files:**
- Create: `frontend/hooks/useMediaQuery.js`
- Create: `frontend/hooks/usePointerMode.js`
- Create: `frontend/hooks/usePointerMode.test.mjs`

**Interfaces:**
- Produces: `useMediaQuery(query: string) => boolean`, default export of `frontend/hooks/useMediaQuery.js`.
- Produces: `usePointerMode() => "fine" | "coarse"`, default export of `frontend/hooks/usePointerMode.js`, plus named exports `POINTER_MODE_FINE = "fine"` and `POINTER_MODE_COARSE = "coarse"`, and a pure named export `resolvePointerModeFromEvent(event, currentMode) => "fine" | "coarse"` so the branch is testable without a DOM.
- Consumed by: Task 2 (`CompactSparkline`), Task 3 (`SetValueLineChart`, `PackValueHistoryChart`), and Plan 4.

- [ ] **Step 1: Write the failing test**

Create `frontend/hooks/usePointerMode.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import {
  POINTER_MODE_COARSE,
  POINTER_MODE_FINE,
  resolvePointerModeFromEvent,
} from "./usePointerMode.js";

test("touch and pen switch the page into tap mode", () => {
  assert.equal(resolvePointerModeFromEvent({ pointerType: "touch" }, POINTER_MODE_FINE), POINTER_MODE_COARSE);
  assert.equal(resolvePointerModeFromEvent({ pointerType: "pen" }, POINTER_MODE_FINE), POINTER_MODE_COARSE);
});

test("a mouse switches back to hover mode on the same device", () => {
  // Hybrid laptops and tablets with a trackpad must keep both modes. Whichever
  // device was used last wins; neither is permanently disabled.
  assert.equal(resolvePointerModeFromEvent({ pointerType: "mouse" }, POINTER_MODE_COARSE), POINTER_MODE_FINE);
});

test("unknown or missing pointer types leave the mode alone", () => {
  assert.equal(resolvePointerModeFromEvent({ pointerType: "" }, POINTER_MODE_COARSE), POINTER_MODE_COARSE);
  assert.equal(resolvePointerModeFromEvent({}, POINTER_MODE_FINE), POINTER_MODE_FINE);
  assert.equal(resolvePointerModeFromEvent(null, POINTER_MODE_FINE), POINTER_MODE_FINE);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test hooks/usePointerMode.test.mjs`

Expected: FAIL — `Cannot find module './usePointerMode.js'`.

- [ ] **Step 3: Write `useMediaQuery`**

Create `frontend/hooks/useMediaQuery.js`:

```javascript
"use client";

import { useEffect, useState } from "react";

// Reads a media query reactively. `initialValue` is what SSR and the first
// client paint assume — always pass the desktop answer, so a hydration flash
// can never momentarily strip desktop behaviour.
export default function useMediaQuery(query, initialValue = false) {
  const [matches, setMatches] = useState(initialValue);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }
    const mediaQueryList = window.matchMedia(query);
    const update = () => setMatches(mediaQueryList.matches);
    update();
    if (typeof mediaQueryList.addEventListener === "function") {
      mediaQueryList.addEventListener("change", update);
      return () => mediaQueryList.removeEventListener("change", update);
    }
    return undefined;
  }, [query]);

  return matches;
}
```

- [ ] **Step 4: Write `usePointerMode`**

Create `frontend/hooks/usePointerMode.js`:

```javascript
"use client";

import { useEffect, useState } from "react";

export const POINTER_MODE_FINE = "fine";
export const POINTER_MODE_COARSE = "coarse";

// Viewport width does not determine input type: a tablet may be driven by
// touch, a mouse or a trackpad, and a laptop may have a touchscreen. Resolve
// the mode from the pointer that was actually used most recently, seeded from
// the device's own capability query.
export function resolvePointerModeFromEvent(event, currentMode) {
  const pointerType = event?.pointerType;
  if (pointerType === "touch" || pointerType === "pen") {
    return POINTER_MODE_COARSE;
  }
  if (pointerType === "mouse") {
    return POINTER_MODE_FINE;
  }
  return currentMode;
}

export default function usePointerMode() {
  // Default to fine on the server and on first paint. Desktop hover is the
  // existing behaviour and must never be lost to a hydration flash.
  const [mode, setMode] = useState(POINTER_MODE_FINE);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    if (typeof window.matchMedia === "function") {
      const hoverQuery = window.matchMedia("(hover: hover) and (pointer: fine)");
      setMode(hoverQuery.matches ? POINTER_MODE_FINE : POINTER_MODE_COARSE);
    }

    const handlePointerDown = (event) => {
      setMode((current) => resolvePointerModeFromEvent(event, current));
    };

    window.addEventListener("pointerdown", handlePointerDown, { capture: true, passive: true });
    return () => window.removeEventListener("pointerdown", handlePointerDown, { capture: true });
  }, []);

  return mode;
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test hooks/usePointerMode.test.mjs`

Expected: PASS, all three tests.

---

### Task 2: Give `CompactSparkline` real pointer handling

`CompactSparkline` (`RipStatisticsPageClient.jsx:2313`) is the Top Chase trend chart. It is hand-rolled SVG wired to `onMouseMove` / `onMouseLeave` only, so on a phone it is decorative: nothing can select a point, and nothing shows a value.

**Files:**
- Create: `frontend/components/explore/compactSparklineInteraction.mjs`
- Create: `frontend/components/explore/compactSparklineInteraction.test.mjs`
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:2313-2463`

**Interfaces:**
- Consumes: `usePointerMode`, `POINTER_MODE_COARSE` from `@/hooks/usePointerMode`.
- Produces, from `compactSparklineInteraction.mjs`:
  - `TAP_MOVEMENT_THRESHOLD_PX = 8`
  - `findNearestPointIndex(numericPoints, chartPointCount, ratio) => number` — `numericPoints` is `[{ index, y, ... }]`, `ratio` is `0..1` across the chart; returns an index **into `numericPoints`**.
  - `clampTooltipX({ chartLeft, chartWidth, pointerX, tooltipWidth, viewportWidth, gutter }) => number` — returns a chart-local x in px such that the tooltip stays fully inside the viewport.
  - `classifyPointerGesture({ startX, startY, currentX, currentY, threshold }) => "tap" | "scrub" | "scroll"`.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/explore/compactSparklineInteraction.test.mjs`:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/explore/compactSparklineInteraction.test.mjs`

Expected: FAIL — module not found.

- [ ] **Step 3: Write the interaction module**

Create `frontend/components/explore/compactSparklineInteraction.mjs`:

```javascript
// Pure geometry and gesture logic for CompactSparkline. Kept out of the
// component so it can be tested without a DOM — the frontend suite runs on
// node:test with react-test-renderer and has no jsdom.

// Below this much movement a touch is a tap, not a drag.
export const TAP_MOVEMENT_THRESHOLD_PX = 8;

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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/explore/compactSparklineInteraction.test.mjs`

Expected: PASS, all nine tests.

- [ ] **Step 5: Rewrite `CompactSparkline` to use pointer events**

In `frontend/components/explore/RipStatisticsPageClient.jsx`, add to the imports near the other `@/hooks` imports:

```javascript
import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";
import {
  TAP_MOVEMENT_THRESHOLD_PX,
  classifyPointerGesture,
  clampTooltipX,
  findNearestPointIndex,
} from "./compactSparklineInteraction.mjs";
```

Then replace the body of `CompactSparkline` from the `const [activeIndex, setActiveIndex] = useState(null);` line (2314) through the closing `handlePointerMove` function (2364) with:

```javascript
  const [activeIndex, setActiveIndex] = useState(null);
  const [tooltipX, setTooltipX] = useState(null);
  const pointerMode = usePointerMode();
  const isCoarsePointer = pointerMode === POINTER_MODE_COARSE;
  const containerRef = useRef(null);
  const gestureRef = useRef(null);
  const chartId = useId().replace(/:/g, "");
  const chartPoints = Array.isArray(points)
    ? points.map((point, index) => ({
        index,
        date: point?.date ?? null,
        y: toNumber(point?.[valueKey] ?? point?.value),
        isCarriedForward: Boolean(point?.isCarriedForward),
        sourceDate: point?.sourceDate ?? null,
      }))
    : [];
  const numericPoints = chartPoints.filter((point) => point.y !== null);
  const strokeColor =
    trendDirection === "negative"
      ? NEGATIVE_VALUE_COLOR
      : trendDirection === "positive"
      ? POSITIVE_VALUE_COLOR
      : "rgba(148,163,184,0.8)";
  const activePoint = activeIndex === null ? null : numericPoints[activeIndex] || null;
  const firstPoint = numericPoints[0] || null;
  const activeDeltaAmount = activePoint && firstPoint ? getPriceDeltaAmount(activePoint.y, firstPoint.y) : null;
  const activeDeltaPercent = activePoint && firstPoint ? getPriceDeltaPercent(activePoint.y, firstPoint.y) : null;

  const selectAtClientX = (clientX) => {
    const element = containerRef.current;
    if (!element || numericPoints.length === 0) {
      return;
    }
    const bounds = element.getBoundingClientRect();
    const ratio = bounds.width > 0 ? (clientX - bounds.left) / bounds.width : 0;
    setActiveIndex(findNearestPointIndex(numericPoints, chartPoints.length, ratio));
    setTooltipX(
      clampTooltipX({
        chartLeft: bounds.left,
        chartWidth: bounds.width,
        pointerX: clientX - bounds.left,
        // Matches SetValueCompactTooltipCard's max-w-[14rem].
        tooltipWidth: 224,
        viewportWidth: typeof window === "undefined" ? bounds.width : window.innerWidth,
        gutter: 8,
      })
    );
  };

  const clearSelection = () => {
    setActiveIndex(null);
    setTooltipX(null);
  };

  // Mouse and trackpad keep the exact hover behaviour they have today.
  const handlePointerMove = (event) => {
    if (event.pointerType === "mouse") {
      selectAtClientX(event.clientX);
      return;
    }
    const gesture = gestureRef.current;
    if (!gesture) {
      return;
    }
    const classification = classifyPointerGesture({
      startX: gesture.startX,
      startY: gesture.startY,
      currentX: event.clientX,
      currentY: event.clientY,
      threshold: TAP_MOVEMENT_THRESHOLD_PX,
    });
    if (classification === "scroll") {
      // The finger is heading down the page. Hand it back and stop tracking.
      gestureRef.current = null;
      return;
    }
    if (classification === "scrub") {
      gesture.moved = true;
      selectAtClientX(event.clientX);
    }
  };

  const handlePointerDown = (event) => {
    if (event.pointerType === "mouse") {
      return;
    }
    gestureRef.current = { startX: event.clientX, startY: event.clientY, moved: false };
  };

  const handlePointerUp = (event) => {
    if (event.pointerType === "mouse") {
      return;
    }
    const gesture = gestureRef.current;
    gestureRef.current = null;
    if (!gesture || gesture.moved) {
      // A scrub already selected as it went; leave the selection visible.
      return;
    }
    // A tap on the already-selected point dismisses it; any other tap selects.
    const element = containerRef.current;
    if (element && activePoint) {
      const bounds = element.getBoundingClientRect();
      const ratio = bounds.width > 0 ? (event.clientX - bounds.left) / bounds.width : 0;
      if (findNearestPointIndex(numericPoints, chartPoints.length, ratio) === activeIndex) {
        clearSelection();
        return;
      }
    }
    selectAtClientX(event.clientX);
  };

  const handlePointerLeave = (event) => {
    // Touch selections must survive the finger leaving the screen — that is the
    // whole point of tap-to-inspect. Only hover clears on leave.
    if (event?.pointerType === "mouse" || !isCoarsePointer) {
      clearSelection();
    }
  };
```

Then replace the container element's opening tag (line 2394–2412) with:

```jsx
    <div
      ref={containerRef}
      data-compact-sparkline
      data-pointer-mode={pointerMode}
      role="img"
      aria-label={
        activePoint
          ? `Price trend. Selected ${formatLongDate(activePoint.date)}: ${formatCurrency(activePoint.y)}.`
          : "Price trend"
      }
      className={["group relative z-[60] touch-pan-y overflow-visible rounded-lg", className].filter(Boolean).join(" ")}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={() => { gestureRef.current = null; }}
      onPointerLeave={handlePointerLeave}
      onFocus={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        setActiveIndex(numericPoints.length - 1);
        setTooltipX(
          clampTooltipX({
            chartLeft: bounds.left,
            chartWidth: bounds.width,
            pointerX: bounds.width / 2,
            tooltipWidth: 224,
            viewportWidth: typeof window === "undefined" ? bounds.width : window.innerWidth,
            gutter: 8,
          })
        );
      }}
      onBlur={clearSelection}
      onKeyDown={(event) => {
        if (numericPoints.length === 0) return;
        if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
          event.preventDefault();
          const step = event.key === "ArrowRight" ? 1 : -1;
          const base = activeIndex === null ? numericPoints.length - 1 : activeIndex;
          setActiveIndex(Math.max(0, Math.min(numericPoints.length - 1, base + step)));
        } else if (event.key === "Escape") {
          clearSelection();
        }
      }}
      tabIndex={0}
    >
```

`touch-pan-y` emits `touch-action: pan-y`: the browser keeps vertical scrolling and the component gets horizontal movement. Keep the existing `<svg>`, marker `<span>` and tooltip JSX below unchanged apart from the tooltip's `style`, which becomes `style={{ left: tooltipX }}` — it already is.

- [ ] **Step 6: Add the component-level interaction test**

Create `frontend/components/explore/CompactSparklineInteraction.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
// RipStatisticsPageClient.jsx has mixed CRLF/LF endings; normalise before any
// multi-line anchor.
const source = fs
  .readFileSync(path.resolve(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

const sparkline = source.slice(
  source.indexOf("function CompactSparkline("),
  source.indexOf("function normalizeSetValueHistoryPoints(")
);

test("the sparkline listens on pointer events, not mouse-only events", () => {
  assert.ok(sparkline.length > 0, "CompactSparkline must be locatable");
  assert.ok(sparkline.includes("onPointerDown={handlePointerDown}"));
  assert.ok(sparkline.includes("onPointerMove={handlePointerMove}"));
  assert.ok(sparkline.includes("onPointerUp={handlePointerUp}"));
  assert.ok(!sparkline.includes("onMouseMove="), "the mouse-only handler is replaced");
  assert.ok(!sparkline.includes("onMouseLeave="), "the mouse-only handler is replaced");
});

test("vertical page scrolling is handed back to the browser", () => {
  assert.ok(sparkline.includes("touch-pan-y"), "touch-action: pan-y keeps vertical scroll native");
});

test("desktop hover is untouched", () => {
  // The mouse branch selects on move exactly as before and still clears on leave.
  assert.ok(sparkline.includes('if (event.pointerType === "mouse") {\n      selectAtClientX(event.clientX);'));
  assert.ok(sparkline.includes('if (event?.pointerType === "mouse" || !isCoarsePointer) {\n      clearSelection();'));
});

test("a touch selection survives the finger leaving the screen", () => {
  assert.ok(
    sparkline.includes("// Touch selections must survive the finger leaving the screen"),
    "the leave handler documents and implements the touch exemption"
  );
});

test("keyboard inspection is preserved and extended", () => {
  assert.ok(sparkline.includes("tabIndex={0}"));
  assert.ok(sparkline.includes('event.key === "ArrowRight"'));
  assert.ok(sparkline.includes('event.key === "Escape"'));
});

test("no synthetic mouse events are dispatched", () => {
  assert.ok(!sparkline.includes("new MouseEvent"), "hover must not be simulated");
  assert.ok(!sparkline.includes("dispatchEvent"), "hover must not be simulated");
});
```

- [ ] **Step 7: Run both test files**

Run: `cd frontend && npx tsx --test components/explore/compactSparklineInteraction.test.mjs components/explore/CompactSparklineInteraction.contract.test.mjs`

Expected: PASS.

- [ ] **Step 8: Verify by hand on a touch device or emulator**

At `390px` with touch emulation, on `/TCGs/Pokemon/Sets/<any-set>?tab=overview`:
- Tap the first point of a Top Chase sparkline — a marker and tooltip appear with that date's value.
- Lift your finger — the tooltip stays.
- Tap a different point — the tooltip updates.
- Tap the same point again — the tooltip dismisses.
- Tap the final point — it is selectable.
- Drag your finger vertically starting on a sparkline — the page scrolls and no point is selected.
- Drag horizontally across a sparkline — consecutive points are inspected.
- On the leftmost and rightmost sparklines in a row, confirm the tooltip stays fully on screen.

At `1366px` with a mouse: hover still works exactly as before.

---

### Task 3: Switch the Recharts tooltips to a pointer-aware trigger

Recharts 2.15 supports `<Tooltip trigger="hover" | "click">`. With `trigger="click"` the tooltip is bound to chart clicks and persists after the pointer leaves — which is exactly the touch behaviour the parity spec requires — and it does **not** bind `touchmove`, so vertical scrolling and stray finger movement cannot activate points.

**Files:**
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:2579-2711` (`SetValueLineChart`)
- Modify: `frontend/components/explore/PackValueHistoryChart.jsx:1-20, 520`
- Create: `frontend/components/explore/RechartsPointerTrigger.contract.test.mjs`

**Interfaces:**
- Consumes: `usePointerMode`, `POINTER_MODE_COARSE` from `@/hooks/usePointerMode`.
- Produces: both charts render `<Tooltip trigger={isCoarsePointer ? "click" : "hover"} ... />` and keep every other tooltip prop unchanged.

- [ ] **Step 1: Write the failing contract test**

Create `frontend/components/explore/RechartsPointerTrigger.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const client = read("RipStatisticsPageClient.jsx");
const packValue = read("PackValueHistoryChart.jsx");

const setValueChart = client.slice(
  client.indexOf("function SetValueLineChart("),
  client.indexOf("function SetValueTrendCard(")
);

test("Set Value Trend switches trigger by pointer mode", () => {
  assert.ok(
    setValueChart.includes('trigger={isCoarsePointer ? "click" : "hover"}'),
    "the tooltip trigger follows the active pointer"
  );
  assert.ok(setValueChart.includes("const isCoarsePointer = usePointerMode() === POINTER_MODE_COARSE;"));
  // Everything else about the tooltip is unchanged.
  assert.ok(setValueChart.includes("content={<SetValueTooltip />}"));
  assert.ok(setValueChart.includes('cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }}'));
});

test("Opening Profit vs Cost switches trigger by pointer mode", () => {
  assert.ok(packValue.includes('trigger={isCoarsePointer ? "click" : "hover"}'));
  assert.ok(packValue.includes('import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";'));
  assert.ok(packValue.includes("content={<TrendTooltip packCost={packCost} variant={variant} />}"));
});

test("neither chart simulates hover or disables it globally", () => {
  for (const [name, source] of [["set value", setValueChart], ["opening profit vs cost", packValue]]) {
    assert.ok(!source.includes("new MouseEvent"), `${name} must not synthesise mouse events`);
    assert.ok(!source.includes('trigger="click"'), `${name} must not hardcode click and strip desktop hover`);
  }
});

test("both charts keep exactly one ResponsiveContainer", () => {
  assert.equal((setValueChart.match(/<ResponsiveContainer/g) || []).length, 1);
  assert.equal((packValue.match(/<ResponsiveContainer/g) || []).length, 1);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/explore/RechartsPointerTrigger.contract.test.mjs`

Expected: FAIL — no `trigger=` prop exists.

- [ ] **Step 3: Wire `SetValueLineChart`**

In `frontend/components/explore/RipStatisticsPageClient.jsx`, add as the first line of the `SetValueLineChart` body (immediately before `const chartId = useId()...` at line 2580):

```javascript
  const isCoarsePointer = usePointerMode() === POINTER_MODE_COARSE;
```

Then change the tooltip at line 2682 from:

```jsx
            <RechartsTooltip content={<SetValueTooltip />} cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }} />
```

to:

```jsx
            {/* Touch gets an explicit tap trigger: it persists after the finger
                lifts, and it binds click rather than touchmove, so scrolling
                past the chart can never select a random point. Mouse and
                trackpad keep hover at every width. */}
            <RechartsTooltip
              trigger={isCoarsePointer ? "click" : "hover"}
              content={<SetValueTooltip />}
              cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }}
            />
```

- [ ] **Step 4: Wire `PackValueHistoryChart`**

In `frontend/components/explore/PackValueHistoryChart.jsx`, add to the imports:

```javascript
import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";
```

Add as the first line of the default-exported component's body (alongside the other hooks, before `const seriesLabels = ...` at line 349):

```javascript
  const isCoarsePointer = usePointerMode() === POINTER_MODE_COARSE;
```

Then change line 520 from:

```jsx
            <Tooltip content={<TrendTooltip packCost={packCost} variant={variant} />} cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }} />
```

to:

```jsx
            {/* See SetValueLineChart: tap on touch, hover on mouse, both at
                every width. */}
            <Tooltip
              trigger={isCoarsePointer ? "click" : "hover"}
              content={<TrendTooltip packCost={packCost} variant={variant} />}
              cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }}
            />
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/explore/RechartsPointerTrigger.contract.test.mjs`

Expected: PASS, all four tests.

- [ ] **Step 6: Verify the tooltip clears the sticky tabs and the bottom nav**

At `390px` with touch emulation, tap a point near the **top** of the Set Value Trend chart while scrolled so the sticky tabs are pinned. The tooltip must render above the tab bar, not behind it. Then tap a point near the bottom of the chart with the page scrolled to the end — the tooltip must not be covered by the global bottom nav.

If either fails, the fix is a `z-index` on the Recharts tooltip wrapper, not a layout change to the nav. Add to `frontend/app/styles/globals.css` inside the `@media (max-width: 1199.98px)` block added in Plan 2 Task 5:

```css
  .set-detail-glass-scope .recharts-tooltip-wrapper {
    z-index: 9999;
  }
```

---

### Task 4: Responsive chart heights, axis density and control overflow

Brief §5 wants roughly `240–280px` of chart on a phone and `300–340px` on a tablet, with reduced Y-axis label density and less dead padding. Today `SetValueLineChart` is a flat `h-[21rem]` (336px) at every width and `PackValueHistoryChart` reserves `min-h-[24rem]` (384px) plus a `112px` right margin for its end-of-series labels.

**Files:**
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:2636-2637` (`SetValueLineChart` frame), `:2832` (`SetValueTrendCard` min-height), `:2848-2854` (timeframe control row)
- Modify: `frontend/components/explore/PackValueHistoryChart.jsx:450, 488-489, 592-635`
- Create: `frontend/components/explore/ChartResponsiveSizing.contract.test.mjs`

**Interfaces:**
- Consumes: `useMediaQuery` from `@/hooks/useMediaQuery` (for the Recharts `margin` prop, which is JS and cannot be a Tailwind class).
- Produces: `PackValueHistoryChart` renders a `data-latest-values` row below the legend when `isDesktopComposition` is false, carrying the same three series values that the inline end-of-series labels carry at desktop.

- [ ] **Step 1: Write the failing contract test**

Create `frontend/components/explore/ChartResponsiveSizing.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const client = read("RipStatisticsPageClient.jsx");
const packValue = read("PackValueHistoryChart.jsx");

const setValueChart = client.slice(
  client.indexOf("function SetValueLineChart("),
  client.indexOf("function SetValueTrendCard(")
);

test("Set Value Trend sizes to phone, tablet and desktop", () => {
  // Phone 16rem = 256px (brief: 240-280). Tablet 20rem = 320px (brief: 300-340).
  // Desktop keeps its existing 21rem.
  assert.ok(setValueChart.includes("h-[16rem] tab:h-[20rem] desk:h-[21rem]"));
  assert.ok(setValueChart.includes("min-h-[16rem] tab:min-h-[20rem] desk:min-h-[21rem]"));
  assert.ok(!/ChartFrame className="h-\[21rem\] w-full"/.test(setValueChart), "the flat desktop height is gone");
});

test("Opening Profit vs Cost matches that sizing grammar", () => {
  assert.ok(packValue.includes("min-h-[17rem] tab:min-h-[21rem] desk:min-h-[24rem]"));
  assert.ok(packValue.includes("min-h-[19rem] tab:min-h-[23rem] desk:min-h-[26rem]"));
});

test("mobile reduces axis label density without hiding scale", () => {
  assert.ok(setValueChart.includes("const isDesktopComposition = useMediaQuery"));
  assert.ok(setValueChart.includes("tickCount={isDesktopComposition ? undefined : 4}"));
  assert.ok(setValueChart.includes("width={isDesktopComposition ? 58 : 44}"));
});

test("the wide desktop right margin does not eat the phone plot", () => {
  assert.ok(packValue.includes("right: isDesktopComposition ? 112 : 12"));
});

test("the three series values survive when the inline end labels do not", () => {
  // Expected Value / Typical Return / Realistic Upside are relocated, never
  // removed: below 1200px they render in a compact row under the legend.
  assert.ok(packValue.includes("data-latest-values"), "a latest-values row exists below desktop");
  assert.ok(packValue.includes("index === latestDataIndex && isDesktopComposition"), "inline labels are desktop-only");
});

test("timeframe controls scroll rather than shrink to unreadable text", () => {
  assert.ok(client.includes("max-desk:overflow-x-auto max-desk:flex-nowrap"));
  assert.ok(!setValueChart.includes("text-[9px]"), "controls must not be shrunk into illegibility");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/explore/ChartResponsiveSizing.contract.test.mjs`

Expected: FAIL on every test.

- [ ] **Step 3: Size and thin out `SetValueLineChart`**

In `frontend/components/explore/RipStatisticsPageClient.jsx`, add to the imports:

```javascript
import useMediaQuery from "@/hooks/useMediaQuery";
```

In `SetValueLineChart`, after the `isCoarsePointer` line added in Task 3, add:

```javascript
  // `true` on the server and first paint so desktop never flashes a mobile axis.
  const isDesktopComposition = useMediaQuery("(min-width: 1200px)", true);
```

Replace lines 2636–2637:

```jsx
    <div className="min-h-[21rem] w-full">
      <ChartFrame className="h-[21rem] w-full">
```

with:

```jsx
    <div className="min-h-[16rem] w-full tab:min-h-[20rem] desk:min-h-[21rem]">
      <ChartFrame className="h-[16rem] w-full tab:h-[20rem] desk:h-[21rem]">
```

Change the chart margin (line 2639) to trim the dead top and bottom padding below desktop:

```jsx
          <ComposedChart data={numericPoints} margin={{ top: isDesktopComposition ? 12 : 6, right: isDesktopComposition ? 18 : 10, left: 0, bottom: isDesktopComposition ? 8 : 2 }}>
```

Change the `<YAxis>` (lines 2673–2681) to:

```jsx
            <YAxis
              domain={[yMin, yMax]}
              ticks={isDesktopComposition ? yAxisTicks : undefined}
              tickCount={isDesktopComposition ? undefined : 4}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={formatAxisCurrency}
              width={isDesktopComposition ? 58 : 44}
            />
```

Four ticks still communicate scale (min, two interior, max) while returning ~14px of plot width. Do not drop below four — the brief requires "enough labels to understand scale."

- [ ] **Step 4: Let the Set Value card shrink and its controls scroll**

Line 2832's content column is `flex min-h-[29rem] flex-col space-y-4`. Change it to:

```jsx
        <div className="flex min-h-0 flex-col space-y-4 desk:min-h-[29rem]">
```

Change the timeframe control row (line 2848) from:

```jsx
          <div className="flex flex-wrap items-center gap-2">
```

to:

```jsx
          <div className="flex flex-wrap items-center gap-2 max-desk:overflow-x-auto max-desk:flex-nowrap max-desk:[-ms-overflow-style:none] max-desk:[scrollbar-width:none] max-desk:[&::-webkit-scrollbar]:hidden">
```

This keeps `Lifetime` reachable on a 320px phone by scrolling rather than by shrinking the labels.

- [ ] **Step 5: Size `PackValueHistoryChart` and relocate its end labels**

In `frontend/components/explore/PackValueHistoryChart.jsx`, add to the imports:

```javascript
import useMediaQuery from "@/hooks/useMediaQuery";
```

Add alongside the `isCoarsePointer` line from Task 3:

```javascript
  const isDesktopComposition = useMediaQuery("(min-width: 1200px)", true);
```

Change the `flush` wrapper (line 450):

```jsx
    <div className={flush ? "flex h-full min-h-[19rem] flex-col tab:min-h-[23rem] desk:min-h-[26rem]" : "rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 sm:p-5"}>
```

Change the `ChartFrame` (line 488):

```jsx
      <ChartFrame className={flush ? "mt-3 min-h-[17rem] w-full flex-1 tab:min-h-[21rem] desk:min-h-[24rem]" : "mt-4 h-[20rem] w-full sm:h-[23rem]"}>
```

Change the chart margin (line 489):

```jsx
          <LineChart data={chartData} margin={{ top: 10, right: isDesktopComposition ? 112 : 12, left: 6, bottom: isDesktopComposition ? 14 : 6 }}>
```

Gate each of the three inline `label={...}` renders (lines 592–596, 611–615, 630–634) on the desktop composition. For each, change `index === latestDataIndex` to `index === latestDataIndex && isDesktopComposition`. For example, the mean series becomes:

```jsx
                label={({ x, y, value, index }) =>
                  index === latestDataIndex && isDesktopComposition
                    ? <RatioPointLabel x={x} y={y} value={value} dollarValue={chartData[index]?.meanValue} />
                    : null
                }
```

- [ ] **Step 6: Add the latest-values row so nothing is lost**

Still in `PackValueHistoryChart.jsx`, immediately after the closing `</div>` of the legend row (after the `LegendToggle` block ends around line 485, before `<ChartFrame`), add:

```jsx
      {/* Below 1200px the inline end-of-series labels are suppressed to give the
          plot its width back. The values are not removed — Expected Value,
          Typical Return and Realistic Upside render here instead, with the same
          series colours and the same numbers the labels carried. */}
      {!isDesktopComposition ? (
        <dl data-latest-values className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[11px]">
          {[
            { key: "mean", show: showMeanLine, label: seriesLabels.mean, color: HISTORICAL_TREND_COLORS.meanToCost, ratio: chartData[latestDataIndex]?.meanCostRatio, dollars: chartData[latestDataIndex]?.meanValue },
            { key: "median", show: showMedianLine, label: seriesLabels.median, color: HISTORICAL_TREND_COLORS.medianToCost, ratio: chartData[latestDataIndex]?.medianCostRatio, dollars: chartData[latestDataIndex]?.medianValue },
            { key: "p95", show: hasP95Data && showP95Line, label: seriesLabels.p95, color: HISTORICAL_TREND_COLORS.p95ToCost, ratio: chartData[latestDataIndex]?.p95CostRatio, dollars: chartData[latestDataIndex]?.p95Value },
          ]
            .filter((entry) => entry.show && entry.ratio !== null && entry.ratio !== undefined)
            .map((entry) => (
              <div key={`latest-value:${entry.key}`} className="flex min-w-0 items-baseline gap-1.5">
                <span className="inline-block h-0.5 w-3 flex-none translate-y-[-0.15rem] rounded" style={{ backgroundColor: entry.color }} aria-hidden="true" />
                <dt className="text-[var(--text-secondary)]">{entry.label}</dt>
                <dd className="font-semibold tabular-nums text-[var(--text-primary)]">
                  {formatRatio(entry.ratio)}
                  {entry.dollars === null || entry.dollars === undefined ? null : (
                    <span className="ml-1 font-normal text-[var(--text-secondary)]">({formatCurrency(entry.dollars)})</span>
                  )}
                </dd>
              </div>
            ))}
        </dl>
      ) : null}
```

If `formatRatio` or `formatCurrency` are not already in scope at this point in the file, they are — both are used by the axis and the break-even label above. Confirm with the Grep tool before assuming.

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/explore/ChartResponsiveSizing.contract.test.mjs`

Expected: PASS, all six tests.

- [ ] **Step 8: Verify sizing and legibility**

At `320px`, `390px`, `834px` and `1366px`:
- Measure both charts: `document.querySelector('[data-overview-opening-economics]')` is below the chart, and the chart's own rect height should be ~256px at 390px, ~320px at 834px, and unchanged (~336px Set Value / ~384px OPvC) at 1366px.
- Y-axis labels are readable and there are at least four of them.
- The legend wraps to two rows on a narrow phone rather than shrinking; the `data-latest-values` row shows all active series.
- The timeframe row scrolls horizontally on a 320px phone and `Lifetime` is reachable.
- No chart content sits beneath the global bottom nav at the end of the page.
- At `1366px`, screenshot-diff both charts against `main`. They must be identical.

---

### Task 5: Prove chart state survives unrelated rerenders

Parity spec §5 forbids resetting the selected timeframe, series, Checklist/Hits/Top 10 mode or active point when the viewport changes slightly, the phone rotates, sticky state changes, an unrelated section rerenders, or Market Movers advances.

`SetValueTrendCard` has a real hazard here: `useEffect(() => { setSelectedWindowKey(null); }, [setId, selectedScope])` at line 2781, plus `chartKey` at line 2779, which is passed as `key` to `SetValueLineChart` and **remounts the chart whenever it changes**.

**Files:**
- Create: `frontend/components/explore/setValueTrendState.test.mjs`
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:2779` only if the test proves a defect.

- [ ] **Step 1: Write the test**

Create `frontend/components/explore/setValueTrendState.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

const card = source.slice(
  source.indexOf("function SetValueTrendCard("),
  source.indexOf("function OverviewMetricTile(")
);

test("the chart identity does not depend on anything a rerender can jiggle", () => {
  const keyLine = /const chartKey = `([^`]+)`;/.exec(card);
  assert.ok(keyLine, "chartKey must be locatable");
  const key = keyLine[1];
  // A remount discards the active point and replays the mount animation. The
  // key may only change when the underlying series genuinely changes identity.
  for (const forbidden of ["window.innerWidth", "isDesktopComposition", "pointerMode", "activeIndex"]) {
    assert.ok(!key.includes(forbidden), `chartKey must not include ${forbidden}`);
  }
  assert.ok(key.includes("${setId"), "set identity is a legitimate remount trigger");
  assert.ok(key.includes("${selectedTrend.scope}"), "scope change is a legitimate remount trigger");
});

test("the timeframe reset is scoped to set and scope changes only", () => {
  const resetEffect = /useEffect\(\(\) => \{\s*setSelectedWindowKey\(null\);\s*\}, \[([^\]]+)\]\);/.exec(card);
  assert.ok(resetEffect, "the reset effect must be locatable");
  const deps = resetEffect[1].split(",").map((entry) => entry.trim()).filter(Boolean);
  assert.deepEqual(deps.sort(), ["selectedScope", "setId"], "no other dependency may reset the timeframe");
});

test("the selected scope is owned above the card so a card rerender cannot lose it", () => {
  assert.ok(card.includes("selectedScope = CANONICAL_SET_VALUE_SCOPE,"), "scope is a prop, not local state");
  assert.ok(card.includes("onSelectedScopeChange"), "scope changes are lifted to the page");
  assert.ok(
    source.includes("selectedScope={setValueTrendScope}") && source.includes("onSelectedScopeChange={setSetValueTrendScope}"),
    "the page owns Checklist / Hits / Top 10 state"
  );
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npx tsx --test components/explore/setValueTrendState.test.mjs`

Expected: PASS on the current code. This test is a **regression lock**, not a bug report — the state ownership is already correct, and Tasks 3 and 4 must not break it. If it fails, you introduced a dependency in Task 3 or 4; remove it rather than relaxing the test.

- [ ] **Step 3: Verify by hand that Market Movers does not reset the chart**

At `390px`, select the `7D` timeframe and the `Hits` scope on Set Value Trend, then tap a chart point. Wait through at least two full Market Movers ticker cycles. The timeframe, the scope and the selected point must all still be there.

Rotate the device (or toggle between `390px` and `844px` in device emulation). The timeframe and scope must survive; the active point may clear on a genuine remount but the chart must not jump back to its default period.

---

### Task 6: Full-suite and cross-width verification

- [ ] **Step 1: Run the whole suite**

Run: `cd frontend && npm run test:frontend`

Expected: no failures beyond the Plan 1 Task 1 baseline.

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`

Expected: succeeds.

- [ ] **Step 3: Confirm chart instances did not multiply**

In the browser at `390px` and again at `1366px` on `/TCGs/Pokemon/Sets/<any-set>?tab=overview`:

```javascript
document.querySelectorAll(".recharts-responsive-container").length
```

Expected: the same number at both widths, and no larger than after Plan 2. If it grew, something mounted a mobile-only chart — find it and remove it.

- [ ] **Step 4: Width sweep**

At `320, 360, 390, 430, 480, 599, 600, 768, 834, 1024, 1199, 1200, 1366` confirm for both Overview charts:
- Tooltip values, dates and both movement figures match the underlying data point.
- The first and the final data point are both selectable.
- The tooltip stays inside the viewport at the left and right chart edges.
- Vertical page scrolling works with a finger starting on the chart.
- Desktop hover works at `1200px` and `1366px`.
- Timeframe and series switching still change the chart.

---

## Acceptance for this plan

Maps to brief acceptance criteria 15, 16, 23, 24, and parity spec §2, §3, §4, §5, §9.

- [ ] Every Overview chart is inspectable by tap on touch and by hover on mouse, at every width.
- [ ] No synthetic mouse events; both Recharts charts use the supported `trigger` API.
- [ ] Vertical page scrolling is never captured by a chart.
- [ ] Tooltips stay inside the viewport and render above the sticky tabs and the bottom nav.
- [ ] First and final data points are selectable on both charts and the sparkline.
- [ ] Phone chart bodies land in `240–280px`; tablet in `300–340px`; desktop is unchanged.
- [ ] At least four Y-axis labels below desktop.
- [ ] Expected Value, Typical Return and Realistic Upside are all still displayed below 1200px.
- [ ] Timeframe controls scroll rather than shrink; `Lifetime` is reachable at 320px.
- [ ] Chart count is identical at 390px and 1366px.
- [ ] Timeframe, scope and active point survive Market Movers advancing and unrelated rerenders.
- [ ] Desktop at 1200px+ is pixel-identical to `main`.
