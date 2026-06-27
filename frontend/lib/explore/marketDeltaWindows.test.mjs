import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

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

function loadPokemonSetMarketClientForTests() {
  const source = readFileSync(new URL("../pokemon/pokemonSetMarketClient.js", import.meta.url), "utf8")
    .replace(/export\s+(async\s+function|function)\s+/g, "$1 ");
  const context = {
    console,
    process: { env: { NODE_ENV: "test" } },
    performance: { now: () => 0 },
  };
  vm.runInNewContext(
    `${source}\nglobalThis.__exports = { normalizeMarketDashboardPayload };`,
    context,
    { filename: "pokemonSetMarketClient.js" }
  );
  return context.__exports;
}

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

function buildMappedTopChaseRows() {
  return buildDailyRows(75, { startDate: "2026-04-11", startValue: 200 })
    .filter((point) => point.date !== "2026-04-12")
    .map((point) => ({
      date: point.date,
      marketPrice: point.value,
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

test("top chase card price history filters to distinct 7D, 30D, and 3M ranges from 365 loaded points", () => {
  const priceHistory = buildDailyRows(365, { startDate: "2025-06-25", startValue: 10 }).map((point) => ({
    date: point.date,
    marketPrice: point.value,
  }));

  const selected7D = getSelectedDeltaWindowFromHistory(priceHistory, {
    selectedKey: "7D",
    valueKey: "marketPrice",
  }).selectedWindow;
  const selected30D = getSelectedDeltaWindowFromHistory(priceHistory, {
    selectedKey: "30D",
    valueKey: "marketPrice",
  }).selectedWindow;
  const selected3M = getSelectedDeltaWindowFromHistory(priceHistory, {
    selectedKey: "3M",
    valueKey: "marketPrice",
  }).selectedWindow;

  const rows7D = filterHistoryPointsForDeltaWindow(priceHistory, selected7D);
  const rows30D = filterHistoryPointsForDeltaWindow(priceHistory, selected30D);
  const rows3M = filterHistoryPointsForDeltaWindow(priceHistory, selected3M);

  assert.equal(rows7D.length, 7);
  assert.equal(rows30D.length, 30);
  assert.equal(rows3M.length, 90);
  assert.equal(rows7D[0].date, "2026-06-18");
  assert.equal(rows30D[0].date, "2026-05-26");
  assert.equal(rows3M[0].date, "2026-03-27");
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

test("top chase raw observation history gives non-flat 30D and partial 3M deltas", () => {
  const priceHistory = buildDailyRows(75, { startDate: "2026-04-11", startValue: 100 }).map((point) => ({
    date: point.date,
    marketPrice: point.value,
    isObserved: true,
  }));

  const selected30D = getSelectedDeltaWindowFromHistory(priceHistory, {
    selectedKey: "30D",
    valueKey: "marketPrice",
  }).selectedWindow;
  const selected3M = getSelectedDeltaWindowFromHistory(priceHistory, {
    selectedKey: "3M",
    valueKey: "marketPrice",
  }).selectedWindow;
  const rows30D = filterHistoryPointsForDeltaWindow(priceHistory, selected30D);
  const rows3M = filterHistoryPointsForDeltaWindow(priceHistory, selected3M);
  const metrics30D = getVisibleHistoryWindowMetrics(priceHistory, selected30D, { valueKey: "marketPrice" });
  const metrics3M = getVisibleHistoryWindowMetrics(priceHistory, selected3M, { valueKey: "marketPrice" });

  assert.equal(selected30D.startDate, "2026-05-26");
  assert.equal(metrics30D.deltaAmount, 29);
  assert.notEqual(metrics30D.deltaAmount, 0);
  assert.equal(selected3M.startDate, "2026-04-11");
  assert.equal(selected3M.isSinceFirstAvailable, true);
  assert.equal(rows3M[0].date, "2026-04-11");
  assert.equal(rows3M.length, 75);
  assert.equal(metrics3M.deltaAmount, 74);
  assert.notEqual(metrics3M.deltaAmount, 0);
  assert.equal(rows30D.length, 30);
});

test("top chase normalization chooses mapped 74-point history over stale embedded 7-point card history", () => {
  const { normalizeMarketDashboardPayload } = loadPokemonSetMarketClientForTests();
  const embeddedHistory = buildDailyRows(7, { startDate: "2026-06-18", startValue: 260 }).map((point) => ({
    date: point.date,
    marketPrice: point.value,
  }));
  const mappedHistory = buildMappedTopChaseRows();

  const normalized = normalizeMarketDashboardPayload({
    set: { id: "ascended-heroes", name: "Ascended Heroes" },
    topChaseCards: [
      {
        cardId: "mega-gengar-ex",
        cardVariantId: "variant-mega-gengar-ex",
        name: "Mega Gengar ex",
        priceHistory: embeddedHistory,
      },
    ],
    topChaseCardHistories: {
      "variant-mega-gengar-ex": mappedHistory,
    },
  });
  const card = normalized.topChaseCards[0];

  assert.equal(card.embeddedHistoryPointCount, 7);
  assert.equal(card.mappedHistoryPointCount, 74);
  assert.equal(card.selectedHistoryPointCount, 74);
  assert.equal(card.selectedHistorySource, "top_chase_card_histories");
  assert.equal(card.selectedHistoryStartDate, "2026-04-11");
  assert.equal(card.selectedHistoryEndDate, "2026-06-24");
  assert.equal(card.priceHistory.length, 74);
  assert.equal(card.price_history, card.priceHistory);
});

test("top chase normalized mapped history renders 30D and partial 3M slices from full observed range", () => {
  const { normalizeMarketDashboardPayload } = loadPokemonSetMarketClientForTests();
  const normalized = normalizeMarketDashboardPayload({
    topChaseCards: [
      {
        cardId: "mega-gengar-ex",
        cardVariantId: "variant-mega-gengar-ex",
        name: "Mega Gengar ex",
        priceHistory: buildDailyRows(7, { startDate: "2026-06-18", startValue: 260 }).map((point) => ({
          date: point.date,
          marketPrice: point.value,
        })),
      },
    ],
    topChaseCardHistories: {
      "variant-mega-gengar-ex": buildMappedTopChaseRows(),
    },
  });
  const priceHistory = normalized.topChaseCards[0].priceHistory;
  const selected30D = getSelectedDeltaWindowFromHistory(priceHistory, {
    selectedKey: "30D",
    valueKey: "marketPrice",
  }).selectedWindow;
  const selected3M = getSelectedDeltaWindowFromHistory(priceHistory, {
    selectedKey: "3M",
    valueKey: "marketPrice",
  }).selectedWindow;
  const rows30D = filterHistoryPointsForDeltaWindow(priceHistory, selected30D);
  const rows3M = filterHistoryPointsForDeltaWindow(priceHistory, selected3M);

  assert.equal(selected30D.startDate, "2026-05-26");
  assert.equal(rows30D.length, 30);
  assert.equal(rows30D[0].date, "2026-05-26");
  assert.equal(rows30D.at(-1).date, "2026-06-24");
  assert.equal(selected3M.startDate, "2026-04-11");
  assert.equal(selected3M.isSinceFirstAvailable, true);
  assert.equal(rows3M.length, 74);
  assert.equal(rows3M[0].date, "2026-04-11");
  assert.equal(rows3M.at(-1).date, "2026-06-24");
});

test("1D window uses previous valid daily point rather than latest point", () => {
  const rows = [
    { date: "2026-06-20", marketPrice: 100 },
    { date: "2026-06-21", marketPrice: 105 },
    { date: "2026-06-22", marketPrice: 110 },
    { date: "2026-06-23", marketPrice: 120 },
    { date: "2026-06-24", marketPrice: 125 },
  ];
  const selectedWindow = getSelectedDeltaWindowFromHistory(rows, {
    selectedKey: "1D",
    valueKey: "marketPrice",
  }).selectedWindow;

  assert.equal(selectedWindow.key, "1D");
  assert.equal(selectedWindow.startDate, "2026-06-23");
  assert.equal(selectedWindow.amount, 5);
  assert.ok(Math.abs(selectedWindow.percent - (5 / 120) * 100) < 0.0001);
});

test("1D rendered slice includes previous and latest points", () => {
  const rows = [
    { date: "2026-06-20", marketPrice: 100 },
    { date: "2026-06-21", marketPrice: 105 },
    { date: "2026-06-22", marketPrice: 110 },
    { date: "2026-06-23", marketPrice: 120 },
    { date: "2026-06-24", marketPrice: 125 },
  ];
  const selectedWindow = getSelectedDeltaWindowFromHistory(rows, {
    selectedKey: "1D",
    valueKey: "marketPrice",
  }).selectedWindow;
  const chartRows = filterHistoryPointsForDeltaWindow(rows, selectedWindow);

  assert.equal(chartRows.length, 2);
  assert.equal(chartRows[0].date, "2026-06-23");
  assert.equal(chartRows.at(-1).date, "2026-06-24");
});

test("visible 1D metrics use previous-to-latest delta", () => {
  const rows = [
    { date: "2026-06-20", marketPrice: 100 },
    { date: "2026-06-21", marketPrice: 105 },
    { date: "2026-06-22", marketPrice: 110 },
    { date: "2026-06-23", marketPrice: 120 },
    { date: "2026-06-24", marketPrice: 125 },
  ];
  const selectedWindow = getSelectedDeltaWindowFromHistory(rows, {
    selectedKey: "1D",
    valueKey: "marketPrice",
  }).selectedWindow;
  const metrics = getVisibleHistoryWindowMetrics(rows, selectedWindow, { valueKey: "marketPrice" });
  const latestPoint = metrics.points.at(-1);

  assert.equal(metrics.currentValue, 125);
  assert.equal(metrics.deltaAmount, 5);
  assert.equal(latestPoint.deltaFromPrevious, 5);
  assert.equal(latestPoint.deltaPercentFromPrevious, metrics.deltaPercent);
});

test("1D neutral when only one valid point exists", () => {
  const rows = [{ date: "2026-06-24", marketPrice: 125 }];
  const selectedWindow = getSelectedDeltaWindowFromHistory(rows, {
    selectedKey: "1D",
    valueKey: "marketPrice",
  }).selectedWindow;
  const metrics = getVisibleHistoryWindowMetrics(rows, selectedWindow, { valueKey: "marketPrice" });

  assert.equal(selectedWindow, null);
  assert.equal(metrics.currentValue, 125);
  assert.equal(metrics.deltaAmount, null);
  assert.equal(metrics.deltaPercent, null);
});

test("top chase 1D can ignore trailing carried-forward duplicate points", () => {
  const rows = [
    { date: "2026-06-20", marketPrice: 100 },
    { date: "2026-06-21", marketPrice: 105 },
    { date: "2026-06-22", marketPrice: 110 },
    { date: "2026-06-23", marketPrice: 120 },
    { date: "2026-06-24", marketPrice: 120, isCarriedForward: true, sourceDate: "2026-06-23" },
  ];
  const selectedWindow = getSelectedDeltaWindowFromHistory(rows, {
    selectedKey: "1D",
    valueKey: "marketPrice",
    preferActualPointsForOneDay: true,
  }).selectedWindow;
  const chartRows = filterHistoryPointsForDeltaWindow(rows, selectedWindow);

  assert.equal(selectedWindow.startDate, "2026-06-22");
  assert.equal(selectedWindow.endDate, "2026-06-23");
  assert.equal(selectedWindow.amount, 10);
  assert.equal(chartRows.length, 2);
  assert.equal(chartRows[0].date, "2026-06-22");
  assert.equal(chartRows.at(-1).date, "2026-06-23");
});

test("set value windows can anchor to latest observed point instead of carried-forward today", () => {
  const rows = [
    { date: "2026-06-20", setValue: 729.07 },
    { date: "2026-06-23", setValue: 732.87 },
    { date: "2026-06-24", setValue: 734.52 },
    { date: "2026-06-25", setValue: 734.52, isCarriedForward: true, sourceDate: "2026-06-24" },
    { date: "2026-06-26", setValue: 734.52, isCarriedForward: true, sourceDate: "2026-06-24" },
  ];

  const selected1D = getSelectedDeltaWindowFromHistory(rows, {
    selectedKey: "1D",
    valueKey: "setValue",
    preferObservedPoints: true,
  }).selectedWindow;
  const selected7D = getSelectedDeltaWindowFromHistory(rows, {
    selectedKey: "7D",
    valueKey: "setValue",
    preferObservedPoints: true,
  }).selectedWindow;
  const metrics1D = getVisibleHistoryWindowMetrics(rows, selected1D, {
    valueKey: "setValue",
    preferObservedPoints: true,
  });

  assert.equal(selected1D.startDate, "2026-06-23");
  assert.equal(selected1D.endDate, "2026-06-24");
  assert.equal(Number(selected1D.amount.toFixed(2)), 1.65);
  assert.equal(selected7D.endDate, "2026-06-24");
  assert.equal(metrics1D.latestPoint.date, "2026-06-24");
  assert.equal(Number(metrics1D.deltaAmount.toFixed(2)), 1.65);
});

test("observed-point windows do not report zero when only carried-forward duplicates trail one observed point", () => {
  const rows = [
    { date: "2026-06-24", setValue: 734.52 },
    { date: "2026-06-25", setValue: 734.52, isCarriedForward: true, sourceDate: "2026-06-24" },
    { date: "2026-06-26", setValue: 734.52, isCarriedForward: true, sourceDate: "2026-06-24" },
  ];
  const selectedWindow = getSelectedDeltaWindowFromHistory(rows, {
    selectedKey: "1D",
    valueKey: "setValue",
    preferObservedPoints: true,
  }).selectedWindow;
  const metrics = getVisibleHistoryWindowMetrics(rows, selectedWindow, {
    valueKey: "setValue",
    preferObservedPoints: true,
  });

  assert.equal(selectedWindow, null);
  assert.equal(metrics.currentValue, 734.52);
  assert.equal(metrics.latestPoint.date, "2026-06-24");
  assert.equal(metrics.deltaAmount, null);
  assert.equal(metrics.deltaPercent, null);
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
