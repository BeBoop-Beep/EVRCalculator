import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

import { buildOpeningSimulationFreshness } from "./openingSimulationFreshness.mjs";
import { forwardFillDailyHistoryThroughDate } from "./packValueHistoryNormalization.mjs";
import { getLatestRealPerformanceDate, mergePerformanceHistories } from "./performanceHistorySelector.mjs";

test("a current simulation date produces no stale warning", () => {
  const freshness = buildOpeningSimulationFreshness({
    latestRealSimulationDate: "2026-08-01",
    marketAsOfDate: "2026-08-01",
  });
  assert.equal(freshness.isStale, false);
  assert.equal(freshness.label, "Simulation as of Aug 1, 2026");
  assert.ok(!freshness.label.includes("market data through"));
});

test("a current market date with an older simulation date is stated truthfully", () => {
  // The exact production divergence.
  const freshness = buildOpeningSimulationFreshness({
    latestRealSimulationDate: "2026-07-27",
    marketAsOfDate: "2026-08-01",
  });
  assert.equal(freshness.isStale, true);
  assert.equal(freshness.simulationAsOfDate, "2026-07-27");
  assert.equal(freshness.label, "Simulation as of Jul 27, 2026 · market data through Aug 1, 2026");
  assert.match(freshness.accessibleLabel, /last simulated on Jul 27, 2026/);
  assert.match(freshness.accessibleLabel, /current through Aug 1, 2026/);
});

test("the freshness line names dates only, never pipeline internals", () => {
  const freshness = buildOpeningSimulationFreshness({
    latestRealSimulationDate: "2026-07-27",
    marketAsOfDate: "2026-08-01",
  });
  for (const forbidden of [
    "snapshot",
    "calculation_history_trend",
    "simulation_run_summary",
    "carried",
    "fallback",
    "pipeline",
    "batch",
  ]) {
    assert.ok(
      !freshness.label.toLowerCase().includes(forbidden),
      `freshness copy leaked "${forbidden}"`
    );
  }
});

test("no simulation date yields no line at all rather than a misleading one", () => {
  const freshness = buildOpeningSimulationFreshness({
    latestRealSimulationDate: null,
    marketAsOfDate: "2026-08-01",
  });
  assert.equal(freshness.label, null);
  assert.equal(freshness.isStale, false);
});

test("the latest real simulation date ignores carried-forward points", () => {
  const history = [
    { date: "2026-07-26", mean_value_to_cost_ratio: 0.5 },
    { date: "2026-07-27", mean_value_to_cost_ratio: 0.51 },
    { date: "2026-07-28", mean_value_to_cost_ratio: 0.51, isCarriedForward: true },
    { date: "2026-08-01", mean_value_to_cost_ratio: 0.51, is_carried_forward: true },
  ];
  assert.equal(getLatestRealPerformanceDate(history), "2026-07-27");

  const freshness = buildOpeningSimulationFreshness({
    latestRealSimulationDate: getLatestRealPerformanceDate(history),
    marketAsOfDate: "2026-08-01",
  });
  assert.equal(freshness.isStale, true);
});

test("a real observation always displaces a carried-forward copy for the same date", () => {
  const merged = mergePerformanceHistories({
    setPageHistory: [{ date: "2026-07-27", mean_value_to_cost_ratio: 0.5, isCarriedForward: true }],
    marketHistory: [{ date: "2026-07-27", mean_value_to_cost_ratio: 0.9 }],
  });
  assert.equal(merged.length, 1);
  assert.equal(merged[0].isCarriedForward, undefined);
  assert.equal(getLatestRealPerformanceDate(merged), "2026-07-27");
});

test("the simulation series is not carried forward past its last real run", () => {
  // Preferred behavior: the observed line ends on the last simulated day. It
  // must not be extended to the market date, which would draw days on which no
  // simulation was executed.
  const rows = [
    { snapshotDate: "2026-07-26", meanCostRatio: 0.5 },
    { snapshotDate: "2026-07-27", meanCostRatio: 0.51 },
  ];
  const filled = forwardFillDailyHistoryThroughDate(rows, {
    dateField: "snapshotDate",
    valueKeys: ["meanCostRatio", "medianCostRatio", "p95CostRatio"],
    endDateKey: "2026-08-01",
    stopFillAtLatestObservation: true,
  });
  assert.equal(filled.at(-1).snapshotDate, "2026-07-27");
  assert.ok(filled.every((row) => !row.isCarriedForward));
});

test("interior gaps between real runs are still filled", () => {
  const rows = [
    { snapshotDate: "2026-07-24", meanCostRatio: 0.5 },
    { snapshotDate: "2026-07-27", meanCostRatio: 0.51 },
  ];
  const filled = forwardFillDailyHistoryThroughDate(rows, {
    dateField: "snapshotDate",
    valueKeys: ["meanCostRatio"],
    endDateKey: "2026-08-01",
    stopFillAtLatestObservation: true,
  });
  assert.deepEqual(
    filled.map((row) => row.snapshotDate),
    ["2026-07-24", "2026-07-25", "2026-07-26", "2026-07-27"]
  );
  assert.deepEqual(
    filled.map((row) => Boolean(row.isCarriedForward)),
    [false, true, true, false]
  );
});

test("market series keep carrying to the market date by default", () => {
  // The opt-out must not change price-series behavior: today's price really is
  // the last observed price.
  const filled = forwardFillDailyHistoryThroughDate(
    [{ date: "2026-07-30", value: 10 }],
    { dateField: "date", valueKeys: ["value"], endDateKey: "2026-08-01" }
  );
  assert.equal(filled.at(-1).date, "2026-08-01");
  assert.equal(filled.at(-1).isCarriedForward, true);
});

test("the Overview section renders the freshness line from the shared helper", () => {
  const source = fs
    .readFileSync(path.join(import.meta.dirname, "RipStatisticsPageClient.jsx"), "utf8")
    .replace(/\r\n/g, "\n");
  assert.ok(source.includes("buildOpeningSimulationFreshness({"));
  assert.ok(source.includes("data-opening-simulation-freshness"));
  assert.ok(source.includes("latestRealSimulationDate: latestRealPerformanceDate,"));
  assert.ok(
    source.includes("stopFillAtLatestObservation: true") === false,
    "the chart owns the fill flag, not the page client"
  );
});

test("the Opening Profit vs Cost chart stops its fill at the last real run", () => {
  const source = fs
    .readFileSync(path.join(import.meta.dirname, "PackValueHistoryChart.jsx"), "utf8")
    .replace(/\r\n/g, "\n");
  assert.ok(source.includes("stopFillAtLatestObservation: true"));
});
