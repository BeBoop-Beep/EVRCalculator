import test from "node:test";
import assert from "node:assert/strict";
import { buildMarketPerformanceDomain, buildRelativePerformanceDomain, toSelectedWindowPerformance } from "./marketPerformanceDomain.mjs";

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
