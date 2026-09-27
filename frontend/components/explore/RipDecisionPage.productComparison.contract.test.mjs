import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.resolve("components/explore/RipDecisionPage.jsx"), "utf8");
const comparison = source.slice(source.indexOf('data-rip-section="compare-products"'), source.indexOf('data-rip-section="chase-summary"'));

test("Set Product Comparison presents economics and omits retired Product RIP headlines", () => {
  const head = comparison.slice(comparison.indexOf("<thead"), comparison.indexOf("</thead>"));
  const compactHead = head.replace(/\s+/g, " ");
  const labels = ["Product</th>", "Price", "Average Return", "Typical Opening", "Covers Cost", "Top 1% Value Share", "Entertainment Cost"];
  let previous = -1;
  for (const label of labels) { const current = compactHead.indexOf(label); assert.ok(current > previous, label); previous = current; }
  assert.equal((head.match(/<th scope="col"/g) || []).length, 7);
  for (const retired of ["Product Rank", "RIP Score", "RipScoreBadge", "RipTierMark", "overallRipLeaderScore", "publicTier"])
    assert.ok(!comparison.includes(retired), retired);
  assert.match(comparison, /Product Benchmark headlines live on each Product detail page/);
});

test("economics retain the canonical normalized product fields", () => {
  for (const token of ["product.marketPrice", "product.packCount", "product.typicalOpening", "product.entertainmentCost.perPack", "product.chanceToRecoverCost", "product.modeledReturnPercent", "product.topOneOutcomeValueShare"])
    assert.ok(source.includes(token), token);
});

test("comparison performs no Product Benchmark fanout", () => {
  assert.ok(!comparison.includes("readCurrentProductBenchmark"));
  assert.ok(!comparison.includes("useProductBenchmark"));
  assert.ok(!comparison.includes("Promise.all"));
});

test("mobile keeps product identity and price while locking analytical economics", () => {
  assert.ok(comparison.includes("data-set-product-comparison-mobile"));
  assert.ok(source.includes("min-w-0 w-full overflow-hidden p-3"));
  assert.ok(source.includes("<ProductIdentity"));
  assert.ok(source.includes("<LockedValue canView={canView}"));
  assert.ok(source.includes("{money(product.marketPrice)}"));
});

test("hero and every product row share the sealed-product resolver", async () => {
  const { buildSealedProductHref } = await import("./setProductComparison.mjs");
  for (const id of ["booster-pack", "bundle", "etb", "pc-etb", "booster-box"])
    assert.equal(buildSealedProductHref(id), `/sealed-products/${id}`);
  assert.ok(source.includes("href={buildSealedProductHref(heroProduct.sealedProductId)}"));
  assert.ok(source.includes("const href = buildSealedProductHref(product.sealedProductId)"));
});
