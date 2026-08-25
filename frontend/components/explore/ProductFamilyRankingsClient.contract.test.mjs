import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.resolve("components/explore/ProductFamilyRankingsClient.jsx"), "utf8");
const page = fs.readFileSync(path.resolve("app/Explore/page.js"), "utf8");

test("one Rankings page switches between Sets and non-empty product families", () => {
  assert.ok(page.includes("ProductFamilyRankingsClient"));
  assert.ok(source.includes('value:"sets",label:"Sets"'));
  assert.ok(source.includes('value:"products",label:"Products"'));
  assert.ok(!source.includes('label: "Individual Products"'));
  assert.ok(source.includes('variant="primary"'));
  assert.ok(source.includes("SegmentedControl"));
  assert.ok(source.includes("Number(block?.count) > 0"));
  assert.ok(!source.includes('families["all"]'));
});

test("desktop and mobile preserve canonical family identity and official rank", () => {
  assert.ok(source.includes("p.familyRank"));
  assert.ok(source.includes("p.productFamilyLabel"));
  assert.ok(source.includes('className="hidden overflow-x-auto md:block"'));
  assert.ok(source.includes('className="space-y-2 p-3 md:hidden"'));
});

test("all required product metrics are presentation-sort choices", () => {
  for (const metric of ["overallRipScore", "financialRipScore", "collectorAppealScore", "marketPrice", "expectedValue", "chanceToRecoverCost"]) {
    assert.ok(source.includes(metric), metric);
  }
  assert.ok(source.includes("Number(a.familyRank) - Number(b.familyRank)"));
});

test("product navigation uses the set RIP route and preserves sealed product context", () => {
  assert.ok(source.includes("buildTcgSetHrefFromTarget"));
  assert.ok(source.includes("sealedProduct="));
});

test("a locked Overall tab exists and shows only Coming Soon, with no ranking data or budget controls", () => {
  assert.ok(source.includes('setView("overall-locked")'), "Overall remains a distinct product subview");
  assert.ok(source.includes('>Overall</button>'), "the product subnav is labeled Overall");
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

test("Products opens locked Overall first and exposes Overall before populated families", () => {
  assert.ok(source.includes('setView(next === "products" ? "overall-locked" : "sets")'));
  assert.ok(source.includes('const productsActive = view !== "sets"'));
  const nav = source.slice(source.indexOf('<nav aria-label="Product family"'), source.indexOf('</nav>'));
  assert.ok(nav.indexOf('>Overall</button>') < nav.indexOf('familyEntries.map'));
  assert.ok(source.includes("pluralFamilyLabel(block.label)"));
});

test("premium Product table uses shared score/tier UI, DarkSelect, search, and corrected columns", () => {
  for (const heading of ["Rank", "Product / Set"]) assert.ok(source.includes(`<th>${heading}</th>`), heading);
  for (const heading of ["Overall RIP", "Tier", "Financial RIP", "Collector Appeal", "Market Price", "Expected Value", "Chance to Recover Cost", "Format Strength"]) assert.ok(source.includes(`>${heading}</HeaderWithInfo>`), heading);
  assert.equal(source.includes("Model Break-Even"), false);
  assert.equal(source.includes("Typical Opening"), false);
  assert.ok(source.includes("<RipScoreBadge score={p.overallRipScore} tier={p.familyTier}"));
  assert.ok(source.includes("<RipTierMark tier={p.familyTier}"));
  assert.ok(source.includes("<DarkSelect ariaLabel=\"Sort products\""));
  assert.equal(source.includes("<select"), false);
  assert.ok(source.includes("styles.setMarketControl"));
  assert.ok(source.includes("product?.productName, product?.setName"));
});

test("product metric headers provide inline definitions and the desktop controls use three aligned tracks", () => {
  assert.ok(source.includes("function HeaderWithInfo"));
  assert.equal((source.match(/<HeaderWithInfo text=/g) || []).length, 8);
  assert.ok(source.includes("md:grid-cols-[minmax(0,1fr)_minmax(14rem,17rem)_minmax(14rem,17rem)]"));
  assert.ok(source.includes("px-2.5 text-xs"));
});
