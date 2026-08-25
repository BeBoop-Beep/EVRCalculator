import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const source = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "MiniMarketSparkline.jsx"), "utf8");

test("mini sparkline is a passive, lightweight real-coordinate SVG", () => {
  assert.match(source, /<svg data-mini-market-sparkline/);
  assert.match(source, /<polyline points=\{coordinates\}/);
  assert.match(source, /buildMarketSparklineDomain/);
  assert.doesNotMatch(source, /useState|onPointer|onMouse|tooltip|createPortal|tabIndex/);
});

test("insufficient data renders a neutral dash instead of an invented shape", () => {
  assert.match(source, /valid\.length < 2/);
  assert.match(source, /data-mini-market-sparkline-empty/);
});
