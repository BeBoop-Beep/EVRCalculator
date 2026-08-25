import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs
  .readFileSync(new URL("./MarketPerformanceChart.jsx", import.meta.url), "utf8")
  .replace(/\r\n/g, "\n");

test("renders one semantic Index 100 reference at its scaled y coordinate", () => {
  assert.match(source, /const referenceY = yAt\(MARKET_INDEX_REFERENCE_VALUE\);/);
  assert.match(source, /data-market-performance-reference="100"[^>]*y1=\{referenceY\}[^>]*y2=\{referenceY\}/);
  assert.equal((source.match(/data-market-performance-reference="100"/g) || []).length, 1);
  assert.doesNotMatch(source, /\[0, 0\.5, 1\]\.map/);
  assert.doesNotMatch(source, /PLOT_TOP \+ fraction \* \(PLOT_BOTTOM - PLOT_TOP\)/);
});

test("labels and accessibly describes the Index 100 reference", () => {
  assert.match(source, /data-market-performance-reference-label/);
  assert.match(source, />\s*100\s*<\/span>/);
  assert.match(source, /Reference line represents Market Index 100\./);
});
