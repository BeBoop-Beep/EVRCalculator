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
  const workspace = source.indexOf("data-market-explorer-chart-workspace", compare);
  const graph = source.indexOf("data-market-explorer-graph", compare);
  const results = source.indexOf("data-market-explorer-compare-results", compare);
  assert.ok(explore >= 0 && compare >= 0 && build >= 0);
  assert.ok(sidebarEnd < build && build < compare, "browse rail precedes the unified builder overlay and graph");
  assert.ok(source.indexOf("<MarketExplorerBrowse", explore) < compare);
  assert.ok(source.indexOf("<MarketExplorerScreens", explore) < compare);
  assert.ok(active < workspace && workspace < graph && graph < results);
  assert.doesNotMatch(source, /desk:row-start-2/);
  assert.doesNotMatch(source, /data-market-explorer-research-peek/);
  assert.match(source, /inert=\{detailsOpen \? true : undefined\}/);
  assert.equal(source.indexOf('data-market-explorer-sidebar-section="filter"'), -1);
  assert.ok(source.indexOf("<MarketExplorerQueryBuilder", build) > build);
  assert.ok(source.indexOf("<MarketExplorerExactBasket", build) > build);
  assert.match(source, /data-market-explorer-hide-details/);
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
  assert.match(chart, /data-market-explorer-view-details/);
  assert.match(chart, /desk:h-\[calc\(100dvh-23rem\)\]/);
  assert.doesNotMatch(chart, /desk:h-\[40rem\]/);
  assert.doesNotMatch(chart, /2xl:h-\[46rem\]/);
  assert.match(chart, /desk:flex-row/);
  assert.ok(toggle.indexOf("MARKET_CHART_VIEW_INDEX") < toggle.indexOf("MARKET_CHART_VIEW_PERFORMANCE, label"));
  assert.match(toggle, /value = MARKET_CHART_VIEW_INDEX/);
  assert.match(toggle, /min-h-10/);
  assert.match(toggle, /bg-cyan-400\/15/);
  assert.match(windows, /min-w-max flex-nowrap/);
});
