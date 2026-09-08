import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const client = read("./MarketExplorerClient.jsx");
const chart = read("./MarketExplorerChart.jsx");
const signal = read("./MarketExplorerSeriesCard.jsx");
const styles = read("./explore.module.css");

test("desktop is one rail plus a right chart-first research canvas", () => {
  assert.match(styles, /grid-template-areas:[\s\S]*?"rail signals"[\s\S]*?"rail active"[\s\S]*?"rail chart"/);
  assert.match(styles, /grid-template-columns: 18rem minmax\(0, 1fr\)/);
  assert.match(styles, /position: sticky/);
});

test("signals are informational and include the honest Graded placeholder", () => {
  assert.doesNotMatch(signal, /aria-pressed|onToggle|<button/);
  assert.match(signal, /Coming soon/);
  assert.match(client, /data-market-explorer-signals/);
});

test("there is one active strip above the chart and no chart visibility legend", () => {
  assert.equal((client.match(/<MarketExplorerActiveMarkets/g) || []).length, 1);
  assert.ok(client.indexOf("<MarketExplorerActiveMarkets") < client.indexOf("<MarketExplorerChart"));
  assert.doesNotMatch(chart, /data-market-explorer-legend-toggle/);
  assert.doesNotMatch(chart, /data-market-explorer-show-all|data-market-explorer-hide-all/);
});

test("the main plot is materially larger and transparent enough for page artwork", () => {
  assert.match(chart, /desk:h-\[38rem\].*2xl:h-\[42rem\]/);
  assert.doesNotMatch(client, /marketExplorerAnalysis} set-glass-surface/);
});

test("tablet and mobile intentionally stack with chart before the Builder", () => {
  assert.match(styles, /max-width: 1199\.98px/);
  assert.match(styles, /data-market-explorer-chart-pane[^}]*order: 3/);
  assert.match(styles, /data-market-explorer-filters[^}]*order: 4/);
});
