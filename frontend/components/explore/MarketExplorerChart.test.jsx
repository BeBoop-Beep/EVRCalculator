import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerChart from "./MarketExplorerChart.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

import fs from "node:fs";

// Accepted contract (Bucket 1): series identity is the market's own color; a
// return's green/red is performance semantics only. The retired
// colorExplorerVisibleSeries projection (recoloring a single line by its
// change) must not come back.
test("chart keeps market identity color and never recolors a line by its return", () => {
  const source = fs.readFileSync(new URL("./MarketExplorerChart.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /colorExplorerVisibleSeries/);
  assert.match(source, /Series identity is the market's own color/);
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
