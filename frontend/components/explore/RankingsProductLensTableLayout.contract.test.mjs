import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
const jsx = fs.readFileSync(new URL("./RankingsProductLensClient.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("./explore.module.css", import.meta.url), "utf8");
test("split Product tables use explicit fixed-layout geometry", () => { for (const name of ["productScoresTable", "productEconomicsTable", "productRankColumn", "productIdentityColumn", "productRipColumn", "productMetricColumn", "productEconomicsColumn"]) { assert.ok(jsx.includes(`styles.${name}`), name); assert.match(css, new RegExp(`\\.${name}`)); } assert.match(css, /\.productScoresTable,[\s\S]*table-layout:\s*fixed/); });
test("Scores and Economics do not share mixed columns", () => { const scores = jsx.slice(jsx.indexOf("function ScoresTable"), jsx.indexOf("function BestOpen")); const economics = jsx.slice(jsx.indexOf("function EconomicsTable"), jsx.indexOf("function freshnessContext")); assert.doesNotMatch(scores, /Unit Price|Best-Open Price|EV \/ Pack/); assert.doesNotMatch(economics, /RIP Score|Set Chase|Set Collector/); assert.doesNotMatch(jsx, /Units|Committed|Strategy/); });
test("mobile cards replace horizontal Product tables below desktop", () => { assert.match(jsx, /desk:hidden/); assert.match(jsx, /hidden overflow-x-auto desk:block/); assert.match(jsx, /data-product-score-card/); assert.match(jsx, /data-product-economics-card/); });
