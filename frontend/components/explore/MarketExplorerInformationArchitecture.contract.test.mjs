import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("Market Explorer exposes the Phase 7 product promise and intent-zone order", async () => {
  const source = await read("./MarketExplorerClient.jsx");
  assert.match(source, />Market Explorer<\/h1>/);
  assert.match(source, /Explore\. Compare\. Build your own Pokémon markets\./);
  const explore = source.indexOf('data-market-explorer-zone="explore"');
  const compare = source.indexOf('data-market-explorer-zone="compare"');
  const build = source.indexOf('data-market-explorer-zone="build"');
  assert.ok(explore >= 0 && explore < compare && compare < build);
  assert.ok(source.indexOf("<MarketExplorerBrowse", explore) < compare);
  assert.ok(source.indexOf("<MarketExplorerScreens", compare) < build);
  assert.ok(source.indexOf("<MarketExplorerQueryBuilder", build) > build);
  assert.ok(source.indexOf("<MarketExplorerExactBasket", build) > build);
});

test("chart toolbar keeps the primary toggle left and responsive timeframes right", async () => {
  const chart = await read("./MarketExplorerChart.jsx");
  const toggle = await read("./MarketChartViewToggle.jsx");
  const windows = await read("./MarketOverviewWindowSelector.jsx");
  assert.match(chart, /data-market-explorer-chart-toolbar/);
  assert.ok(chart.indexOf("<MarketChartViewToggle") < chart.indexOf("<MarketExplorerTimeframeSelector"));
  assert.match(chart, /desk:flex-row/);
  assert.match(toggle, /min-h-10/);
  assert.match(toggle, /rgba\(45,212,191,0\.18\)/);
  assert.match(windows, /min-w-max flex-nowrap/);
});
