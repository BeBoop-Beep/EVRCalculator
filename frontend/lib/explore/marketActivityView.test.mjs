import test from "node:test";
import assert from "node:assert/strict";
import { activityCapabilityBatchKey } from "./marketActivityCapabilities.mjs";
import { ACTIVITY_WINDOW_BY_TIMEFRAME, activityWindowForTimeframe, enterActivityView, reconcileActivityView } from "./marketActivityView.mjs";
import { MARKET_CHART_VIEW_ACTIVITY, MARKET_CHART_VIEW_INDEX } from "../../components/explore/marketPerformanceDomain.mjs";

test("Activity supports exactly the approved Explorer windows", () => {
  assert.deepEqual(ACTIVITY_WINDOW_BY_TIMEFRAME, { "7D": 7, "30D": 30, "3M": 90, "6M": 180 });
  for (const [timeframe, days] of Object.entries(ACTIVITY_WINDOW_BY_TIMEFRAME)) assert.equal(activityWindowForTimeframe(timeframe), days);
  for (const timeframe of ["1D", "1Y", "All"]) assert.equal(activityWindowForTimeframe(timeframe), null);
  assert.deepEqual(enterActivityView("1D"), { chartViewMode: MARKET_CHART_VIEW_ACTIVITY, timeframe: "30D" });
});

test("Activity remains only for a focused supported Card capability", () => {
  assert.equal(reconcileActivityView(MARKET_CHART_VIEW_ACTIVITY, { asset: "cards" }, { available: true }), MARKET_CHART_VIEW_ACTIVITY);
  assert.equal(reconcileActivityView(MARKET_CHART_VIEW_ACTIVITY, { asset: "cards" }, { available: false }), MARKET_CHART_VIEW_INDEX);
  assert.equal(reconcileActivityView(MARKET_CHART_VIEW_ACTIVITY, { asset: "sealed" }, { available: true }), MARKET_CHART_VIEW_INDEX);
  assert.equal(reconcileActivityView(MARKET_CHART_VIEW_ACTIVITY, null, { available: true }), MARKET_CHART_VIEW_INDEX);
});

test("capability cache identity includes the Activity window", () => {
  const markets = [{ focusKey: "raw", marketKey: "raw", rosterRef: { kind: "SURFACE_V2_GENERATION", marketKey: "raw", generationId: "g" } }];
  assert.notEqual(activityCapabilityBatchKey(markets, "user", "plus", 30), activityCapabilityBatchKey(markets, "user", "plus", 90));
});
