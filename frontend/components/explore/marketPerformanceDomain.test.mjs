import test from "node:test";
import assert from "node:assert/strict";
import { buildMarketPerformanceDomain } from "./marketPerformanceDomain.mjs";

function assertContainsReference(values) {
  const [domainMin, domainMax] = buildMarketPerformanceDomain(
    values.map((value) => ({ value }))
  );
  assert.ok(domainMin < 100, `${domainMin} should be below 100`);
  assert.ok(domainMax > 100, `${domainMax} should be above 100`);
}

test("keeps Index 100 visible when all active values are above it", () => {
  assertContainsReference([104, 105, 106, 107]);
});

test("keeps Index 100 visible when all active values are below it", () => {
  assertContainsReference([96, 93]);
});

test("keeps Index 100 visible for mixed values", () => {
  assertContainsReference([97, 101, 106]);
});

test("keeps Index 100 visible as visibility leaves one series on either side", () => {
  assertContainsReference([106, 107]);
  assertContainsReference([97, 98]);
});
