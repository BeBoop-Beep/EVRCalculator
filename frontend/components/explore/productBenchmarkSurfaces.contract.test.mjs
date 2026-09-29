import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
const source = fs.readFileSync(new URL("./RankingsProductLensClient.jsx", import.meta.url), "utf8");
test("Product Scores use Benchmark V1 only for RIP Score", () => { assert.match(source, /RankingsRipScoreBadge/); assert.match(source, /metric\(row\.financialRip\)/); assert.match(source, /metric\(row\.setChaseAccessibility\)/); assert.match(source, /metric\(row\.parentSetCollector\)/); assert.doesNotMatch(source, /BenchmarkScoreBadge|readCurrentProductBenchmark/); });
test("rank semantics and inherited Set metrics are explicit", () => { assert.match(source, /Rank \$\{row\.rank\} of \$\{row\.cohortSize\} in the Full Market cohort/); assert.match(source, /inherited from this Product's parent Set/); assert.doesNotMatch(source, /#\$\{row\.rank[^`]*Full Market/); });
test("anonymous and Basic users are gated before Product reads", () => { assert.match(source, /if \(!canViewRankingsIntelligence\) return null/); assert.match(source, /data-product-rankings-locked/); assert.match(source, /PlanLock/); });
test("Scores and Economics render separate desktop and mobile presentations", () => { for (const token of ["data-product-scores-table", "data-product-economics-table", "data-product-score-card", "data-product-economics-card"]) assert.match(source, new RegExp(token)); });
