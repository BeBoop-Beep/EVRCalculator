import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { PRODUCT_ECONOMICS_COLUMNS, PRODUCT_SCORE_COLUMNS, bestOpenDetails, filterProductRows, productFamilyOptions, sortProductRows } from "./productRankingsPresentation.mjs";

const source = fs.readFileSync(new URL("./RankingsProductLensClient.jsx", import.meta.url), "utf8");
const lazy = fs.readFileSync(new URL("./RankingsLazyClient.jsx", import.meta.url), "utf8");
const badge = fs.readFileSync(new URL("./RipScoreBadge.jsx", import.meta.url), "utf8");
const bestOpenPopover = fs.readFileSync(new URL("./BestOpenDetailsPopover.jsx", import.meta.url), "utf8");

test("Product Scores and Economics expose the exact split column contracts", () => {
  assert.deepEqual(PRODUCT_SCORE_COLUMNS, ["Rank", "Product", "Product Overall", "Financial", "Chase", "Collector Appeal"]);
  assert.deepEqual(PRODUCT_ECONOMICS_COLUMNS, ["Product", "Unit Price", "Best-Open Price", "EV / Pack", "Modeled Return", "Recover Cost"]);
  for (const label of [...PRODUCT_SCORE_COLUMNS, ...PRODUCT_ECONOMICS_COLUMNS]) assert.ok(source.includes(label), label);
  assert.doesNotMatch(source, /Typical Opening|Typical Retention|typicalOpening|typicalRetention/);
});

test("Product RIP stays an explicit absolute 0-100 score", () => {
  assert.ok(source.includes("metric(row.ripScore?.scoreValue)"));
  assert.ok(!source.includes("<RankingsRipScoreBadge"));
  assert.ok(!source.includes('Full Market 5.0 reference'));
  assert.doesNotMatch(source, /Above Full Market benchmark|Below family benchmark|Above Pokémon benchmark/);
  assert.doesNotMatch(source, /`#\$\{row\.rank[^`]*Full Market/);
});

test("Scores default and Economics use independent parameterized session-cache requests", () => {
  assert.ok(source.includes('useState("scores")'));
  assert.ok(source.includes("readProductRankings(view"));
  assert.ok(source.includes("sessionCache"));
  assert.ok(source.includes("page_size: PAGE_SIZE"));
  assert.doesNotMatch(lazy, /loadProductRankingsAuthorities|products:full_market/);
});

test("legacy local helpers remain deterministic for non-paginated consumers", () => {
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

test("Best-Open uses explicit exact-price direction and never raw enums", () => {
  assert.equal(bestOpenDetails({ bestOpenPrice: 80, bestOpenMarketPrice: 100 }).differenceText, "+$20.00 · +20.0%");
  assert.match(bestOpenDetails({ bestOpenPrice: 120, bestOpenMarketPrice: 100 }).interpretation, /market price is \$20\.00 below/);
  assert.ok(bestOpenPopover.includes("Best-Open:"));
  assert.ok(!bestOpenPopover.includes("resolved_below_market"));
});

test("inherited metrics and Full Market scope use B4 labels", () => {
  assert.ok(source.includes('chaseScore: "Chase"'));
  assert.ok(source.includes('collectorAppeal: "Collector Appeal"'));
  assert.ok(source.includes("inherited from this Product's parent Set"));
  assert.ok(source.includes("Current Full Market Product cohort"));
  assert.ok(!source.includes("Full Market authority"));
});
