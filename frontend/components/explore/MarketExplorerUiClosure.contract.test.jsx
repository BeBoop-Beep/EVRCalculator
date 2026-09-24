import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";
import { readFileSync } from "node:fs";
import MarketPerformanceChart from "./MarketPerformanceChart.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// Repo sources have mixed CRLF/LF; normalize before multi-line anchors.
const read = (name) => readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const chart = read("./MarketExplorerChart.jsx");
const client = read("./MarketExplorerClient.jsx");
const browse = read("./MarketExplorerBrowse.jsx");
const perf = read("./MarketPerformanceChart.jsx");
const pokemonPerf = read("./PokemonMarketPerformance.jsx");

const model = (values) => ({
  available: true,
  dates: values.map((_, index) => `2026-09-${String(index + 1).padStart(2, "0")}`),
  series: [{ key: "a", label: "A", color: "#fff", values }],
});
const surfaceOf = (props) => {
  let renderer;
  TestRenderer.act(() => { renderer = TestRenderer.create(<MarketPerformanceChart {...props} />); });
  const node = renderer.root.findByProps({ "data-market-performance-chart": true });
  const out = { className: node.props.className, surface: node.props["data-market-performance-surface"], root: renderer.root };
  return out;
};

test("(A) the constituents trigger is no longer in the top toolbar beside the Index toggle", () => {
  const toolbar = chart.slice(chart.indexOf("data-market-explorer-chart-toolbar"), chart.indexOf("data-market-explorer-graph-controls"));
  assert.doesNotMatch(toolbar, /data-market-explorer-view-details/);
  assert.equal(chart.match(/data-market-explorer-view-details/g).length, 1);
});

test("(B) the trigger is structurally the bottom-centre of the chart workspace, after the plot", () => {
  assert.ok(chart.indexOf("data-market-explorer-view-details") > chart.indexOf("<MarketPerformanceChart"));
  const row = chart.slice(chart.indexOf("data-market-explorer-chart-bottom-actions"));
  assert.match(row, /^[^>]*justify-center/);
  assert.match(row, /data-market-explorer-view-details/);
  assert.ok(row.indexOf("data-market-explorer-view-details") < row.indexOf("</section>"));
  assert.doesNotMatch(chart, /fixed inset-0/, "not a fullscreen modal");
});

test("(2) the trigger uses the violet analysis-action treatment, not green/red/teal", () => {
  const button = chart.slice(chart.indexOf("data-market-explorer-view-details"), chart.indexOf("View Constituents"));
  assert.match(button, /border-violet-400/);
  assert.match(button, /bg-violet-500\/\[\.12\]/);
  assert.match(button, /text-violet-200/);
  assert.match(button, /hover:bg-violet-500\/\[\.24\]/);
  assert.match(button, /focus-visible:ring-2 focus-visible:ring-violet-300/);
  assert.doesNotMatch(button, /emerald|green|red-|rose|teal|45,212,191|248,113,113|cyan/);
});

test("(C)(D) opening activates the in-place overlay and closing restores the same mounted chart", () => {
  assert.match(client, /onToggleDetails=\{\(\) => setDetailsOpen\(true\)\}/);
  assert.match(client, /data-market-explorer-hide-details\n\s+onClick=\{\(\) => setDetailsOpen\(false\)\}/);
  assert.match(client, /Hide Constituents &amp; Comparison/);
  // The chart is always mounted (only made inert), so its Index/Performance state survives.
  assert.match(client, /data-market-explorer-graph\n\s+aria-hidden=\{detailsOpen/);
  assert.doesNotMatch(client, /\{detailsOpen \? null : <MarketExplorerChart/);
  assert.match(client, /\{detailsOpen \? \(\n\s+<div\n\s+data-market-explorer-compare-results\n\s+className="absolute inset-0/);
});

test("(E) Explorer gets the open-canvas chart; other consumers keep the card surface", () => {
  assert.match(chart, /openCanvas = true/);
  assert.match(chart, /minimal=\{openCanvas\}/);
  const explorer = surfaceOf({ model: model([101, 102, 103]), viewMode: "index", timeframe: "7D", minimal: true });
  assert.equal(explorer.surface, "open-canvas");
  assert.doesNotMatch(explorer.className, /border-\[var\(--border-subtle\)\]|rounded-lg|bg-\[rgba/);
  const shared = surfaceOf({ model: model([101, 102, 103]), viewMode: "index", timeframe: "7D" });
  assert.equal(shared.surface, "card");
  assert.match(shared.className, /rounded-lg border border-\[var\(--border-subtle\)\] bg-\[rgba\(2,6,23,0\.16\)\]/);
  assert.doesNotMatch(pokemonPerf, /minimal/, "/Market chart never opts into the open canvas");
});

test("(F) Clear Graph is a restrained red danger control without loudening Remove", () => {
  const button = chart.slice(chart.indexOf("data-market-explorer-clear-graph"), chart.indexOf("Clear Graph\n"));
  assert.match(button, /text-\[rgb\(248,113,113\)\]/);
  assert.match(button, /border-\[rgba\(248,113,113,0\.4\)\]/);
  assert.match(button, /bg-\[rgba\(248,113,113,0\.07\)\]/);
  assert.match(button, /hover:border-\[rgba\(248,113,113,0\.7\)\]/);
  assert.match(button, /hover:bg-\[rgba\(248,113,113,0\.16\)\]/);
  assert.match(button, /focus-visible:ring-\[rgba\(248,113,113,0\.7\)\]/);
  assert.match(button, /disabled:opacity-40/);
  assert.match(button, /disabled:cursor-not-allowed/);
});

test("(G) Browse Markets gets modest top padding above the Market Directory heading", () => {
  assert.match(browse, /data-market-explorer-browse[^>]*className="relative min-w-0 px-3 pb-3 pt-3"/);
});

test("(V) the fixed 40rem/46rem desktop graph heights do not return; sizing stays viewport-aware", () => {
  assert.doesNotMatch(chart, /desk:h-\[40rem\]|2xl:h-\[46rem\]/);
  assert.match(chart, /desk:h-\[clamp\(19rem,calc\(100dvh-24rem\),42rem\)\]/);
});

test("(4) research column takes the remaining width with a small deliberate right gutter", () => {
  assert.match(client, /desk:grid-cols-\[minmax\(18rem,20rem\)_minmax\(0,1fr\)\]/);
  assert.doesNotMatch(chart + perf, /100vw/);
  assert.doesNotMatch(client.split("\n").find((line) => line.includes("desk:grid-cols-[minmax(18rem")), /100vw/);
  assert.match(chart, /pl-2 pr-3 sm:pl-3 sm:pr-4/);
});

test("(10) INDEX view always renders a labelled 100 reference line at short windows", () => {
  for (const [values, timeframe] of [[[102.2, 102.5, 102.8], "7D"], [[94.1, 95, 96.3], "1D"], [[103, 104, 105], "30D"], [[97, 98, 99], "3M"], [[104, 107, 110], "All"]]) {
    const { root } = surfaceOf({ model: model(values), viewMode: "index", timeframe });
    assert.equal(root.findAll((n) => n.props?.["data-market-performance-reference"] === 100).length >= 1, true, `${timeframe} reference line`);
    const label = root.findByProps({ "data-market-performance-reference-label": true });
    assert.equal(label.children.join(""), "100.00");
  }
});

test("(P) Performance view keeps its 0% reference", () => {
  const { root } = surfaceOf({ model: model([100, 101, 102]), viewMode: "performance", timeframe: "7D" });
  assert.equal(root.findAll((n) => n.props?.["data-market-performance-reference"] === 0).length >= 1, true);
  assert.equal(root.findByProps({ "data-market-performance-reference-label": true }).children.join(""), "0%");
});
