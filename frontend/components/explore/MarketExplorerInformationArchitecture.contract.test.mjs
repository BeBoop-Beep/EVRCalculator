import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("Market Explorer uses a graph-first desktop workspace and compact mobile controls", async () => {
  const source = await read("./MarketExplorerClient.jsx");
  assert.match(source, />Market Explorer<\/h1>/);
  assert.match(source, /data-market-explorer-workspace/);
  assert.match(source, /desk:grid-cols-\[minmax\(21rem,24rem\)_minmax\(0,1fr\)\]/);
  assert.doesNotMatch(source.slice(source.indexOf('data-market-explorer-zone="compare"'),
    source.indexOf('aria-labelledby="compare-markets-zone-heading"')), /set-glass-surface/);
  assert.match(source, /data-market-explorer-sidebar/);
  assert.match(source, /data-market-explorer-mobile-tools/);
  assert.match(source, /desk:hidden/);
  assert.match(source, /mobileToolsOpen \? "block" : "hidden"/);

  const explore = source.indexOf('data-market-explorer-zone="explore"');
  const compare = source.indexOf('data-market-explorer-zone="compare"');
  const filter = source.indexOf('data-market-explorer-sidebar-section="filter"');
  const build = source.indexOf('data-market-explorer-zone="build"');
  const sidebarEnd = source.indexOf("</aside>", explore);
  const active = source.indexOf("data-market-explorer-active-strip", compare);
  const graph = source.indexOf("data-market-explorer-graph", compare);
  const overview = source.indexOf("data-market-explorer-signals", compare);
  const results = source.indexOf("data-market-explorer-compare-results", compare);
  assert.ok(explore >= 0 && compare >= 0 && filter >= 0 && build >= 0);
  assert.ok(filter < sidebarEnd && sidebarEnd < build && build < compare, "sidebar tools precede the independent overlay and graph");
  assert.ok(source.indexOf("<MarketExplorerBrowse", explore) < compare);
  assert.ok(source.indexOf("<MarketExplorerScreens", explore) < compare);
  assert.ok(active < graph && graph < results);
  assert.match(source.slice(overview, overview + 160), /order-3/);
  assert.match(source.slice(graph, graph + 120), /order-2/);
  assert.ok(source.indexOf("<MarketExplorerQueryBuilder", filter) > filter);
  assert.ok(source.indexOf("<MarketExplorerExactBasket", build) > build);
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

test("one constituent workspace replaces the chart presentation without unmounting either owner", async () => {
  const source = await read("./MarketExplorerClient.jsx");
  assert.equal(source.match(/<MarketExplorerConstituents\s/g)?.length, 1);
  assert.equal(source.match(/<MarketExplorerChart\s/g)?.length, 1);
  assert.match(source, /data-market-explorer-mode=\{workspaceMode\}/);
  assert.match(source, /aria-hidden=\{workspaceMode === "constituents"\}/);
  assert.match(source, /mode=\{workspaceMode === "chart" \? "preview" : "expanded"\}/);
  assert.ok(source.indexOf("<MarketExplorerConstituents") < source.indexOf("<MarketExplorerDetails"));
});

test("desktop, tablet, and mobile keep separate scroll and width owners", async () => {
  const [client, browse, constituents, chart, styles, tailwind] = await Promise.all([
    read("./MarketExplorerClient.jsx"), read("./MarketExplorerBrowse.jsx"),
    read("./MarketExplorerConstituents.jsx"), read("./MarketExplorerChart.jsx"),
    read("./explore.module.css"), read("../../tailwind.config.js"),
  ]);
  assert.match(tailwind, /desk:\s*"1200px"/);
  for (const width of [1728, 1440]) {
    assert.ok(width - 24 * 16 - 16 > width / 2, "the main analysis column remains dominant");
  }
  for (const width of [768, 390]) assert.ok(width < 1200, "tablet and mobile use the stacked layout");
  assert.match(client, /min-w-0 gap-3 desk:grid-cols-\[minmax\(21rem,24rem\)_minmax\(0,1fr\)\]/);
  assert.match(client, /data-market-explorer-mobile-tools/);
  assert.match(client, /desk:max-h-\[calc\(100vh-7rem\)\] desk:overflow-y-auto/);
  assert.match(styles, /\.explorerZoneBrowse\s*\{\s*overflow:\s*visible;/);
  assert.match(browse, /max-h-\[min\(25rem,55vh\)\] overflow-y-auto/);
  assert.match(browse, /min-h-11 min-w-0 flex-1/);
  assert.match(chart, /min-w-0 overflow-x-auto pb-1/);
  assert.match(constituents, /hidden overflow-x-auto[^`]*desk:block/);
  assert.match(constituents, /data-market-constituents-cards[^\n]*desk:hidden/);
  assert.match(constituents, /max-h-\[75vh\] overflow-y-auto desk:max-h-none/);
});
