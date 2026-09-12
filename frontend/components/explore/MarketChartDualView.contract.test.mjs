import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");

test("Market and Explorer share one accessible view toggle and default to Performance", () => {
  const toggle = read("./MarketChartViewToggle.jsx");
  const market = read("./PokemonMarketPerformance.jsx");
  const explorer = read("./MarketExplorerChart.jsx");
  assert.match(toggle, /aria-pressed=\{selected\}/);
  assert.match(toggle, /data-market-chart-view=\{option\.value\}/);
  for (const source of [market, explorer]) {
    assert.match(source, /useState\(MARKET_CHART_VIEW_PERFORMANCE\)/);
    assert.match(source, /<MarketChartViewToggle value=\{viewMode\} onChange=\{setViewMode\}/);
    assert.match(source, /viewMode=\{viewMode\}/);
  }
});

test("mode switching is local presentation state with no network owner", () => {
  const toggle = read("./MarketChartViewToggle.jsx");
  const chart = read("./MarketPerformanceChart.jsx");
  assert.doesNotMatch(toggle, /fetch\(|axios|router\.|searchParams/);
  assert.doesNotMatch(chart, /fetch\(|axios|router\.|searchParams/);
});

test("shared chart selects mode-specific projection, domain, reference and tooltip priority", () => {
  const chart = read("./MarketPerformanceChart.jsx");
  assert.match(chart, /projectMarketChartValues\(entry\.values \|\| \[\], viewMode\)/);
  assert.match(chart, /buildMarketPerformanceDomain\(allValues, timeframe\)/);
  assert.match(chart, /buildRelativePerformanceDomain\(allValues\)/);
  assert.match(chart, /isMarketIndexReferenceVisible/);
  assert.match(chart, /Market Index \{reading\.rawValue/);
  assert.match(chart, /Performance \{reading\.performanceValue/);
});

test("mode-specific notes explain rebasing versus canonical lifetime levels", () => {
  for (const source of [read("./PokemonMarketPerformance.jsx"), read("./MarketExplorerChart.jsx")]) {
    assert.match(source, /Each market starts at 0% at its first available observation/);
    assert.match(source, /index levels remain based on each market's lifetime chain-linked history/);
  }
});
