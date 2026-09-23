import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("Market Explorer uses a graph-first desktop workspace and compact mobile controls", async () => {
  const source = await read("./MarketExplorerClient.jsx");
  assert.doesNotMatch(source, /data-market-explorer-product-header/);
  assert.match(source, /data-market-explorer-workspace/);
  assert.match(source, /desk:grid-cols-\[minmax\(19rem,22rem\)_minmax\(0,1fr\)\]/);
  assert.match(source, /data-market-explorer-sidebar/);
  assert.match(source, /data-market-explorer-mobile-tools/);
  assert.match(source, /desk:hidden/);
  assert.match(source, /mobileToolsOpen \? "block" : "hidden"/);

  const explore = source.indexOf('data-market-explorer-zone="explore"');
  const compare = source.indexOf('data-market-explorer-zone="compare"');
  const build = source.indexOf('data-market-explorer-zone="build"');
  const sidebarEnd = source.indexOf("</aside>", explore);
  const active = source.indexOf("data-market-explorer-active-strip", compare);
  const graph = source.indexOf("data-market-explorer-graph", compare);
  const results = source.indexOf("data-market-explorer-compare-results", compare);
  assert.ok(explore >= 0 && compare >= 0 && build >= 0);
  assert.ok(sidebarEnd < build && build < compare, "browse rail precedes the unified builder overlay and graph");
  assert.ok(source.indexOf("<MarketExplorerBrowse", explore) < compare);
  assert.ok(source.indexOf("<MarketExplorerScreens", explore) < compare);
  assert.ok(active < graph && graph < results);
  assert.match(source.slice(graph, graph + 120), /order-2/);
  assert.equal(source.indexOf('data-market-explorer-sidebar-section="filter"'), -1);
  assert.ok(source.indexOf("<MarketExplorerQueryBuilder", build) > build);
  assert.ok(source.indexOf("<MarketExplorerExactBasket", build) > build);
  assert.ok(source.indexOf("View Constituents & Comparison", graph) > graph);
  assert.equal(source.match(/<MarketExplorerBrowse/g)?.length, 1);
  assert.equal(source.match(/<MarketExplorerScreens/g)?.length, 1);
  assert.equal(source.match(/<MarketExplorerQueryBuilder/g)?.length, 1);
  assert.equal(source.match(/<MarketExplorerExactBasket/g)?.length, 1);
});

test("chart toolbar keeps the primary toggle left and responsive timeframes right", async () => {
  const chart = await read("./MarketExplorerChart.jsx");
  const toggle = await read("./MarketChartViewToggle.jsx");
  const windows = await read("./MarketOverviewWindowSelector.jsx");
  assert.match(chart, /data-market-explorer-chart-toolbar/);
  assert.ok(chart.indexOf("<MarketChartViewToggle") < chart.indexOf("<MarketExplorerTimeframeSelector"));
  assert.match(chart, /desk:flex-row/);
  assert.match(toggle, /min-h-10/);
  assert.match(toggle, /bg-cyan-400\/15/);
  assert.match(windows, /min-w-max flex-nowrap/);
});
