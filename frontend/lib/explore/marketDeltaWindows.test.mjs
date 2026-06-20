import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  DELTA_WINDOW_DEFINITIONS,
  computeDeltaWindowsFromHistory,
  extractDeltaWindows,
  filterHistoryPointsForDeltaWindow,
  getDeltaWindowLabel,
  getDeltaTrendDirection,
  getPreferredDeltaWindowKey,
  getSelectedDeltaWindowFromHistory,
  getStandardDeltaWindowDefinitions,
  getVisibleHistoryWindowMetrics,
  STANDARD_DELTA_WINDOW_KEYS,
} from "./marketDeltaWindows.mjs";

function addDays(dateKey, days) {
  const date = new Date(`${dateKey}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function buildDailyRows(count, { startDate = "2025-06-19", startValue = 100 } = {}) {
  return Array.from({ length: count }, (_, index) => ({
    date: addDays(startDate, index),
    value: startValue + index,
  }));
}

test("marketDeltaWindows exposes the standard market window definitions", () => {
  assert.deepEqual(
    STANDARD_DELTA_WINDOW_KEYS,
    ["1D", "7D", "30D", "3M", "6M", "1Y", "lifetime"]
  );
  assert.deepEqual(
    DELTA_WINDOW_DEFINITIONS.map((definition) => definition.label),
    ["1D", "7D", "30D", "3M", "6M", "1Y", "Lifetime"]
  );
});

test("extractDeltaWindows reads actual amount and percent fields", () => {
  const windows = extractDeltaWindows({
    delta_30d: 25,
    delta_pct_30d: 12.5,
    delta_7d: 5,
  });

  assert.deepEqual(
    windows.map((window) => [window.key, window.amount, window.percent]),
    [
      ["7D", 5, null],
      ["30D", 25, 12.5],
    ]
  );
});

test("extractDeltaWindows reads nested top-card delta payloads", () => {
  const windows = extractDeltaWindows({
    deltas: {
      "30D": -8.25,
      lifetime: -8.25,
    },
  });

  assert.equal(getPreferredDeltaWindowKey(windows, "30D"), "30D");
  assert.equal(windows.find((window) => window.key === "30D")?.percent, -8.25);
});

test("computeDeltaWindowsFromHistory keeps standard windows and clamps overlong windows to first available", () => {
  const rows = [
    { date: "2026-06-12", value: 100 },
    { date: "2026-06-13", value: 105 },
    { date: "2026-06-14", value: 110 },
    { date: "2026-06-15", value: 120 },
    { date: "2026-06-16", value: 125 },
    { date: "2026-06-17", value: 130 },
    { date: "2026-06-18", value: 140, isCarriedForward: true },
  ];

  const windows = computeDeltaWindowsFromHistory(rows);

  assert.deepEqual(windows.map((window) => window.key), STANDARD_DELTA_WINDOW_KEYS);
  assert.equal(windows.find((window) => window.key === "7D")?.amount, 40);
  assert.equal(windows.find((window) => window.key === "30D")?.startDate, "2026-06-12");
  assert.equal(windows.find((window) => window.key === "30D")?.isSinceFirstAvailable, true);
  assert.equal(windows.find((window) => window.key === "7D")?.isCarriedForward, true);
  assert.equal(getDeltaWindowLabel("7D"), "7D");
});

test("window controls can be based on full loaded history while the rendered slice is short", () => {
  const fullHistory = buildDailyRows(365);
  const { windows, selectedWindow } = getSelectedDeltaWindowFromHistory(fullHistory, {
    selectedKey: "30D",
    preferredKey: "30D",
  });
  const renderedSlice = filterHistoryPointsForDeltaWindow(fullHistory, selectedWindow);

  assert.ok(windows.some((window) => window.key === "30D"));
  assert.ok(windows.some((window) => window.key === "6M"));
  assert.ok(windows.some((window) => window.key === "1Y"));
  assert.equal(renderedSlice.length, 30);
});

test("30D, 6M, and 1Y windows become available from sufficient loaded history", () => {
  assert.ok(computeDeltaWindowsFromHistory(buildDailyRows(30)).some((window) => window.key === "30D"));
  assert.ok(computeDeltaWindowsFromHistory(buildDailyRows(180)).some((window) => window.key === "6M"));
  assert.ok(computeDeltaWindowsFromHistory(buildDailyRows(365)).some((window) => window.key === "1Y"));
});

test("standard controls remain available when selected window is longer than actual history", () => {
  const rows = buildDailyRows(37, { startDate: "2026-04-26", startValue: 100 });
  const { windows, selectedWindow } = getSelectedDeltaWindowFromHistory(rows, {
    selectedKey: "3M",
    preferredKey: "30D",
  });
  const chartRows = filterHistoryPointsForDeltaWindow(rows, selectedWindow);

  assert.deepEqual(windows.map((window) => window.key), STANDARD_DELTA_WINDOW_KEYS);
  assert.equal(selectedWindow.key, "3M");
  assert.equal(selectedWindow.startDate, "2026-04-26");
  assert.equal(selectedWindow.isSinceFirstAvailable, true);
  assert.equal(chartRows[0].date, "2026-04-26");
  assert.equal(chartRows.length, 37);
});

test("selected-window delta uses the selected period rather than a hardcoded default", () => {
  const rows = buildDailyRows(365, { startValue: 10 });
  const selected7D = getSelectedDeltaWindowFromHistory(rows, { selectedKey: "7D" }).selectedWindow;
  const selected30D = getSelectedDeltaWindowFromHistory(rows, { selectedKey: "30D" }).selectedWindow;

  assert.equal(selected7D.amount, 6);
  assert.equal(selected30D.amount, 29);
});

test("visible history metrics recompute current value and delta from the selected window", () => {
  const rows = buildDailyRows(31, { startDate: "2026-05-21", startValue: 100 });
  const selected7D = getSelectedDeltaWindowFromHistory(rows, { selectedKey: "7D" }).selectedWindow;
  const selected30D = getSelectedDeltaWindowFromHistory(rows, { selectedKey: "30D" }).selectedWindow;
  const metrics7D = getVisibleHistoryWindowMetrics(rows, selected7D);
  const metrics30D = getVisibleHistoryWindowMetrics(rows, selected30D);

  assert.equal(metrics7D.currentValue, 130);
  assert.equal(metrics7D.deltaAmount, 6);
  assert.equal(metrics30D.currentValue, 130);
  assert.equal(metrics30D.deltaAmount, 29);
  assert.notEqual(metrics7D.deltaAmount, metrics30D.deltaAmount);
});

test("visible history metrics change when the active value scope changes", () => {
  const standardRows = [
    { date: "2026-06-18", value: 100 },
    { date: "2026-06-19", value: 110 },
    { date: "2026-06-20", value: 130 },
  ];
  const hitsRows = [
    { date: "2026-06-18", value: 25 },
    { date: "2026-06-19", value: 30 },
    { date: "2026-06-20", value: 50 },
  ];
  const standardWindow = getSelectedDeltaWindowFromHistory(standardRows, { selectedKey: "lifetime" }).selectedWindow;
  const hitsWindow = getSelectedDeltaWindowFromHistory(hitsRows, { selectedKey: "lifetime" }).selectedWindow;
  const standardMetrics = getVisibleHistoryWindowMetrics(standardRows, standardWindow);
  const hitsMetrics = getVisibleHistoryWindowMetrics(hitsRows, hitsWindow);

  assert.equal(standardMetrics.currentValue, 130);
  assert.equal(standardMetrics.deltaAmount, 30);
  assert.equal(hitsMetrics.currentValue, 50);
  assert.equal(hitsMetrics.deltaAmount, 25);
});

test("visible history point changes use the first visible point in the selected window", () => {
  const rows = [
    { date: "2026-06-16", value: 100 },
    { date: "2026-06-17", value: 105 },
    { date: "2026-06-18", value: 103 },
    { date: "2026-06-19", value: 120 },
  ];
  const window = {
    startDate: "2026-06-17",
  };
  const metrics = getVisibleHistoryWindowMetrics(rows, window);

  assert.deepEqual(
    metrics.points.map((point) => [point.date, point.deltaFromPrevious]),
    [
      ["2026-06-17", null],
      ["2026-06-18", -2],
      ["2026-06-19", 15],
    ]
  );
  assert.equal(metrics.deltaAmount, 15);
});

test("visible history latest tooltip change equals selected-window delta", () => {
  const rows = buildDailyRows(31, { startDate: "2026-05-21", startValue: 100 });
  const selected30D = getSelectedDeltaWindowFromHistory(rows, { selectedKey: "30D" }).selectedWindow;
  const metrics = getVisibleHistoryWindowMetrics(rows, selected30D);
  const latestPoint = metrics.points[metrics.points.length - 1];

  assert.equal(latestPoint.deltaFromPrevious, metrics.deltaAmount);
  assert.equal(latestPoint.deltaPercentFromPrevious, metrics.deltaPercent);
});

test("visible history tooltip changes recalculate by active scope", () => {
  const checklistRows = [
    { date: "2026-06-18", value: 100 },
    { date: "2026-06-19", value: 110 },
    { date: "2026-06-20", value: 90 },
  ];
  const top10Rows = [
    { date: "2026-06-18", value: 30 },
    { date: "2026-06-19", value: 35 },
    { date: "2026-06-20", value: 45 },
  ];
  const checklistWindow = getSelectedDeltaWindowFromHistory(checklistRows, { selectedKey: "lifetime" }).selectedWindow;
  const top10Window = getSelectedDeltaWindowFromHistory(top10Rows, { selectedKey: "lifetime" }).selectedWindow;
  const checklistMetrics = getVisibleHistoryWindowMetrics(checklistRows, checklistWindow);
  const top10Metrics = getVisibleHistoryWindowMetrics(top10Rows, top10Window);
  const checklistLatest = checklistMetrics.points[checklistMetrics.points.length - 1];
  const top10Latest = top10Metrics.points[top10Metrics.points.length - 1];

  assert.equal(checklistLatest.deltaFromPrevious, -10);
  assert.equal(top10Latest.deltaFromPrevious, 15);
  assert.equal(top10Metrics.deltaAmount, 15);
});

test("visible history metrics return neutral values for missing series", () => {
  const metrics = getVisibleHistoryWindowMetrics([], { startDate: "2026-06-01" });

  assert.deepEqual(metrics.points, []);
  assert.equal(metrics.currentValue, null);
  assert.equal(metrics.deltaAmount, null);
  assert.equal(metrics.deltaPercent, null);
  assert.equal(metrics.firstPoint, null);
  assert.equal(metrics.latestPoint, null);
});

test("getPreferredDeltaWindowKey does not invent unavailable windows", () => {
  const windows = [{ key: "30D", label: "30D", amount: 10, percent: 4 }];

  assert.equal(getPreferredDeltaWindowKey(windows, "7D"), "30D");
  assert.equal(getPreferredDeltaWindowKey([], "7D"), null);
});

test("standard window definitions can be rendered independent of history availability", () => {
  assert.deepEqual(
    getStandardDeltaWindowDefinitions().map((window) => window.key),
    STANDARD_DELTA_WINDOW_KEYS
  );
});

test("top chase card delta chip no longer contains the nested period badge markup", () => {
  const source = readFileSync(new URL("../../components/explore/RipStatisticsPageClient.jsx", import.meta.url), "utf8");

  assert.equal(source.includes("absolute right-1.5 top-1 rounded-[4px]"), false);
  assert.equal(source.includes("pr-7 text-xs font-semibold leading-tight"), false);
});

test("delta trend triangle direction maps values consistently", () => {
  assert.equal(getDeltaTrendDirection(1), "up");
  assert.equal(getDeltaTrendDirection(-1), "down");
  assert.equal(getDeltaTrendDirection(0), "neutral");
  assert.equal(getDeltaTrendDirection(null), "neutral");
});
