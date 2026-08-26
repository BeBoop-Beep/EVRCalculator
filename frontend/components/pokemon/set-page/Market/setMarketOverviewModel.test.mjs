import assert from "node:assert/strict";
import test from "node:test";

import {
  BREADTH_SUPPORTED_WINDOW_KEYS,
  MARKET_SEGMENT_KEYS,
  SEGMENT_UNAVAILABLE_TEXT,
  buildMarketSegmentRows,
  buildSupportingDetails,
  normalizeSegmentHistory,
  resolveActiveSegmentKey,
  resolveDefaultSegmentKey,
  selectChaseConcentration,
  selectMarketBreadth,
  selectPreparedMarketBreadth,
  selectPreparedSegmentTrend,
  selectSegmentTrend,
  toPreparedMovementKey,
  unavailableSegmentTrend,
} from "./setMarketOverviewModel.mjs";

function dailyHistory(values, { startDate = "2026-01-01", valueKey = "setValue" } = {}) {
  const start = new Date(`${startDate}T00:00:00Z`);
  return values.map((value, index) => {
    const day = new Date(start.getTime() + index * 86400000);
    return { date: day.toISOString().slice(0, 10), [valueKey]: value };
  });
}

test("history normalization speaks one vocabulary for cards and sealed", () => {
  const cards = normalizeSegmentHistory([{ date: "2026-01-02", setValue: 10 }]);
  const sealed = normalizeSegmentHistory([{ date: "2026-01-02", marketPrice: 10 }]);
  assert.equal(cards[0].setValue, 10);
  assert.equal(sealed[0].setValue, 10, "the sealed snapshot's marketPrice must fold into setValue");
});

test("history normalization sorts and drops undated points", () => {
  const points = normalizeSegmentHistory([
    { date: "2026-01-03", setValue: 3 },
    { date: null, setValue: 99 },
    { date: "2026-01-01", setValue: 1 },
  ]);
  assert.deepEqual(
    points.map((point) => point.date),
    ["2026-01-01", "2026-01-03"]
  );
});

test("prepared index movement owns Period Return while Set Value owns dollar change", () => {
  const trend = selectPreparedSegmentTrend({
    valueHistory: dailyHistory([100, 110], { startDate: "2026-01-01" }),
    marketIndex: {
      currentValue: 103.25,
      trackingSince: "2026-01-01",
      history: [{ date: "2026-01-01", indexValue: 100 }, { date: "2026-01-02", indexValue: 103.25 }],
      movements: { "7D": { available: true, percent: 3.25 } },
    },
    selectedWindowKey: "7D",
  });
  assert.equal(trend.deltaAmount, 10);
  assert.equal(trend.deltaPercent, 3.25);
  assert.equal(trend.marketIndexValue, 103.25);
});

test("prepared breadth is displayed verbatim and All maps centrally to SinceTracking", () => {
  assert.equal(toPreparedMovementKey("lifetime"), "SinceTracking");
  assert.deepEqual(selectPreparedMarketBreadth({
    windowKey: "7D",
    marketBreadth: { "7D": { available: true, eligibleCount: 10, advancingCount: 6, decliningCount: 3, unchangedCount: 1, advancingPercent: 60, decliningPercent: 30 } },
  }), { available: true, windowKey: "7D", advancing: 6, declining: 3, flat: 1, total: 10, advancingPercent: 60, decliningPercent: 30, unchangedPercent: 10 });
});

test("prepared breadth identifies an unpublished timeframe explicitly", () => {
  assert.equal(
    selectPreparedMarketBreadth({ marketBreadth: {}, windowKey: "6M" }).reason,
    "Breadth is currently available for 1D, 7D, and 30D."
  );
});

test("a segment trend reports value, delta, return, high and low for the selected window", () => {
  const trend = selectSegmentTrend({
    history: dailyHistory([100, 90, 120, 110]),
    selectedWindowKey: "lifetime",
    trackedItemCount: 305,
    trackedItemNoun: "Cards",
  });
  assert.equal(trend.available, true);
  assert.equal(trend.currentValue, 110);
  assert.equal(trend.deltaAmount, 10);
  assert.ok(Math.abs(trend.deltaPercent - 10) < 1e-9);
  assert.equal(trend.periodHigh, 120);
  assert.equal(trend.periodLow, 90);
  assert.equal(trend.trackingSinceDate, "2026-01-01");
  assert.equal(trend.trackedItemCount, 305);
});

test("period high and low bracket only the window on screen", () => {
  // The 2025 spike is real history but is outside a 7D read, so it must not be
  // reported as the period high for a reader looking at the last week.
  const history = [
    { date: "2025-01-01", setValue: 900 },
    ...dailyHistory([100, 101, 102, 103, 104, 105, 106, 107], { startDate: "2026-01-01" }),
  ];
  const week = selectSegmentTrend({ history, selectedWindowKey: "7D" });
  assert.ok(week.periodHigh < 900, "a value outside the selected window is not the period high");
  const lifetime = selectSegmentTrend({ history, selectedWindowKey: "lifetime" });
  assert.equal(lifetime.periodHigh, 900);
});

test("changing the timeframe changes the delta, the return and the plotted series", () => {
  const history = dailyHistory(Array.from({ length: 40 }, (_, index) => 100 + index));
  const week = selectSegmentTrend({ history, selectedWindowKey: "7D" });
  const month = selectSegmentTrend({ history, selectedWindowKey: "30D" });
  assert.notEqual(week.deltaAmount, month.deltaAmount);
  assert.notEqual(week.deltaPercent, month.deltaPercent);
  assert.ok(month.series.length > week.series.length);
  assert.equal(week.currentValue, month.currentValue, "current value is the same latest price at either timeframe");
});

test("a lens with no history is unavailable rather than zero", () => {
  const trend = selectSegmentTrend({ history: [] });
  assert.equal(trend.available, false);
  assert.equal(trend.currentValue, null, "an empty lens must never resolve to 0");
  assert.notEqual(trend.currentValue, 0);
});

test("segment rows keep an unavailable lens visible but unselectable, and never print $0", () => {
  const rows = buildMarketSegmentRows({
    cards: selectSegmentTrend({ history: dailyHistory([100, 120]), selectedWindowKey: "lifetime" }),
    sealed: selectSegmentTrend({ history: dailyHistory([40, 44]), selectedWindowKey: "lifetime" }),
    graded: unavailableSegmentTrend(),
  });
  assert.deepEqual(
    rows.map((row) => row.key),
    MARKET_SEGMENT_KEYS
  );
  const graded = rows.find((row) => row.key === "graded");
  assert.equal(graded.available, false);
  assert.equal(graded.selectable, false);
  assert.equal(graded.currentValue, null);
  assert.equal(graded.unavailableReason, SEGMENT_UNAVAILABLE_TEXT);
  assert.equal(rows.find((row) => row.key === "cards").selectable, true);
});

test("Cards is the default lens, and selection can never strand the chart", () => {
  const trends = {
    cards: selectSegmentTrend({ history: dailyHistory([100, 120]), selectedWindowKey: "lifetime" }),
    sealed: selectSegmentTrend({ history: dailyHistory([40, 44]), selectedWindowKey: "lifetime" }),
    graded: unavailableSegmentTrend(),
  };
  assert.equal(resolveDefaultSegmentKey(trends), "cards");
  assert.equal(resolveActiveSegmentKey("sealed", trends), "sealed");
  assert.equal(resolveActiveSegmentKey("graded", trends), "cards", "an unavailable lens falls back to Cards");
  assert.equal(resolveActiveSegmentKey("nonsense", trends), "cards");
});

// --- Breadth ----------------------------------------------------------------

function moversByWindow(amounts) {
  return {
    "7D": { marketMovers: { all: amounts.map((changeAmount) => ({ changeAmount })) } },
  };
}

test("breadth counts the complete mover-eligible list, not the ticker's slice", () => {
  const breadth = selectMarketBreadth({
    moversByWindow: moversByWindow([5, 4, -1, -2, -3, -4, -5, -6]),
    windowKey: "7D",
  });
  assert.equal(breadth.available, true);
  assert.equal(breadth.total, 8);
  assert.equal(breadth.advancing, 2);
  assert.equal(breadth.declining, 6);
  assert.equal(breadth.advancingPercent, 25);
  assert.equal(breadth.decliningPercent, 75);
});

test("breadth is unavailable for timeframes the movers contract does not publish", () => {
  assert.deepEqual(BREADTH_SUPPORTED_WINDOW_KEYS, ["1D", "7D", "30D"]);
  for (const windowKey of ["3M", "6M", "1Y", "lifetime"]) {
    const breadth = selectMarketBreadth({ moversByWindow: moversByWindow([1, -1]), windowKey });
    assert.equal(breadth.available, false, `${windowKey} has no authoritative breadth reading`);
    assert.equal(breadth.advancingPercent, undefined, "no percentage is invented for an unsupported window");
  }
});

test("breadth is unavailable rather than 0% when the window carries no movements", () => {
  const breadth = selectMarketBreadth({ moversByWindow: { "7D": { marketMovers: { all: [] } } }, windowKey: "7D" });
  assert.equal(breadth.available, false);
  assert.equal(breadth.reason, SEGMENT_UNAVAILABLE_TEXT);
});

// --- Concentration ----------------------------------------------------------

test("concentration is the published top10 scope over the published set scope", () => {
  const concentration = selectChaseConcentration({ top10Value: 6400, cardsValue: 10000 });
  assert.equal(concentration.available, true);
  assert.equal(concentration.sharePercent, 64);
  assert.equal(concentration.top10Value, 6400);
});

test("concentration is unavailable when either canonical scope is missing", () => {
  assert.equal(selectChaseConcentration({ top10Value: null, cardsValue: 10000 }).available, false);
  assert.equal(selectChaseConcentration({ top10Value: 6400, cardsValue: null }).available, false);
  assert.equal(selectChaseConcentration({ top10Value: 6400, cardsValue: 0 }).available, false);
});

test("concentration exposes no Low/Medium/High banding", () => {
  const concentration = selectChaseConcentration({ top10Value: 6400, cardsValue: 10000 });
  const serialized = JSON.stringify(concentration).toLowerCase();
  for (const banding of ["low", "medium", "high", "band", "tier"]) {
    assert.ok(!serialized.includes(`"${banding}"`), `no invented ${banding} classification`);
  }
});

// --- Supporting details -----------------------------------------------------

test("supporting details publish the five approved fields in order", () => {
  const details = buildSupportingDetails(
    selectSegmentTrend({
      history: dailyHistory([100, 90, 120, 110]),
      selectedWindowKey: "lifetime",
      trackedItemCount: 305,
      trackedItemNoun: "Cards",
    })
  );
  assert.deepEqual(
    details.map((detail) => detail.key),
    ["periodHigh", "periodLow", "trackingSince", "marketIndex", "trackedItems"]
  );
  assert.deepEqual(
    details.map((detail) => detail.label),
    ["Period High", "Period Low", "Tracking Since", "Market Index", "Tracked Items"]
  );
});

test("tracked items follow the active lens's own noun and count", () => {
  const cards = buildSupportingDetails(
    selectSegmentTrend({ history: dailyHistory([1, 2]), trackedItemCount: 305, trackedItemNoun: "Cards" })
  ).at(-1);
  const sealed = buildSupportingDetails(
    selectSegmentTrend({ history: dailyHistory([1, 2]), trackedItemCount: 7, trackedItemNoun: "Sealed Products" })
  ).at(-1);
  assert.equal(cards.count, 305);
  assert.equal(cards.noun, "Cards");
  assert.equal(sealed.count, 7);
  assert.equal(sealed.noun, "Sealed Products");
});

test("supporting details for an unavailable lens carry nulls, not zeros", () => {
  const details = buildSupportingDetails(unavailableSegmentTrend());
  assert.equal(details.find((detail) => detail.key === "periodHigh").value, null);
  assert.equal(details.find((detail) => detail.key === "trackedItems").count, null);
});
