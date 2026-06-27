import assert from "node:assert/strict";
import test from "node:test";

import {
  forwardFillDailyHistoryThroughToday,
  normalizeHistoryTrendPoint,
  patchLatestHistoryRowWithSummaryRatios,
  shouldUseSummaryRatioFallback,
} from "./packValueHistoryNormalization.mjs";
import {
  buildPerformanceTooltipRows,
  formatRatioWithCurrency,
} from "./performanceVsCostFormatting.mjs";
import { formatHistoryDate } from "./historyDateFormatting.mjs";

test("shouldUseSummaryRatioFallback returns true for null or zero latest ratio when summary ratio is non-zero", () => {
  assert.equal(shouldUseSummaryRatioFallback(null, 1.23), true);
  assert.equal(shouldUseSummaryRatioFallback(0, 1.23), true);
  assert.equal(shouldUseSummaryRatioFallback(0.0000002, 1.23), true);
  assert.equal(shouldUseSummaryRatioFallback(0.84, 1.23), false);
  assert.equal(shouldUseSummaryRatioFallback(0, 0), false);
});

test("patchLatestHistoryRowWithSummaryRatios uses summary mean/median ratios when latest historical ratios are zero placeholders", () => {
  const latestRow = {
    snapshotDate: "2026-06-09",
    meanCostRatio: 0,
    medianCostRatio: 0,
    meanValue: 0,
    medianValue: 0,
    p95CostRatio: 2.78,
    p95Value: 82.0,
  };

  const patched = patchLatestHistoryRowWithSummaryRatios(latestRow, {
    meanRatioSummary: 0.5,
    medianRatioSummary: 0.133,
    effectivePackCost: 29.47,
  });

  assert.equal(patched.meanCostRatio, 0.5);
  assert.equal(patched.medianCostRatio, 0.133);
  assert.ok(Math.abs(patched.meanValue - 14.735) < 0.001);
  assert.ok(Math.abs(patched.medianValue - 3.91951) < 0.001);
  assert.equal(patched.p95CostRatio, 2.78);
  assert.equal(patched.p95Value, 82.0);
});

test("normalizeHistoryTrendPoint resolves camelCase historical fields", () => {
  const point = normalizeHistoryTrendPoint(
    {
      snapshotDate: "2026-06-09",
      calculationRunId: "run-123",
      runCreatedAt: "2026-06-09T17:15:58.820087+00:00",
      packCost: 29.47,
      meanValueToCostRatio: 0.5,
      medianValueToCostRatio: 0.133,
      p95ValueToCostRatio: 2.7883,
    },
    0,
    null
  );

  assert.equal(point.snapshotDate, "2026-06-09");
  assert.equal(point.calculationRunId, "run-123");
  assert.equal(point.meanCostRatio, 0.5);
  assert.equal(point.medianCostRatio, 0.133);
  assert.equal(point.p95CostRatio, 2.7883);
});

test("normalizeHistoryTrendPoint resolves snake_case historical fields", () => {
  const point = normalizeHistoryTrendPoint(
    {
      snapshot_date: "2026-06-05",
      calculation_run_id: "run-456",
      run_created_at: "2026-06-05T17:15:58.820087+00:00",
      pack_cost: 29.47,
      mean_value_to_cost_ratio: 0.494,
      median_value_to_cost_ratio: 0.1282,
      p95_value_to_cost_ratio: 2.8173,
    },
    1,
    null
  );

  assert.equal(point.snapshotDate, "2026-06-05");
  assert.equal(point.calculationRunId, "run-456");
  assert.equal(point.meanCostRatio, 0.494);
  assert.equal(point.medianCostRatio, 0.1282);
  assert.equal(point.p95CostRatio, 2.8173);
});

test("formatHistoryDate keeps date-only snapshots on their calendar day", () => {
  assert.equal(
    formatHistoryDate("2026-06-17", { month: "short", day: "numeric" }),
    "Jun 17"
  );
  assert.equal(
    formatHistoryDate("2026-06-17", { year: "numeric", month: "short", day: "numeric" }),
    "Jun 17, 2026"
  );
});

test("forwardFillDailyHistoryThroughToday appends local today from latest actual point", () => {
  const points = forwardFillDailyHistoryThroughToday(
    [
      { date: "2026-06-16", value: 100 },
      { date: "2026-06-17", value: 123.45 },
    ],
    { todayDateKey: "2026-06-18" }
  );

  assert.equal(points.length, 3);
  assert.deepEqual(points.map((point) => point.date), ["2026-06-16", "2026-06-17", "2026-06-18"]);
  assert.equal(points[1].isCarriedForward, false);
  assert.equal(points[2].value, 123.45);
  assert.equal(points[2].isCarriedForward, true);
  assert.equal(points[2].sourceDate, "2026-06-17");
});

test("forwardFillDailyHistoryThroughToday leaves real current-day data in place", () => {
  const points = forwardFillDailyHistoryThroughToday(
    [
      { date: "2026-06-17", value: 123.45 },
      { date: "2026-06-18", value: 130 },
    ],
    { todayDateKey: "2026-06-18" }
  );

  assert.equal(points.length, 2);
  assert.equal(points[1].date, "2026-06-18");
  assert.equal(points[1].value, 130);
  assert.equal(points[1].isCarriedForward, false);
  assert.equal(points[1].sourceDate, null);
});

test("forwardFillDailyHistoryThroughToday fills every missing calendar day", () => {
  const points = forwardFillDailyHistoryThroughToday(
    [
      { date: "2026-06-20", value: 701.73 },
      { date: "2026-06-23", value: 707.56 },
      { date: "2026-06-24", value: 701.77 },
    ],
    { todayDateKey: "2026-06-26" }
  );

  assert.deepEqual(points.map((point) => point.date), [
    "2026-06-20",
    "2026-06-21",
    "2026-06-22",
    "2026-06-23",
    "2026-06-24",
    "2026-06-25",
    "2026-06-26",
  ]);
  assert.equal(points[1].value, 701.73);
  assert.equal(points[1].isCarriedForward, true);
  assert.equal(points[1].sourceDate, "2026-06-20");
  assert.equal(points[2].sourceDate, "2026-06-20");
  assert.equal(points[3].isCarriedForward, false);
  assert.equal(points[5].value, 701.77);
  assert.equal(points[5].sourceDate, "2026-06-24");
  assert.equal(points[6].sourceDate, "2026-06-24");
});

test("forwardFillDailyHistoryThroughToday does not overwrite observed rows", () => {
  const points = forwardFillDailyHistoryThroughToday(
    [
      { date: "2026-06-20", value: 701.73 },
      { date: "2026-06-21", value: 702.11 },
      { date: "2026-06-23", value: 707.56 },
    ],
    { todayDateKey: "2026-06-23" }
  );

  assert.deepEqual(points.map((point) => [point.date, point.value, point.isCarriedForward]), [
    ["2026-06-20", 701.73, false],
    ["2026-06-21", 702.11, false],
    ["2026-06-22", 702.11, true],
    ["2026-06-23", 707.56, false],
  ]);
});

test("forwardFillDailyHistoryThroughToday never carries before the first actual value", () => {
  const points = forwardFillDailyHistoryThroughToday(
    [
      { date: "2026-06-17", value: null },
    ],
    { todayDateKey: "2026-06-18" }
  );

  assert.equal(points.length, 1);
  assert.equal(points[0].date, "2026-06-17");
  assert.equal(points[0].isCarriedForward, false);
});

test("performance line-end labels can render ratio with dollar value", () => {
  assert.equal(formatRatioWithCurrency(1.11, 15.48), "1.11x ($15.48)");
  assert.equal(formatRatioWithCurrency(0.78, 10.93), "0.78x ($10.93)");
});

test("performance labels omit empty parentheses when dollar value is missing", () => {
  assert.equal(formatRatioWithCurrency(0.21, null), "0.21x");
  assert.equal(formatRatioWithCurrency(null, null), "\u2014");
});

test("performance endpoint labels render absolute return multiples, not deltas", () => {
  assert.equal(formatRatioWithCurrency(-1.11, -15.48), "1.11x ($15.48)");
  assert.equal(formatRatioWithCurrency(-0.78, 10.93), "0.78x ($10.93)");
});

test("performance tooltip rows put upside first and cost context last", () => {
  const rows = buildPerformanceTooltipRows(
    {
      snapshotDate: "2026-06-20",
      p95CostRatio: 1.11,
      p95Value: 15.48,
      meanCostRatio: 0.78,
      meanValue: 10.93,
      medianCostRatio: 0.21,
      medianValue: 2.96,
      packCost: 13.94,
    },
    null
  );

  assert.deepEqual(
    rows.map((row) => row.label),
    ["Big Hit Upside", "Expected Value", "Typical Return", "Break-even", "Pack Market Price"]
  );
  assert.deepEqual(
    rows.map((row) => row.value),
    ["1.11x ($15.48)", "0.78x ($10.93)", "0.21x ($2.96)", "1.00x", "$13.94"]
  );
});

test("performance tooltip rows do not expose carried-forward copy", () => {
  const rows = buildPerformanceTooltipRows(
    {
      isCarriedForward: true,
      sourceDate: "2026-06-18",
      meanCostRatio: 0.78,
      meanValue: 10.93,
      medianCostRatio: 0.21,
      medianValue: 2.96,
    },
    13.94
  );

  assert.equal(JSON.stringify(rows).includes("Carried forward"), false);
  assert.equal(JSON.stringify(rows).includes("sourceDate"), false);
});
