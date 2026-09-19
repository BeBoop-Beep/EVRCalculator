import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerChart, { colorExplorerVisibleSeries } from "./MarketExplorerChart.jsx";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const model = (percent, available = true) => ({
  available: true,
  series: [{ key: "a", color: "identity-a", change: { available, percent } }],
});

test("Explorer alone colors one visible line from published change", () => {
  assert.equal(colorExplorerVisibleSeries(model(5), 1).series[0].color, POSITIVE_VALUE_COLOR);
  assert.equal(colorExplorerVisibleSeries(model(-3), 1).series[0].color, NEGATIVE_VALUE_COLOR);
  assert.equal(colorExplorerVisibleSeries(model(0), 1).series[0].color, "identity-a");
  assert.equal(colorExplorerVisibleSeries(model(null, false), 1).series[0].color, "identity-a");
  assert.equal(colorExplorerVisibleSeries(model(null), 1).series[0].color, "identity-a");
});

test("comparison identity colors return when a second market is visible", () => {
  const pair = { available: true, series: [model(-10).series[0], {
    key: "b", color: "identity-b", change: { available: true, percent: 20 },
  }] };
  assert.deepEqual(colorExplorerVisibleSeries(pair, 2).series.map((entry) => entry.color),
    ["identity-a", "identity-b"]);
  assert.equal(colorExplorerVisibleSeries({ ...pair, series: pair.series.slice(0, 1) }, 1).series[0].color,
    NEGATIVE_VALUE_COLOR);
  assert.deepEqual(colorExplorerVisibleSeries(pair, 2).series.map((entry) => entry.color),
    ["identity-a", "identity-b"]);
  assert.deepEqual(pair.series.map((entry) => entry.color), ["identity-a", "identity-b"],
    "the Explorer display projection leaves source identity colors intact");
});

test("single-series direction follows the selected published timeframe", () => {
  const changes = { "7D": { available: true, percent: 5 },
    "30D": { available: true, percent: -3 } };
  const forWindow = (window) => colorExplorerVisibleSeries({
    available: true, series: [{ key: "a", color: "identity-a", change: changes[window] }],
  }, 1).series[0].color;
  assert.equal(forWindow("7D"), POSITIVE_VALUE_COLOR);
  assert.equal(forWindow("30D"), NEGATIVE_VALUE_COLOR);
});

test("a fresh Explorer chart defaults to Index while Performance remains selectable", () => {
  let renderer;
  act(() => { renderer = TestRenderer.create(<MarketExplorerChart overview={{}} selectedSeries={[]}
    timeframe="7D" timeframeOptions={[]} />); });
  const toggle = (value) => renderer.root.findByProps({ "data-market-chart-view": value });
  assert.equal(toggle("index").props["aria-pressed"], true);
  assert.equal(toggle("performance").props["aria-pressed"], false);
  act(() => toggle("performance").props.onClick());
  assert.equal(toggle("performance").props["aria-pressed"], true);
  act(() => renderer.unmount());
});
