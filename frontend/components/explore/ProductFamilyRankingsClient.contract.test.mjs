import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.resolve("components/explore/ProductFamilyRankingsClient.jsx"), "utf8");
const page = fs.readFileSync(path.resolve("app/Explore/page.js"), "utf8");

test("one Rankings page switches between Sets and non-empty product families", () => {
  assert.ok(page.includes("ProductFamilyRankingsClient"));
  assert.ok(source.includes('value: "sets", label: "Sets"'));
  assert.ok(source.includes('variant="primary"'));
  assert.ok(source.includes("SegmentedControl"));
  assert.ok(source.includes("Number(block?.count) > 0"));
  assert.ok(!source.includes('families["all"]'));
});

test("desktop and mobile preserve canonical family identity and official rank", () => {
  assert.ok(source.includes("product.familyRank"));
  assert.ok(source.includes("product.productFamilyLabel"));
  assert.ok(source.includes('className="hidden overflow-x-auto md:block"'));
  assert.ok(source.includes('className="space-y-2 p-3 md:hidden"'));
});

test("all required product metrics are presentation-sort choices", () => {
  for (const metric of ["overallRipScore", "financialRipScore", "collectorAppealScore", "marketPrice", "expectedValue", "medianValue", "chanceToRecoverCost"]) {
    assert.ok(source.includes(metric), metric);
  }
  assert.ok(source.includes("a.familyRank - b.familyRank"));
});

test("product navigation uses the set RIP route and preserves sealed product context", () => {
  assert.ok(source.includes("buildTcgSetHrefFromTarget"));
  assert.ok(source.includes("sealedProduct="));
});

test("a locked Overall tab exists and shows only Coming Soon, with no ranking data or budget controls", () => {
  assert.ok(source.includes('value: "overall-locked"'), "the Overall tab exists as a distinct view");
  assert.ok(source.includes('label: "Overall"'), "the tab is labeled Overall");
  assert.ok(source.includes("OverallRankingLockedPanel"), "a dedicated locked panel component renders it");
  assert.ok(source.includes("Coming Soon"), "the locked panel says Coming Soon");

  // No real ranking data, no budget selector, no entitlement/tier disclosure.
  const forbidden = [
    "budgetRank", "budgetTier", "overallRipV10Score", "financialRipV4Score",
    "$25", "$50", "$100", "$150", "$250", "$500",
    "Index Plus", "Index Premium", "Premium",
  ];
  for (const term of forbidden) {
    assert.equal(source.includes(term), false, `locked Overall surface must not reference ${term}`);
  }
});
