import test from "node:test";
import assert from "node:assert/strict";
import { buildMarketSparklineDomain } from "./marketSparklineDomain.mjs";

test("positive price domains are local and contain every real point", () => {
  const [lower, upper] = buildMarketSparklineDomain([{ value: 6000 }, { value: 6242.18 }, { value: 5900 }]);
  assert.ok(lower > 0);
  assert.ok(lower < 5900 && upper > 6242.18);
});

test("flat series receive the three-percent visual-span floor", () => {
  const [lower, upper] = buildMarketSparklineDomain([{ value: 1000 }, { value: 1001 }]);
  assert.ok(upper - lower >= 30);
  assert.ok(lower < 1000 && upper > 1001);
});

test("meaningful movement remains fully visible", () => {
  const [lower, upper] = buildMarketSparklineDomain([{ price: 10 }, { price: 16 }, { price: 12 }], { valueKey: "price" });
  assert.ok(lower < 10 && upper > 16);
  assert.ok(upper - lower < 10);
});

test("null, zero, and empty input are safe", () => {
  assert.deepEqual(buildMarketSparklineDomain([]), [0, 1]);
  const domain = buildMarketSparklineDomain([{ value: null }, { value: 0 }]);
  assert.ok(domain.every(Number.isFinite));
  assert.ok(domain[0] < 0 && domain[1] > 0);
});
