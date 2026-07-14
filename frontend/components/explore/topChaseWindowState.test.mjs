import test from "node:test";
import assert from "node:assert/strict";

import { filterHistoryPointsForDeltaWindow } from "../../lib/explore/marketDeltaWindows.mjs";
import {
  getTopCardPreferredHistoryEndDate,
  resolveTopCardWindowState,
  warnForTopCardWindowState,
} from "./topChaseWindowState.mjs";

function addDays(dateKey, days) {
  const date = new Date(`${dateKey}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function history(count = 200, endDate = "2026-07-13") {
  const startDate = addDays(endDate, -(count - 1));
  return Array.from({ length: count }, (_, index) => ({
    date: addDays(startDate, index),
    value: 100 + index,
    isCarriedForward: false,
  }));
}

function storedMovement(overrides = {}) {
  return {
    changeAmount: 29,
    changePercent: 10,
    currentPrice: 299,
    startDate: "2026-06-14",
    endDate: "2026-07-13",
    targetStartDate: "2026-06-14",
    cardVariantId: "variant-1",
    conditionId: "near-mint",
    ...overrides,
  };
}

function cardWithStored(movement = storedMovement()) {
  return {
    canonicalCardId: "canonical-1",
    cardVariantId: "variant-1",
    conditionId: "near-mint",
    marketDate: "2026-07-13",
    marketDeltaWindows: { "30D": movement },
  };
}

test("30D stored movement remains authoritative while the graph uses only its history window", () => {
  const points = history();
  const state = resolveTopCardWindowState({
    card: cardWithStored(),
    historyPoints: points,
    selectedWindowKey: "30D",
  });
  const visible = filterHistoryPointsForDeltaWindow(points, state.chartWindow);

  assert.equal(state.source, "stored-canonical");
  assert.equal(state.displayMovement.amount, 29);
  assert.equal(state.chartWindow.startDate, "2026-06-14");
  assert.equal(state.chartWindow.endDate, "2026-07-13");
  assert.equal(visible[0].date, "2026-06-14");
  assert.equal(visible.at(-1).date, "2026-07-13");
  assert.equal(visible.length, 30);
});

test("missing 30D stored movement uses a real history delta and a constrained graph", () => {
  const points = history();
  const state = resolveTopCardWindowState({ card: {}, historyPoints: points, selectedWindowKey: "30D" });
  const visible = filterHistoryPointsForDeltaWindow(points, state.chartWindow);

  assert.equal(state.source, "history_fallback_missing_stored_window");
  assert.equal(state.displayMovement.amount, 29);
  assert.equal(visible.length, 30);
  assert.deepEqual(state.warnings, ["missing_stored_window"]);
});

test("missing 7D stored movement never exposes the annual history", () => {
  const points = history(365);
  const state = resolveTopCardWindowState({ card: {}, historyPoints: points, selectedWindowKey: "7D" });
  const visible = filterHistoryPointsForDeltaWindow(points, state.chartWindow);

  assert.equal(visible.length, 7);
  assert.equal(visible[0].date, "2026-07-07");
  assert.equal(visible.at(-1).date, "2026-07-13");
});

test("missing 1D stored movement uses the latest two distinct market dates", () => {
  const points = history(10);
  const state = resolveTopCardWindowState({ card: {}, historyPoints: points, selectedWindowKey: "1D" });
  const visible = filterHistoryPointsForDeltaWindow(points, state.chartWindow);

  assert.deepEqual(visible.map((point) => point.date), ["2026-07-12", "2026-07-13"]);
  assert.equal(state.displayMovement.amount, 1);
});

test("stored movement missing startDate is rejected in favor of valid history", () => {
  const state = resolveTopCardWindowState({
    card: cardWithStored(storedMovement({ startDate: null })),
    historyPoints: history(),
    selectedWindowKey: "30D",
  });

  assert.equal(state.source, "history_fallback_malformed_stored_window");
  assert.equal(state.displayMovement.amount, 29);
  assert.ok(state.warnings.includes("malformed_stored_window"));
});

test("stored amount stays authoritative when stored and history dates disagree", () => {
  const state = resolveTopCardWindowState({
    card: cardWithStored(storedMovement({ changeAmount: 777, startDate: "2026-06-13" })),
    historyPoints: history(),
    selectedWindowKey: "30D",
  });

  assert.equal(state.displayMovement.amount, 777);
  assert.equal(state.chartWindow.startDate, "2026-06-14");
  assert.ok(state.warnings.some((warning) => warning.includes("stored_history_mismatch:startDate")));
});

test("insufficient selected-window history renders no chart window instead of complete history", () => {
  const state = resolveTopCardWindowState({
    card: {},
    historyPoints: [{ date: "2026-07-13", value: 100 }],
    selectedWindowKey: "30D",
  });

  assert.equal(state.source, "insufficient_history");
  assert.equal(state.chartWindow, null);
  assert.equal(state.displayMovement, null);
});

test("3M and 6M remain history-derived", () => {
  const points = history(365);
  const threeMonths = resolveTopCardWindowState({ card: {}, historyPoints: points, selectedWindowKey: "3M" });
  const sixMonths = resolveTopCardWindowState({ card: {}, historyPoints: points, selectedWindowKey: "6M" });

  assert.equal(filterHistoryPointsForDeltaWindow(points, threeMonths.chartWindow).length, 90);
  assert.equal(filterHistoryPointsForDeltaWindow(points, sixMonths.chartWindow).length, 180);
  assert.equal(threeMonths.source, "history");
  assert.equal(sixMonths.source, "history");
});

test("switching from 6M to 30D immediately produces the short visible series", () => {
  const points = history(365);
  const sixMonths = resolveTopCardWindowState({ card: {}, historyPoints: points, selectedWindowKey: "6M" });
  const thirtyDays = resolveTopCardWindowState({ card: {}, historyPoints: points, selectedWindowKey: "30D" });

  assert.equal(filterHistoryPointsForDeltaWindow(points, sixMonths.chartWindow).length, 180);
  assert.equal(filterHistoryPointsForDeltaWindow(points, thirtyDays.chartWindow).length, 30);
});

test("tooltip input points cannot escape the selected visual window", () => {
  const points = history(365);
  const state = resolveTopCardWindowState({ card: {}, historyPoints: points, selectedWindowKey: "7D" });
  const tooltipPoints = filterHistoryPointsForDeltaWindow(points, state.chartWindow);

  assert.ok(tooltipPoints.every((point) => point.date >= "2026-07-07" && point.date <= "2026-07-13"));
});

test("preferred graph end never advances beyond the snapshot market as-of date", () => {
  const points = history(40, "2026-07-20");
  const card = { marketDate: "2026-07-13", dashboardLatestMarketDate: "2026-07-14" };

  assert.equal(getTopCardPreferredHistoryEndDate(card, "30D", points), "2026-07-13");
  assert.equal(
    getTopCardPreferredHistoryEndDate(
      { ...card, marketDeltaWindows: { "30D": storedMovement({ endDate: "2026-07-12" }) } },
      "30D",
      points
    ),
    "2026-07-12"
  );
  assert.equal(
    getTopCardPreferredHistoryEndDate(
      { ...card, marketDeltaWindows: { "30D": storedMovement({ endDate: "2026-07-20" }) } },
      "30D",
      points
    ),
    "2026-07-13"
  );
});

test("development diagnostics record a missing stored-window fallback", () => {
  const originalWarn = console.warn;
  const warnings = [];
  console.warn = (...args) => warnings.push(args);
  try {
    const state = resolveTopCardWindowState({ card: {}, historyPoints: history(), selectedWindowKey: "30D" });
    warnForTopCardWindowState(state, { canonicalCardId: "canonical-1" }, "30D");
  } finally {
    console.warn = originalWarn;
  }

  assert.equal(warnings.length, 1);
  assert.equal(warnings[0][1].warning, "missing_stored_window");
});
