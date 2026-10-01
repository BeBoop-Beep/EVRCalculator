import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketActivityChart, { activityCalendarX, buildActivityInspectionDates } from "./MarketActivityChart.jsx";

const payload = { activityGenerationId: "g", roster: { rosterRevision: { kind: "x" } }, coverage: { observedConstituents: 19 }, totals: {}, series: { asOf: "2026-09-29", activityRange: { startDate: "2026-09-01", endDate: "2026-09-29" }, canonicalRange: { startDate: "2026-09-01", endDate: "2026-09-29" }, sales: { source: "EBAY", counts: { points: [{ date: "2026-09-20", observedCount: 8 }, { date: "2026-09-23", observedCount: 0 }] } }, supply: { source: "TCGPLAYER", aggregation: "LOWER_BOUND", listings: { points: [{ date: "2026-09-23", value: 38, observedAt: null, state: "HISTORICAL_OBSERVATION" }] }, quantity: { points: [{ date: "2026-09-23", value: 40, observedAt: null, state: "HISTORICAL_OBSERVATION" }] } } } };
const model = { startDate: "2026-09-01", endDate: "2026-09-29", dates: ["2026-09-01", "2026-09-23", "2026-09-29"], series: [{ key: "p", color: "red", values: [100, 107, 110] }, { key: "q", color: "green", values: [105, 106, 108] }] };
const bounds = { left: 0, width: 100, top: 0, height: 100 };
const chartEvent = (overrides = {}) => ({ pointerType: "mouse", clientX: 100, clientY: 50, currentTarget: { getBoundingClientRect: () => bounds }, ...overrides });

test("calendar x geometry reflects elapsed time rather than sparse array position", () => {
  const start = activityCalendarX("2026-09-01", "2026-09-01", "2026-09-29");
  const middle = activityCalendarX("2026-09-15", "2026-09-01", "2026-09-29");
  const end = activityCalendarX("2026-09-29", "2026-09-01", "2026-09-29");
  assert.equal(Math.round((middle - start) / (end - start) * 100), 50);
});

test("inspection dates are the sorted visible union of sales, supply, and truthful focused Index observations", () => {
  assert.deepEqual(buildActivityInspectionDates({
    sales: [{ date: "2026-09-20" }], supply: [{ date: "2026-09-23" }], model,
    focusedSeriesKey: "p", startDate: "2026-09-10", endDate: "2026-09-29",
  }), ["2026-09-20", "2026-09-23", "2026-09-29"]);
});

test("Activity draws sparse bars, one supply marker, explicit zero, and ghosted Index context without a supply line", async () => {
  let renderer; await act(async () => { renderer = TestRenderer.create(<MarketActivityChart state={{ status: "ready", data: payload }} model={model} focusedSeries={{ key: "p", label: "Prismatic", asset: "cards" }} timeframe="30D" />); });
  assert.equal(renderer.root.findAll((node) => node.props?.["data-activity-sales-bar"] !== undefined).length, 2);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-activity-sales-value"] === 0).length, 1);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-activity-supply-marker"] !== undefined).length, 1);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-activity-supply-line"] !== undefined).length, 0);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-activity-index-context"] !== undefined).length, 2);
});

test("Index-only inspection shows missing Activity facts, real Index, and a calendar-aligned crosshair; Escape clears both", async () => {
  let renderer; await act(async () => { renderer = TestRenderer.create(<MarketActivityChart state={{ status: "ready", data: payload }} model={model} focusedSeries={{ key: "p", label: "Prismatic", asset: "cards" }} timeframe="30D" />); });
  const chart = renderer.root.findByProps({ "data-market-activity-chart": true });
  await act(async () => chart.props.onFocus());
  assert.equal(renderer.root.findAllByProps({ "data-market-activity-crosshair": true }).length, 1);
  const tooltipValues = renderer.root.findAllByType("dd").map((node) => node.children.join(""));
  assert.deepEqual(tooltipValues, ["Not observed", "Not observed", "Not observed", "110.00"]);
  await act(async () => chart.props.onKeyDown({ key: "Escape" }));
  assert.equal(renderer.root.findAllByProps({ "data-market-activity-tooltip": true }).length, 0);
  assert.equal(renderer.root.findAllByProps({ "data-market-activity-crosshair": true }).length, 0);
});

test("tooltip distinguishes complete evidence from Activity evidence without an exact Index observation", async () => {
  let renderer; await act(async () => { renderer = TestRenderer.create(<MarketActivityChart state={{ status: "ready", data: payload }} model={model} focusedSeries={{ key: "p", label: "Prismatic", asset: "cards" }} timeframe="30D" />); });
  const chart = renderer.root.findByProps({ "data-market-activity-chart": true });
  await act(async () => chart.props.onPointerMove(chartEvent({ clientX: 79 })));
  assert.deepEqual(renderer.root.findAllByType("dd").map((node) => node.children.join("")), ["0", "38", "40", "107.00"]);
  await act(async () => chart.props.onPointerMove(chartEvent({ clientX: 68 })));
  assert.deepEqual(renderer.root.findAllByType("dd").map((node) => node.children.join("")), ["8", "Not observed", "Not observed", "—"]);
});

test("coarse vertical gestures preserve scrolling while tap and horizontal scrub inspect", async () => {
  let renderer; await act(async () => { renderer = TestRenderer.create(<MarketActivityChart state={{ status: "ready", data: payload }} model={model} focusedSeries={{ key: "p", label: "Prismatic", asset: "cards" }} timeframe="30D" />); });
  const chart = renderer.root.findByProps({ "data-market-activity-chart": true });
  await act(async () => {
    chart.props.onPointerDown(chartEvent({ pointerType: "touch", clientX: 40, clientY: 10 }));
    chart.props.onPointerMove(chartEvent({ pointerType: "touch", clientX: 42, clientY: 80 }));
    chart.props.onPointerUp(chartEvent({ pointerType: "touch", clientX: 42, clientY: 80 }));
  });
  assert.equal(renderer.root.findAllByProps({ "data-market-activity-tooltip": true }).length, 0);
  await act(async () => {
    chart.props.onPointerDown(chartEvent({ pointerType: "touch", clientX: 10, clientY: 40 }));
    chart.props.onPointerMove(chartEvent({ pointerType: "touch", clientX: 80, clientY: 42 }));
    chart.props.onPointerUp(chartEvent({ pointerType: "touch", clientX: 80, clientY: 42 }));
  });
  assert.equal(renderer.root.findAllByProps({ "data-market-activity-tooltip": true }).length, 1);
  await act(async () => { chart.props.onKeyDown({ key: "Escape" }); chart.props.onPointerDown(chartEvent({ pointerType: "touch", clientX: 50, clientY: 50 })); chart.props.onPointerUp(chartEvent({ pointerType: "touch", clientX: 50, clientY: 50 })); });
  assert.equal(renderer.root.findAllByProps({ "data-market-activity-tooltip": true }).length, 1);
  assert.match(String(chart.props.className), /touch-pan-y/);
  await act(async () => chart.props.onPointerCancel());
});
