import test from "node:test";
import assert from "node:assert/strict";

import { selectOverviewPerformanceHistoryState } from "./performanceHistorySelector.mjs";

// Regression contract for the "Opening Profit vs Cost only appears after
// visiting Insights and coming back" defect.
//
// The real cause was a backend freshness gap: the market-dashboard snapshot did
// not track the set's simulation sources, so it could serve an OPvC history
// that was older (or shorter) than the set-page/Insights one. Once the market
// dashboard carries a current history, Overview must render the chart from that
// payload alone — no Insights fetch, no tab round trip, no remount.

const CURRENT_MARKET_HISTORY = [
  { date: "2026-08-01", meanValueToCostRatio: 0.82, medianValueToCostRatio: 0.61, packCost: 4.4 },
  { date: "2026-08-02", meanValueToCostRatio: 0.88, medianValueToCostRatio: 0.64, packCost: 4.4 },
];

const LIVE_PAYLOAD = {
  performanceVsCostHistory: CURRENT_MARKET_HISTORY,
  latestMarketDate: "2026-08-02",
};

test("Overview renders OPvC from a current market-dashboard history without any Insights payload", () => {
  const state = selectOverviewPerformanceHistoryState({
    seedPayload: null,
    livePayload: LIVE_PAYLOAD,
    liveStatus: "success",
    liveError: null,
    // No Insights payload at all: this is first paint on Overview.
    insightsHistory: undefined,
    marketAsOfDate: "2026-08-02",
  });

  assert.equal(state.status, "success");
  assert.equal(state.emptyStateEligible, false);
  assert.equal(state.history.length, 2);
  assert.deepEqual(
    state.history.map((point) => point.snapshotDate),
    ["2026-08-01", "2026-08-02"],
  );
  assert.equal(state.latestRealDate, "2026-08-02");
  assert.equal(state.diagnostics.insightsHistoryPointCount, 0);
});

test("visiting Insights afterwards does not change the Overview OPvC series", () => {
  const overviewOnly = selectOverviewPerformanceHistoryState({
    livePayload: LIVE_PAYLOAD,
    liveStatus: "success",
    marketAsOfDate: "2026-08-02",
  });
  const afterInsights = selectOverviewPerformanceHistoryState({
    livePayload: LIVE_PAYLOAD,
    liveStatus: "success",
    insightsHistory: { history_trend: CURRENT_MARKET_HISTORY },
    marketAsOfDate: "2026-08-02",
  });

  assert.equal(afterInsights.status, overviewOnly.status);
  assert.deepEqual(
    afterInsights.history.map((point) => point.snapshotDate),
    overviewOnly.history.map((point) => point.snapshotDate),
  );
});
