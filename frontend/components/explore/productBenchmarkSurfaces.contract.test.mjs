import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
const source = fs.readFileSync(new URL("./RankingsProductLensClient.jsx", import.meta.url), "utf8");
test("Product Scores keep absolute values out of the Benchmark-10 primitive", () => { assert.match(source, /metric\(row\.ripScore\?\.scoreValue\)/); assert.match(source, /metric\(row\.financialRip\)/); assert.match(source, /metric\(row\.chaseScore\)/); assert.match(source, /metric\(row\.collectorAppeal\)/); assert.doesNotMatch(source, /RankingsRipScoreBadge|Full Market 5\.0 reference|readCurrentProductBenchmark/); });
test("rank and inherited Set semantics are explicit", () => { assert.match(source, /Current Full Market Product cohort/); assert.match(source, /inherited from this Product's parent Set/); });
test("anonymous and Basic users use the identity-only public reader", () => { assert.match(source, /publicMode \? await readPublicProductCatalogue/); assert.match(source, /readProductRankings\(view/); assert.match(source, /<Locked/); });
test("Scores and Economics render separate desktop and mobile presentations", () => { for (const token of ["data-product-scores-table", "data-product-economics-table", "data-product-score-card", "data-product-economics-card"]) assert.match(source, new RegExp(token)); });
