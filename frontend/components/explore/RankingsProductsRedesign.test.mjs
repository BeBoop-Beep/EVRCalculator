import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { PRODUCT_ECONOMICS_COLUMNS, PRODUCT_SCORE_COLUMNS, bestOpenGap, filterProductRows, productFamilyOptions, sortProductRows } from "./productRankingsPresentation.mjs";

const source = fs.readFileSync(new URL("./RankingsProductLensClient.jsx", import.meta.url), "utf8");
const lazy = fs.readFileSync(new URL("./RankingsLazyClient.jsx", import.meta.url), "utf8");
const badge = fs.readFileSync(new URL("./RipScoreBadge.jsx", import.meta.url), "utf8");

test("Product Scores and Economics expose the exact split column contracts", () => {
  assert.deepEqual(PRODUCT_SCORE_COLUMNS, ["Rank", "Product", "RIP Score", "Financial", "Set Chase", "Set Collector"]);
  assert.deepEqual(PRODUCT_ECONOMICS_COLUMNS, ["Product", "Unit Price", "Best-Open Price", "EV / Pack", "Modeled Return", "Recover Cost"]);
  for (const label of [...PRODUCT_SCORE_COLUMNS, ...PRODUCT_ECONOMICS_COLUMNS]) assert.ok(source.includes(label), label);
  assert.doesNotMatch(source, /Typical Opening|Typical Retention|typicalOpening|typicalRetention/);
});

test("Product RIP uses the octagonal Benchmark-10 primitive without row prose", () => {
  assert.ok(badge.includes("numeric.toFixed(1)"), "Benchmark-10 scores, including 7.38, format to one decimal (7.4)");
  assert.ok(source.includes("<RankingsRipScoreBadge"));
  assert.ok(source.includes('benchmarkLabel="Full Market 5.0 reference"'));
  assert.doesNotMatch(source, /Above Full Market benchmark|Below family benchmark|Above Pokémon benchmark/);
  assert.doesNotMatch(source, /`#\$\{row\.rank[^`]*Full Market/);
});

test("Scores default and Economics lazy loading have independent last-good state", () => {
  assert.ok(source.includes('useState("scores")'));
  assert.ok(source.includes("states[view]"));
  assert.ok(source.includes("readProductRankings(target"));
  assert.ok(source.includes("beginLastGoodRefresh(current[target]"));
  assert.ok(source.includes("failLastGoodRefresh(current[target]"));
  assert.ok(source.includes("if (!canViewRankingsIntelligence) return null"));
  assert.doesNotMatch(lazy, /loadProductRankingsAuthorities|products:full_market/);
});

test("family filtering, search, and sorting operate locally", () => {
  const rows = [
    { sealedProductId: "box", productName: "Alpha Box", setName: "Alpha", familyKey: "booster_box", familyName: "Booster Box", rank: 2 },
    { sealedProductId: "pack", productName: "Beta Pack", setName: "Beta", familyKey: "loose_booster_pack", familyName: "Booster Pack", rank: 1 },
    { sealedProductId: "etb", productName: "Gamma ETB", setName: "Gamma", familyKey: "elite_trainer_box", familyName: "Elite Trainer Box", rank: 3 },
  ];
  assert.deepEqual(productFamilyOptions(rows).map((entry) => entry.label), ["Booster Box", "Booster Pack", "Elite Trainer Box"]);
  assert.deepEqual(filterProductRows(rows, { family: "booster_box" }).map((row) => row.sealedProductId), ["box"]);
  assert.deepEqual(filterProductRows(rows, { query: "beta" }).map((row) => row.sealedProductId), ["pack"]);
  assert.deepEqual(sortProductRows(rows, "rank").map((row) => row.rank), [1, 2, 3]);
});

test("Best-Open gap uses neutral human wording and never raw enums", () => {
  assert.equal(bestOpenGap({ bestOpenPriceGapDollars: 11.21, bestOpenPriceGapPercent: .124, bestOpenStatus: "resolved_below_market" }), "$11.21 below market · 12.4%");
  assert.equal(bestOpenGap({ bestOpenPriceGapDollars: 4, bestOpenStatus: "current_number_one_with_headroom" }), "$4.00 headroom");
  assert.ok(source.includes("Best-Open as of"));
  assert.ok(!source.includes("resolved_below_market"));
});

test("inherited metrics and Full Market pricing scope are explicit once", () => {
  assert.ok(source.includes("Set Chase"));
  assert.ok(source.includes("Set Collector"));
  assert.ok(source.includes("inherited from this Product's parent Set"));
  assert.ok(source.includes("Full Market pricing"));
  assert.ok(!source.includes("Full Market authority"));
});
