import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs
  .readFileSync(new URL("./MarketPerformanceChart.jsx", import.meta.url), "utf8")
  .replace(/\r\n/g, "\n");

test("renders one semantic zero-performance reference at its scaled y coordinate", () => {
  assert.match(source, /const referenceValue = isIndexView \? MARKET_INDEX_REFERENCE_VALUE : 0;/);
  assert.match(source, /const referenceY = yAt\(referenceValue\);/);
  assert.match(source, /data-market-performance-reference=\{referenceValue\}[^>]*y1=\{referenceY\}[^>]*y2=\{referenceY\}/);
  assert.doesNotMatch(source, /\[0, 0\.5, 1\]\.map/);
  assert.doesNotMatch(source, /PLOT_TOP \+ fraction \* \(PLOT_BOTTOM - PLOT_TOP\)/);
});

test("labels zero percent and preserves raw Market Index in the tooltip", () => {
  assert.match(source, /data-market-performance-reference-label/);
  assert.match(source, /isIndexView \? formatIndexValue\(referenceValue\) : "0%"/);
  assert.match(source, /Market Index \{reading\.rawValue/);
  assert.match(source, /referenceVisible \? <line/);
  assert.match(source, /referenceVisible \? <span/);
});
