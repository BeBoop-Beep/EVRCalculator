import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./SealedMarketTrendCard.jsx", import.meta.url), "utf8");

test("sealed selector is full width beneath the price summary and title follows section typography", () => {
  const price = source.indexOf("<MarketValueChange");
  const selector = source.indexOf("<MarketWindowSelector");
  const chart = source.indexOf("<ChartFrame");
  assert.ok(price >= 0 && selector > price && chart > selector);
  assert.match(source.slice(selector, chart), /\bfullWidth\b/);
  assert.match(source, /<h2 className="text-lg font-semibold leading-normal text-\[var\(--text-primary\)\] desk:text-sm">Sealed Market<\/h2>/);
  assert.match(source, /useState\("30D"\)/);
});
