import assert from "node:assert/strict";
import test from "node:test";

import {
  getLatestRealPerformanceDate,
  getPerformanceHistoryDate,
  getPerformanceHistoryRunTimestamp,
  isCarriedForwardPerformancePoint,
  mergePerformanceHistories,
  selectOverviewPerformanceHistoryState,
} from "./performanceHistorySelector.mjs";

function marketRow(date, overrides = {}) {
  return {
    date,
    snapshot_date: date,
    snapshotDate: date,
    pack_cost: 5.25,
    packCost: 5.25,
    mean_value_to_cost_ratio: 0.9,
    meanValueToCostRatio: 0.9,
    median_value_to_cost_ratio: 0.4,
    medianValueToCostRatio: 0.4,
    p95_value_to_cost_ratio: 2.4,
    p95ValueToCostRatio: 2.4,
    run_created_at: `${date}T12:00:00+00:00`,
    runCreatedAt: `${date}T12:00:00+00:00`,
    ...overrides,
  };
}

function setPageRow(date, overrides = {}) {
  return {
    snapshot_date: date,
    pack_cost: 5.25,
    mean_value_to_cost_ratio: 0.88,
    median_value_to_cost_ratio: 0.39,
    p95_value_to_cost_ratio: 2.3,
    run_created_at: `${date}T06:00:00+00:00`,
    ...overrides,
  };
}

function payloadWithHistory(history, { marketAsOfDate = null, generationId = null } = {}) {
  return {
    performanceVsCostHistory: history,
    meta: {
      snapshot: {
        marketAsOfDate,
        generationId,
      },
    },
  };
}

test("row helpers resolve dates, run timestamps, and carried-forward flags across key spellings", () => {
  assert.equal(getPerformanceHistoryDate({ snapshot_date: "2026-07-09" }), "2026-07-09");
  assert.equal(getPerformanceHistoryDate({ snapshotDate: "2026-07-09T04:00:00+00:00" }), "2026-07-09");
  assert.equal(getPerformanceHistoryDate({ date: "2026-07-09" }), "2026-07-09");
  assert.equal(getPerformanceHistoryDate({ source_date: "2026-07-01" }), "2026-07-01");
  assert.equal(getPerformanceHistoryDate({}), null);
  assert.equal(getPerformanceHistoryDate(null), null);

  assert.equal(
    getPerformanceHistoryRunTimestamp({ run_created_at: "2026-07-09T12:00:00+00:00" }),
    Date.parse("2026-07-09T12:00:00+00:00")
  );
  assert.equal(
    getPerformanceHistoryRunTimestamp({ runAt: "2026-07-09T12:00:00+00:00" }),
    Date.parse("2026-07-09T12:00:00+00:00")
  );
  assert.equal(getPerformanceHistoryRunTimestamp({ run_created_at: "not-a-date" }), null);
  assert.equal(getPerformanceHistoryRunTimestamp({}), null);

  assert.equal(isCarriedForwardPerformancePoint({ is_carried_forward: true }), true);
  assert.equal(isCarriedForwardPerformancePoint({ isCarriedForward: true }), true);
  assert.equal(isCarriedForwardPerformancePoint({ isCarriedForward: false }), false);
  assert.equal(isCarriedForwardPerformancePoint({}), false);
});

// TEST 1 — stale set-page (ends June 30), fresh market history (through July 9).
test("merge keeps fresh market rows past a stale set-page tail and reports the real latest date", () => {
  const setPageHistory = [setPageRow("2026-06-28"), setPageRow("2026-06-29"), setPageRow("2026-06-30")];
  const marketHistory = [
    marketRow("2026-06-30"),
    marketRow("2026-07-05"),
    marketRow("2026-07-08"),
    marketRow("2026-07-09"),
  ];

  const merged = mergePerformanceHistories({ setPageHistory, marketHistory });
  const dates = merged.map((row) => row.snapshotDate);

  assert.deepEqual(dates, ["2026-06-28", "2026-06-29", "2026-06-30", "2026-07-05", "2026-07-08", "2026-07-09"]);
  assert.equal(getLatestRealPerformanceDate(merged), "2026-07-09");
  // July rows must be the real market rows, not June 30 values repeated.
  const july9 = merged.find((row) => row.snapshotDate === "2026-07-09");
  assert.equal(july9.mean_value_to_cost_ratio, 0.9);
});

// TEST 2 — market older, set-page newer: newer set-page dates remain present.
test("merge preserves newer set-page dates when the market history is the stale side", () => {
  const setPageHistory = [setPageRow("2026-07-01"), setPageRow("2026-07-02"), setPageRow("2026-07-03")];
  const marketHistory = [marketRow("2026-06-29"), marketRow("2026-06-30")];

  const merged = mergePerformanceHistories({ setPageHistory, marketHistory });
  const dates = merged.map((row) => row.snapshotDate);

  assert.deepEqual(dates, ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03"]);
  assert.equal(getLatestRealPerformanceDate(merged), "2026-07-03");
});

// TEST 3 — overlapping date: later run timestamp wins.
test("merge resolves an overlapping date to the row with the later run timestamp", () => {
  const setPageHistory = [
    setPageRow("2026-07-01", { run_created_at: "2026-07-01T18:30:00+00:00", mean_value_to_cost_ratio: 0.95 }),
  ];
  const marketHistory = [
    marketRow("2026-07-01", {
      run_created_at: "2026-07-01T06:00:00+00:00",
      runCreatedAt: "2026-07-01T06:00:00+00:00",
      mean_value_to_cost_ratio: 0.7,
      meanValueToCostRatio: 0.7,
    }),
  ];

  const merged = mergePerformanceHistories({ setPageHistory, marketHistory });
  assert.equal(merged.length, 1);
  assert.equal(merged[0].mean_value_to_cost_ratio, 0.95, "the later 18:30 set-page run must win over the 06:00 market run");
});

// TEST 4 — incomplete overlapping row: the more complete row wins when
// timestamps do not resolve it.
test("merge resolves an overlapping date to the more complete row when run timestamps tie or are missing", () => {
  const sparse = {
    snapshot_date: "2026-07-02",
    mean_value_to_cost_ratio: 0.8,
  };
  const complete = marketRow("2026-07-02", { run_created_at: null, runCreatedAt: null });

  const merged = mergePerformanceHistories({ setPageHistory: [sparse], marketHistory: [complete] });
  assert.equal(merged.length, 1);
  assert.equal(merged[0].p95_value_to_cost_ratio, 2.4, "the complete market row must win");

  // Same shape mirrored: complete set-page row vs sparse market row.
  const completeSetPage = setPageRow("2026-07-02", { run_created_at: null });
  const sparseMarket = { snapshot_date: "2026-07-02", mean_value_to_cost_ratio: 0.5 };
  const mirrored = mergePerformanceHistories({ setPageHistory: [completeSetPage], marketHistory: [sparseMarket] });
  assert.equal(mirrored.length, 1);
  assert.equal(mirrored[0].mean_value_to_cost_ratio, 0.88, "the complete set-page row must win over a sparse market row");
});

// TEST 5 — carried-forward rows stay usable for continuity but never define
// freshness and never override a real row for the same date.
test("carried-forward rows never override real rows and never count as the latest real date", () => {
  const realJuly7 = marketRow("2026-07-07");
  const carriedJuly7 = marketRow("2026-07-07", {
    isCarriedForward: true,
    is_carried_forward: true,
    sourceDate: "2026-06-30",
    source_date: "2026-06-30",
    mean_value_to_cost_ratio: 0.1,
    meanValueToCostRatio: 0.1,
    run_created_at: "2026-07-08T23:59:00+00:00",
    runCreatedAt: "2026-07-08T23:59:00+00:00",
  });
  const carriedJuly8 = marketRow("2026-07-08", {
    isCarriedForward: true,
    is_carried_forward: true,
    sourceDate: "2026-07-07",
    source_date: "2026-07-07",
  });

  const merged = mergePerformanceHistories({
    setPageHistory: [carriedJuly7],
    marketHistory: [realJuly7, carriedJuly8],
  });

  const july7 = merged.find((row) => row.snapshotDate === "2026-07-07");
  assert.equal(july7.mean_value_to_cost_ratio, 0.9, "a real row must beat a carried row even with a later run timestamp");
  assert.equal(isCarriedForwardPerformancePoint(july7), false);

  // The intentionally provided carried July 8 row remains for continuity...
  const july8 = merged.find((row) => row.snapshotDate === "2026-07-08");
  assert.ok(july8, "an intentionally provided carried row stays in the merged series");
  assert.equal(isCarriedForwardPerformancePoint(july8), true);
  // ...but never determines the latest real date.
  assert.equal(getLatestRealPerformanceDate(merged), "2026-07-07");
});

// TEST 6 — empty/null histories are safe.
test("merge handles empty, null, and non-array histories without crashing", () => {
  assert.deepEqual(mergePerformanceHistories({}), []);
  assert.deepEqual(mergePerformanceHistories(), []);
  assert.deepEqual(mergePerformanceHistories({ setPageHistory: null, marketHistory: undefined }), []);
  assert.deepEqual(mergePerformanceHistories({ setPageHistory: "nope", marketHistory: 7 }), []);

  const onlyMarket = mergePerformanceHistories({ setPageHistory: [], marketHistory: [marketRow("2026-07-09")] });
  assert.equal(onlyMarket.length, 1);
  assert.equal(onlyMarket[0].snapshotDate, "2026-07-09");

  const onlySetPage = mergePerformanceHistories({ setPageHistory: [setPageRow("2026-06-30")], marketHistory: [] });
  assert.equal(onlySetPage.length, 1);
  assert.equal(onlySetPage[0].snapshotDate, "2026-06-30");

  // Rows without any usable date are excluded, not crashed on.
  const withInvalid = mergePerformanceHistories({
    setPageHistory: [null, "junk", { mean_value_to_cost_ratio: 1 }, setPageRow("2026-06-30")],
    marketHistory: [{ snapshot_date: "not-a-date" }],
  });
  assert.equal(withInvalid.length, 1);
  assert.equal(getLatestRealPerformanceDate([]), null);
  assert.equal(getLatestRealPerformanceDate(null), null);
});

// TEST 7 — input immutability.
test("merge does not mutate either source array or their rows", () => {
  const setPageHistory = [setPageRow("2026-06-30")];
  const marketHistory = [marketRow("2026-06-30"), marketRow("2026-07-09")];
  const setPageSnapshot = JSON.stringify(setPageHistory);
  const marketSnapshot = JSON.stringify(marketHistory);

  const merged = mergePerformanceHistories({ setPageHistory, marketHistory });
  // Mutating the output must not reach back into the sources.
  merged.forEach((row) => {
    row.mean_value_to_cost_ratio = -1;
    row.snapshotDate = "1999-01-01";
  });

  assert.equal(JSON.stringify(setPageHistory), setPageSnapshot, "setPageHistory must be unchanged");
  assert.equal(JSON.stringify(marketHistory), marketSnapshot, "marketHistory must be unchanged");
});

test("overview history state: empty seed + live loading stays loading (empty copy not eligible)", () => {
  const seedPayload = payloadWithHistory([], { marketAsOfDate: "2026-07-09", generationId: "seed-a" });
  const selected = selectOverviewPerformanceHistoryState({
    seedPayload,
    livePayload: null,
    liveStatus: "loading",
    liveError: null,
    insightsHistory: [],
  });

  assert.equal(selected.status, "loading");
  assert.equal(selected.emptyStateEligible, false);
  assert.equal(selected.history.length, 0);
});

test("overview history state: valid seed + live loading stays renderable as success_stale", () => {
  const seedPayload = payloadWithHistory([marketRow("2026-07-08"), marketRow("2026-07-09")]);
  const selected = selectOverviewPerformanceHistoryState({
    seedPayload,
    livePayload: null,
    liveStatus: "loading",
    liveError: null,
    insightsHistory: [],
  });

  assert.equal(selected.status, "success_stale");
  assert.equal(selected.history.length, 2);
});

test("overview history state: empty newer seed does not beat valid older live history", () => {
  const seedPayload = payloadWithHistory([], { marketAsOfDate: "2026-07-12", generationId: "seed-new" });
  const livePayload = payloadWithHistory([marketRow("2026-07-08"), marketRow("2026-07-09")], {
    marketAsOfDate: "2026-07-09",
    generationId: "live-older",
  });
  const selected = selectOverviewPerformanceHistoryState({
    seedPayload,
    livePayload,
    liveStatus: "success",
    liveError: null,
    insightsHistory: [],
  });

  assert.equal(selected.status, "success");
  assert.deepEqual(
    selected.history.map((row) => row.snapshotDate),
    ["2026-07-08", "2026-07-09"]
  );
});

test("overview history state: valid seed + valid live merge by existing duplicate-date rules", () => {
  const seedPayload = payloadWithHistory([
    setPageRow("2026-07-08", { run_created_at: "2026-07-08T08:00:00+00:00", mean_value_to_cost_ratio: 0.7 }),
    setPageRow("2026-07-09", { run_created_at: "2026-07-09T08:00:00+00:00", mean_value_to_cost_ratio: 0.8 }),
  ]);
  const livePayload = payloadWithHistory([
    marketRow("2026-07-09", {
      run_created_at: "2026-07-09T12:00:00+00:00",
      runCreatedAt: "2026-07-09T12:00:00+00:00",
      mean_value_to_cost_ratio: 0.95,
      meanValueToCostRatio: 0.95,
    }),
    marketRow("2026-07-10"),
  ]);

  const selected = selectOverviewPerformanceHistoryState({
    seedPayload,
    livePayload,
    liveStatus: "success",
    liveError: null,
    insightsHistory: [],
  });

  assert.equal(selected.status, "success");
  assert.deepEqual(
    selected.history.map((row) => row.snapshotDate),
    ["2026-07-08", "2026-07-09", "2026-07-10"]
  );
  const july9 = selected.history.find((row) => row.snapshotDate === "2026-07-09");
  assert.equal(july9.mean_value_to_cost_ratio, 0.95);
});

test("overview history state: no seed + live success with no history settles empty", () => {
  const selected = selectOverviewPerformanceHistoryState({
    seedPayload: null,
    livePayload: payloadWithHistory([]),
    liveStatus: "success",
    liveError: null,
    insightsHistory: [],
  });

  assert.equal(selected.status, "empty");
  assert.equal(selected.emptyStateEligible, true);
});

test("overview history state: no seed + live error with no fallback returns error", () => {
  const selected = selectOverviewPerformanceHistoryState({
    seedPayload: null,
    livePayload: null,
    liveStatus: "error",
    liveError: "request failed",
    insightsHistory: [],
  });

  assert.equal(selected.status, "error");
});

test("overview history state: valid seed + live error keeps seed visible as success_stale", () => {
  const selected = selectOverviewPerformanceHistoryState({
    seedPayload: payloadWithHistory([marketRow("2026-07-08"), marketRow("2026-07-09")]),
    livePayload: null,
    liveStatus: "error",
    liveError: "request failed",
    insightsHistory: [],
  });

  assert.equal(selected.status, "success_stale");
  assert.equal(selected.history.length, 2);
});

test("overview history state: insights absent still renders from overview history", () => {
  const selected = selectOverviewPerformanceHistoryState({
    seedPayload: null,
    livePayload: payloadWithHistory([marketRow("2026-07-08"), marketRow("2026-07-09")]),
    liveStatus: "success",
    liveError: null,
    insightsHistory: [],
  });

  assert.equal(selected.status, "success");
  assert.equal(selected.history.length, 2);
});

test("overview history state: insights history supplements overview instead of controlling it", () => {
  const selected = selectOverviewPerformanceHistoryState({
    seedPayload: null,
    livePayload: payloadWithHistory([marketRow("2026-07-09"), marketRow("2026-07-10")]),
    liveStatus: "success",
    liveError: null,
    insightsHistory: [setPageRow("2026-07-08")],
  });

  assert.equal(selected.status, "success");
  assert.deepEqual(
    selected.history.map((row) => row.snapshotDate),
    ["2026-07-08", "2026-07-09", "2026-07-10"]
  );
});

test("overview history state: points beyond marketAsOfDate are excluded", () => {
  const selected = selectOverviewPerformanceHistoryState({
    seedPayload: null,
    livePayload: payloadWithHistory([marketRow("2026-07-08"), marketRow("2026-07-09"), marketRow("2026-07-10")], {
      marketAsOfDate: "2026-07-09",
      generationId: "live-cutoff",
    }),
    liveStatus: "success",
    liveError: null,
    insightsHistory: [],
  });

  assert.deepEqual(
    selected.history.map((row) => row.snapshotDate),
    ["2026-07-08", "2026-07-09"]
  );
  assert.equal(selected.diagnostics.marketAsOfDate, "2026-07-09");
});
