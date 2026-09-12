import test from "node:test";
import assert from "node:assert/strict";
import {
  buildMarketPerformanceDomain,
  buildRelativePerformanceDomain,
  isMarketIndexReferenceVisible,
  MARKET_CHART_VIEW_INDEX,
  MARKET_CHART_VIEW_PERFORMANCE,
  projectMarketChartValues,
  toSelectedWindowPerformance,
} from "./marketPerformanceDomain.mjs";

const domain = (values, timeframe) => buildMarketPerformanceDomain(values.map((value) => ({ value })), timeframe);

test("7D and 30D scale to visible data instead of blindly forcing 100", () => {
  for (const timeframe of ["7D", "30D"]) {
    const [minimum, maximum] = domain([102.2, 102.8], timeframe);
    assert.ok(minimum > 100);
    assert.ok(minimum < 102.2 && maximum > 102.8);
    assert.ok(maximum - minimum < 2);
  }
});

test("flat short-window data retains a restrained minimum-span guard", () => {
  const [minimum, maximum] = domain([102.45, 102.5], "1D");
  assert.ok(maximum - minimum >= 0.75);
  assert.ok(maximum - minimum < 1.5);
});

test("all visible series contribute to the shared domain", () => {
  const [minimum, maximum] = domain([98.5, 99, 104, 105.5], "3M");
  assert.ok(minimum < 98.5);
  assert.ok(maximum > 105.5);
});

test("long windows retain Index 100 reference context", () => {
  for (const timeframe of ["6M", "1Y", "All"]) {
    const [minimum, maximum] = domain([104, 107], timeframe);
    assert.ok(minimum < 100 && maximum > 100);
  }
});

test("domain calculation never changes point values", () => {
  const values = [102.47, 102.52];
  domain(values, "7D");
  assert.deepEqual(values, [102.47, 102.52]);
});

test("selected-window performance anchors each series at its first non-null point", () => {
  const values = toSelectedWindowPerformance([null, 98, 99.96, null]);
  assert.deepEqual(values.slice(0, 2), [null, 0]);
  assert.ok(Math.abs(values[2] - 2) < 1e-9);
  assert.equal(values[3], null);
});

test("relative domain includes zero and uses an honest 0.75 point minimum span", () => {
  const [minimum, maximum] = buildRelativePerformanceDomain([{ value: 0 }, { value: 0.03 }]);
  assert.ok(minimum <= 0 && maximum >= 0.03);
  assert.ok(maximum - minimum >= 0.75 && maximum - minimum < 1);
});

test("7D and 30D display endpoints equal the published start/end return formula", () => {
  for (const values of [[100, 99.09], [98.52, 101.31]]) {
    const display = toSelectedWindowPerformance(values);
    const published = (values.at(-1) / values[0] - 1) * 100;
    assert.ok(Math.abs(display.at(-1) - published) < 1e-12);
  }
});

test("each selected timeframe gets an independent performance baseline", () => {
  const sevenDay = projectMarketChartValues([108.2, 108.05, 108.01], MARKET_CHART_VIEW_PERFORMANCE);
  const thirtyDay = projectMarketChartValues([114.39, 110, 108.01], MARKET_CHART_VIEW_PERFORMANCE);
  assert.equal(sevenDay[0], 0);
  assert.equal(thirtyDay[0], 0);
  assert.notEqual(sevenDay.at(-1), thirtyDay.at(-1));
});

test("All independently rebases each series and preserves leading nulls", () => {
  assert.deepEqual(projectMarketChartValues([100, 105], MARKET_CHART_VIEW_PERFORMANCE), [0, 5.000000000000004]);
  assert.deepEqual(projectMarketChartValues([null, null, 80, 84], MARKET_CHART_VIEW_PERFORMANCE), [null, null, 0, 5.000000000000004]);
});

test("Index projection returns canonical levels without mutating the source", () => {
  const raw = [108.2, 108.05, 108.01];
  const display = projectMarketChartValues(raw, MARKET_CHART_VIEW_INDEX);
  assert.deepEqual(display, raw);
  assert.notEqual(display, raw);
  assert.deepEqual(raw, [108.2, 108.05, 108.01]);
});

test("Index 100 reference is visible only when the raw domain contains it", () => {
  assert.equal(isMarketIndexReferenceVisible([99, 102]), true);
  assert.equal(isMarketIndexReferenceVisible([107.5, 108.5]), false);
});
