import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeMarketDashboardPayload,
  normalizeMarketMoversPayload,
  normalizeOverviewPayload,
  normalizeTopChasePayload,
} from "./pokemonSetMarketClient.js";

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

// ---------------------------------------------------------------------------
// normalizeOverviewPayload
// ---------------------------------------------------------------------------

function makeOverviewPayload(overrides = {}) {
  return {
    set: { id: "set-1", name: "Test Set", slug: "testSet" },
    window: "365d",
    setValueHistoriesByScope: {
      standard: [{ date: "2026-06-01", setValue: 100 }, { date: "2026-06-30", setValue: 123.45 }],
    },
    performanceVsCostHistory: [makeSimPoint()],
    availableScopes: [{ key: "standard", label: "Standard", latestDate: "2026-06-30" }],
    latestMarketDate: "2026-06-30",
    meta: { warnings: [] },
    ...overrides,
  };
}

test("normalizeOverviewPayload normalizes set value histories by scope", () => {
  const result = normalizeOverviewPayload(makeOverviewPayload());

  assert.equal(result.setValueHistoriesByScope.standard.length, 2);
  assert.equal(result.setValueHistoriesByScope.standard[1].setValue, 123.45);
});

test("normalizeOverviewPayload normalizes performanceVsCostHistory", () => {
  const result = normalizeOverviewPayload(makeOverviewPayload());

  assert.equal(result.performanceVsCostHistory.length, 1);
  assert.equal(result.performanceVsCostHistory[0].meanValue, 3.6);
});

test("normalizeOverviewPayload normalizes availableScopes and latestMarketDate", () => {
  const result = normalizeOverviewPayload(makeOverviewPayload());

  assert.equal(result.availableScopes.length, 1);
  assert.equal(result.availableScopes[0].key, "standard");
  assert.equal(result.latestMarketDate, "2026-06-30");
});

test("normalizeOverviewPayload does not include topChaseCards, topChaseCardHistories, marketMovers, or marketMoversByWindow", () => {
  const result = normalizeOverviewPayload(makeOverviewPayload());

  assert.equal(Object.prototype.hasOwnProperty.call(result, "topChaseCards"), false);
  assert.equal(Object.prototype.hasOwnProperty.call(result, "topChaseCardHistories"), false);
  assert.equal(Object.prototype.hasOwnProperty.call(result, "marketMovers"), false);
  assert.equal(Object.prototype.hasOwnProperty.call(result, "marketMoversByWindow"), false);
});

test("normalizeOverviewPayload tolerates missing fields defensively", () => {
  const result = normalizeOverviewPayload({});

  assert.deepEqual(result.setValueHistoriesByScope, {});
  assert.deepEqual(result.performanceVsCostHistory, []);
  assert.deepEqual(result.availableScopes, []);
  assert.equal(result.latestMarketDate, null);
});

// ---------------------------------------------------------------------------
// normalizeTopChasePayload
// ---------------------------------------------------------------------------

function makeTopChasePayload(overrides = {}) {
  return {
    set: { id: "set-1", name: "Test Set", slug: "testSet" },
    window: "30D",
    topChaseCards: [
      {
        cardId: "card-1",
        cardVariantId: "variant-1",
        name: "Chase Card",
        marketPrice: 42.5,
        rank: 1,
      },
    ],
    topChaseCardHistories: {
      "variant-1": [
        { date: "2026-06-01", marketPrice: 40.0 },
        { date: "2026-06-30", marketPrice: 42.5 },
      ],
    },
    latestMarketDate: "2026-06-30",
    meta: { limit: 10, warnings: [] },
    ...overrides,
  };
}

test("normalizeTopChasePayload normalizes cards from topChaseCards", () => {
  const result = normalizeTopChasePayload(makeTopChasePayload());

  assert.equal(result.cards.length, 1);
  assert.equal(result.cards[0].name, "Chase Card");
  assert.equal(result.cards[0].marketPrice, 42.5);
});

test("normalizeTopChasePayload maps topChaseCardHistories onto the matching card's priceHistory", () => {
  const result = normalizeTopChasePayload(makeTopChasePayload());

  assert.ok(result.cards[0].priceHistory.length >= 2);
  assert.equal(result.cards[0].priceHistory[result.cards[0].priceHistory.length - 1].marketPrice, 42.5);
});

test("normalizeTopChasePayload tolerates missing fields defensively", () => {
  const result = normalizeTopChasePayload({});

  assert.deepEqual(result.cards, []);
  assert.deepEqual(result.topChaseCardHistories, {});
});

// ---------------------------------------------------------------------------
// normalizeMarketMoversPayload (direct /market/movers single-window payload)
// ---------------------------------------------------------------------------

function makeMarketMoversPayload(overrides = {}) {
  return {
    set: { id: "set-1", name: "Test Set", slug: "testSet" },
    window: "7D",
    windowDays: 7,
    marketMovers: {
      window: "7D",
      windowDays: 7,
      heatingUp: [makeMoverCard({ cardId: "card-7d", name: "7D Gainer" })],
      coolingOff: [],
      all: [makeMoverCard({ cardId: "card-7d", name: "7D Gainer" })],
    },
    meta: { limit: 5, warnings: [] },
    ...overrides,
  };
}

test("normalizeMarketMoversPayload normalizes a single-window /market/movers payload", () => {
  const result = normalizeMarketMoversPayload(makeMarketMoversPayload());

  assert.equal(result.window, "7D");
  assert.equal(result.windowDays, 7);
  assert.equal(result.heatingUp.length, 1);
  assert.equal(result.heatingUp[0].name, "7D Gainer");
  assert.equal(result.coolingOff.length, 0);
});

test("normalizeMarketMoversPayload tolerates missing fields defensively", () => {
  const result = normalizeMarketMoversPayload({});

  assert.equal(result.window, "30D");
  assert.deepEqual(result.heatingUp, []);
  assert.deepEqual(result.coolingOff, []);
});
