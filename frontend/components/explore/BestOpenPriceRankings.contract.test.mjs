import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (url) => fs.readFileSync(new URL(url, import.meta.url), "utf8");
const products = read("./RankingsProductLensClient.jsx");
const productRip = read("../pokemon/sealed-product-detail/ProductRipSection.jsx");

function count(haystack, needle) {
  return haystack.split(needle).length - 1;
}

test("Best-Open stays inside the existing Price column instead of adding a twelfth column", () => {
  const colgroup = products.match(/<colgroup>([\s\S]*?)<\/colgroup>/)?.[1] || "";
  assert.equal(count(colgroup, "<col "), 11);
  assert.match(colgroup, /styles\.colPrice/);
  assert.doesNotMatch(products, /colBestOpen|bestOpenPriceColumn/);
  assert.match(products, /data-best-open-price/);
  assert.match(products, /Price \/ Best-Open/);
});

test("Best-Open is reachable only for All Products Full Market Plus presentation", () => {
  assert.match(products, /overall\s*&&\s*budgetKey === "full_market"/);
  assert.match(products, /canViewBestOpenPrice/);
  assert.match(products, /overallResult\?\.bestOpenPrice\?\.available === true/);
  assert.match(products, /bestOpenOnly/);
  assert.match(products, /Closest to #1/);
});

test("desktop and mobile show semantic threshold copy for leader and challenger", () => {
  assert.match(products, /data-best-open-price/);
  assert.match(products, /data-best-open-price-mobile/);
  assert.match(products, /current_number_one_with_headroom/);
  assert.match(products, /Stays #1/);
  assert.match(products, /to #1/);
  assert.match(products, /Best-Open \$\{money\.format\(threshold\)\}/);
});

test("methodology disclosure names the actual Full Market counterfactual", () => {
  assert.match(products, /highest price at which this product would rank #1/);
  assert.match(products, /current published Full Market cohort/);
  assert.match(products, /Other products remain at their published prices/);
  assert.match(products, /published Full Market prices as of/);
});

test("budget responses use a distinct cache namespace from the warmed Full Market lens wrapper", () => {
  assert.match(products, /peek\("products:full_market"\)/);
  assert.match(products, /request\("products:full_market", load/);
  assert.match(products, /sessionCache\.request\(`products:budget:\$\{next\}`/);
  assert.doesNotMatch(products, /sessionCache\.request\(`products:\$\{next\}`/);
});

test("first release remains Rankings-only and does not inject Best-Open into Product RIP detail", () => {
  assert.doesNotMatch(productRip, /Best-Open|bestOpenPrice/);
});
