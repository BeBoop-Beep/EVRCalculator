import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { formatRecoverCost, PRODUCT_SCORE_COLUMNS } from "./productRankingsPresentation.mjs";

test("Product labels expose Chase and inherited Collector Appeal", () => {
  assert.deepEqual(PRODUCT_SCORE_COLUMNS, ["Rank", "Product", "Product Overall", "Financial", "Chase", "Collector Appeal"]);
  const source = fs.readFileSync(new URL("./RankingsProductLensClient.jsx", import.meta.url), "utf8");
  assert.match(source, /parent Set/);
  assert.doesNotMatch(source, /Set Collector/);
});

test("Recover Cost adaptive precision never rounds a positive value to zero", () => {
  assert.equal(formatRecoverCost(0), "0%");
  assert.equal(formatRecoverCost(0.099126), "9.9%");
  assert.equal(formatRecoverCost(0.0038), "0.38%");
  assert.equal(formatRecoverCost(0.0004), "0.04%");
  assert.equal(formatRecoverCost(0.00002), "0.002%");
  assert.equal(formatRecoverCost(0.000002), "0.0002%");
  assert.equal(formatRecoverCost(null), "—");
});

test("desktop and mobile use the same Recover Cost formatter", () => {
  const source = fs.readFileSync(new URL("./RankingsProductLensClient.jsx", import.meta.url), "utf8");
  assert.equal(source.match(/formatRecoverCost\(row\.chanceToRecoverCost\)/g)?.length, 2);
});
