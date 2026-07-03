import assert from "node:assert/strict";
import test from "node:test";

import { normalizeMarketDashboardPayload } from "./pokemonSetMarketClient.js";

// ---------------------------------------------------------------------------
// normalizeSimulationPerformanceHistory (via normalizeMarketDashboardPayload)
// ---------------------------------------------------------------------------

function makeSimPoint(overrides = {}) {
  return {
    snapshot_date: "2026-06-20",
    calculation_run_id: "run-abc",
    run_created_at: "2026-06-20T12:00:00+00:00",
    pack_cost: 5.0,
    mean_value: 3.6,
    median_value: 2.25,
    mean_value_to_cost_ratio: 0.72,
    simulated_mean_pack_value_vs_pack_cost: 0.72,
    median_value_to_cost_ratio: 0.45,
    simulated_median_pack_value_vs_pack_cost: 0.45,
    p95_value_to_cost_ratio: 3.1,
    source: "calculation_history_trend+simulation_run_summary",
    provider: "calculation_history_trend+simulation_run_summary",
    isCarriedForward: false,
    is_carried_forward: false,
    ...overrides,
  };
}

function makeDashboardPayload({ performanceVsCostHistory = [], setValueHistories = {} } = {}) {
  return {
    set: { id: "set-1", name: "Test Set", slug: "testSet" },
    window: "365d",
    setValueHistoriesByScope: setValueHistories,
    set_value_histories_by_scope: setValueHistories,
    performanceVsCostHistory,
    performance_vs_cost_history: performanceVsCostHistory,
    topChaseCards: [],
    topChaseCardHistories: {},
    marketMovers: {},
    availableScopes: [],
    latestMarketDate: null,
    meta: { sources: {}, warnings: [] },
  };
}

test("normalizeMarketDashboardPayload preserves simulation ratio fields in performanceVsCostHistory", () => {
  const payload = makeDashboardPayload({
    performanceVsCostHistory: [makeSimPoint()],
  });

  const result = normalizeMarketDashboardPayload(payload);
  const perf = result.performanceVsCostHistory;

  assert.equal(perf.length, 1);
  const pt = perf[0];

  // All ratio and value fields must survive normalization
  assert.equal(pt.simulated_mean_pack_value_vs_pack_cost, 0.72);
  assert.equal(pt.simulatedMeanPackValueVsPackCost, 0.72);
  assert.equal(pt.mean_value_to_cost_ratio, 0.72);
  assert.equal(pt.meanValueToCostRatio, 0.72);
  assert.equal(pt.simulated_median_pack_value_vs_pack_cost, 0.45);
  assert.equal(pt.simulatedMedianPackValueVsPackCost, 0.45);
  assert.equal(pt.median_value_to_cost_ratio, 0.45);
  assert.equal(pt.medianValueToCostRatio, 0.45);
  assert.equal(pt.p95_value_to_cost_ratio, 3.1);
  assert.equal(pt.p95ValueToCostRatio, 3.1);
  assert.equal(pt.pack_cost, 5.0);
  assert.equal(pt.packCost, 5.0);
  assert.equal(pt.mean_value, 3.6);
  assert.equal(pt.meanValue, 3.6);
  assert.equal(pt.median_value, 2.25);
  assert.equal(pt.medianValue, 2.25);
  assert.equal(pt.calculation_run_id, "run-abc");
  assert.equal(pt.calculationRunId, "run-abc");
  assert.equal(pt.isCarriedForward, false);
  assert.equal(pt.is_carried_forward, false);
});

test("normalizeMarketDashboardPayload exposes both performanceVsCostHistory and performance_vs_cost_history", () => {
  const payload = makeDashboardPayload({
    performanceVsCostHistory: [makeSimPoint()],
  });

  const result = normalizeMarketDashboardPayload(payload);

  assert.ok(Array.isArray(result.performanceVsCostHistory));
  assert.ok(Array.isArray(result.performance_vs_cost_history));
  assert.deepEqual(result.performanceVsCostHistory, result.performance_vs_cost_history);
});

test("normalizeMarketDashboardPayload does not copy setValue into performanceVsCostHistory", () => {
  const setValuePoint = { date: "2026-06-20", setValue: 999.0, set_value: 999.0 };
  const payload = makeDashboardPayload({
    performanceVsCostHistory: [makeSimPoint()],
    setValueHistories: {
      standard: [setValuePoint],
    },
  });

  const result = normalizeMarketDashboardPayload(payload);
  const perf = result.performanceVsCostHistory;

  assert.equal(perf.length, 1);
  assert.ok(!("setValue" in perf[0]), "setValue must not appear in performanceVsCostHistory");
  assert.ok(!("set_value" in perf[0]), "set_value must not appear in performanceVsCostHistory");
});

test("regression: changing set value does not change performanceVsCostHistory", () => {
  const simPoint = makeSimPoint();

  const payloadSV100 = makeDashboardPayload({
    performanceVsCostHistory: [simPoint],
    setValueHistories: { standard: [{ date: "2026-06-20", setValue: 100.0 }] },
  });
  const payloadSV200 = makeDashboardPayload({
    performanceVsCostHistory: [simPoint],
    setValueHistories: { standard: [{ date: "2026-06-20", setValue: 200.0 }] },
  });

  const resultSV100 = normalizeMarketDashboardPayload(payloadSV100);
  const resultSV200 = normalizeMarketDashboardPayload(payloadSV200);

  assert.deepEqual(
    resultSV100.performanceVsCostHistory,
    resultSV200.performanceVsCostHistory,
    "set value change must not affect performanceVsCostHistory"
  );
});

test("regression: changing simulation history changes performanceVsCostHistory even when set value is constant", () => {
  const setValueHistories = { standard: [{ date: "2026-06-20", setValue: 100.0 }] };

  const payloadV1 = makeDashboardPayload({
    performanceVsCostHistory: [makeSimPoint({ simulated_mean_pack_value_vs_pack_cost: 0.60 })],
    setValueHistories,
  });
  const payloadV2 = makeDashboardPayload({
    performanceVsCostHistory: [makeSimPoint({ simulated_mean_pack_value_vs_pack_cost: 0.80 })],
    setValueHistories,
  });

  const resultV1 = normalizeMarketDashboardPayload(payloadV1);
  const resultV2 = normalizeMarketDashboardPayload(payloadV2);

  assert.notDeepEqual(
    resultV1.performanceVsCostHistory,
    resultV2.performanceVsCostHistory,
    "simulation change must update performanceVsCostHistory"
  );
  assert.equal(resultV1.performanceVsCostHistory[0].simulated_mean_pack_value_vs_pack_cost, 0.60);
  assert.equal(resultV2.performanceVsCostHistory[0].simulated_mean_pack_value_vs_pack_cost, 0.80);
});

test("normalizeMarketDashboardPayload normalizes by date key from snapshot_date or date field", () => {
  const pt1 = makeSimPoint({ snapshot_date: "2026-06-19", date: undefined });
  const pt2 = makeSimPoint({ snapshot_date: undefined, date: "2026-06-20" });

  const payload = makeDashboardPayload({ performanceVsCostHistory: [pt1, pt2] });
  const result = normalizeMarketDashboardPayload(payload);

  const dates = result.performanceVsCostHistory.map((p) => p.date);
  assert.deepEqual(dates, ["2026-06-19", "2026-06-20"]);
});

test("normalizeMarketDashboardPayload preserves camelCase simulation ratio aliases", () => {
  const payload = makeDashboardPayload({
    performanceVsCostHistory: [
      {
        snapshotDate: "2026-06-20",
        calculationRunId: "run-camel",
        runCreatedAt: "2026-06-20T10:00:00+00:00",
        packCost: 4.0,
        meanValue: 3.0,
        medianValue: 1.5,
        meanValueToCostRatio: 0.75,
        simulatedMeanPackValueVsPackCost: 0.75,
        medianValueToCostRatio: 0.375,
        simulatedMedianPackValueVsPackCost: 0.375,
        p95ValueToCostRatio: 2.5,
        isCarriedForward: false,
        source: "calculation_history_trend+simulation_run_summary",
      },
    ],
  });

  const result = normalizeMarketDashboardPayload(payload);
  const pt = result.performanceVsCostHistory[0];

  assert.equal(pt.meanValueToCostRatio, 0.75);
  assert.equal(pt.mean_value_to_cost_ratio, 0.75);
  assert.equal(pt.simulatedMeanPackValueVsPackCost, 0.75);
  assert.equal(pt.simulated_mean_pack_value_vs_pack_cost, 0.75);
  assert.equal(pt.p95ValueToCostRatio, 2.5);
  assert.equal(pt.p95_value_to_cost_ratio, 2.5);
  assert.equal(pt.packCost, 4.0);
  assert.equal(pt.pack_cost, 4.0);
  assert.equal(pt.calculationRunId, "run-camel");
  assert.equal(pt.calculation_run_id, "run-camel");
});

// ---------------------------------------------------------------------------
// normalizeMarketMoversByWindowPayload (via normalizeMarketDashboardPayload)
// ---------------------------------------------------------------------------

function makeMoverCard(overrides = {}) {
  return {
    cardId: "card-1",
    name: "Charizard ex",
    currentPrice: 100,
    change30dAmount: 10,
    change30dPercent: 11.1,
    ...overrides,
  };
}

test("normalizeMarketDashboardPayload normalizes marketMoversByWindow for 1D/7D/30D", () => {
  const payload = makeDashboardPayload({});
  payload.marketMoversByWindow = {
    "1D": {
      window: "1D",
      windowDays: 1,
      heatingUp: [makeMoverCard({ cardId: "card-1d", name: "1D Gainer" })],
      coolingOff: [],
    },
    "7D": {
      window: "7D",
      windowDays: 7,
      heatingUp: [makeMoverCard({ cardId: "card-7d", name: "7D Gainer" })],
      coolingOff: [],
    },
    "30D": {
      window: "30D",
      windowDays: 30,
      heatingUp: [makeMoverCard({ cardId: "card-30d", name: "30D Gainer" })],
      coolingOff: [],
    },
  };

  const result = normalizeMarketDashboardPayload(payload);

  assert.ok(result.marketMoversByWindow, "marketMoversByWindow must be present");
  assert.deepEqual(Object.keys(result.marketMoversByWindow).sort(), ["1D", "30D", "7D"]);
  assert.equal(result.marketMoversByWindow["1D"].heatingUp[0].name, "1D Gainer");
  assert.equal(result.marketMoversByWindow["1D"].heatingUp[0].cardId, "card-1d");
  assert.equal(result.marketMoversByWindow["7D"].heatingUp[0].name, "7D Gainer");
  assert.equal(result.marketMoversByWindow["30D"].heatingUp[0].name, "30D Gainer");
  assert.deepEqual(result.marketMoversByWindow, result.market_movers_by_window);
});

test("normalizeMarketDashboardPayload accepts snake_case market_movers_by_window", () => {
  const payload = makeDashboardPayload({});
  payload.market_movers_by_window = {
    "1D": { heating_up: [makeMoverCard({ cardId: "card-1d", name: "1D Gainer" })], cooling_off: [] },
  };

  const result = normalizeMarketDashboardPayload(payload);

  assert.equal(result.marketMoversByWindow["1D"].heatingUp[0].name, "1D Gainer");
});

test("normalizeMarketDashboardPayload returns null marketMoversByWindow when absent", () => {
  const payload = makeDashboardPayload({});

  const result = normalizeMarketDashboardPayload(payload);

  assert.equal(result.marketMoversByWindow, null);
  assert.equal(result.market_movers_by_window, null);
});
