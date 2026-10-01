import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketActivityChart, { activityCalendarX } from "./MarketActivityChart.jsx";

const payload = { activityGenerationId: "g", roster: { rosterRevision: { kind: "x" } }, coverage: { observedConstituents: 19 }, totals: {}, series: { asOf: "2026-09-29", activityRange: { startDate: "2026-09-01", endDate: "2026-09-29" }, canonicalRange: { startDate: "2026-09-01", endDate: "2026-09-29" }, sales: { source: "EBAY", counts: { points: [{ date: "2026-09-20", observedCount: 8 }, { date: "2026-09-23", observedCount: 0 }] } }, supply: { source: "TCGPLAYER", aggregation: "LOWER_BOUND", listings: { points: [{ date: "2026-09-23", value: 38, observedAt: null, state: "HISTORICAL_OBSERVATION" }] }, quantity: { points: [{ date: "2026-09-23", value: 40, observedAt: null, state: "HISTORICAL_OBSERVATION" }] } } } };
const model = { startDate: "2026-09-01", endDate: "2026-09-29", dates: ["2026-09-01", "2026-09-29"], series: [{ key: "p", color: "red", values: [100, 110] }, { key: "q", color: "green", values: [105, 108] }] };

test("calendar x geometry reflects elapsed time rather than sparse array position", () => {
  const start = activityCalendarX("2026-09-01", "2026-09-01", "2026-09-29");
  const middle = activityCalendarX("2026-09-15", "2026-09-01", "2026-09-29");
  const end = activityCalendarX("2026-09-29", "2026-09-01", "2026-09-29");
  assert.equal(Math.round((middle - start) / (end - start) * 100), 50);
});

test("Activity draws sparse bars, one supply marker, explicit zero, and ghosted Index context without a supply line", async () => {
  let renderer; await act(async () => { renderer = TestRenderer.create(<MarketActivityChart state={{ status: "ready", data: payload }} model={model} focusedSeries={{ key: "p", label: "Prismatic", asset: "cards" }} timeframe="30D" />); });
  assert.equal(renderer.root.findAll((node) => node.props?.["data-activity-sales-bar"] !== undefined).length, 2);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-activity-sales-value"] === 0).length, 1);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-activity-supply-marker"] !== undefined).length, 1);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-activity-supply-line"] !== undefined).length, 0);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-activity-index-context"] !== undefined).length, 2);
});
