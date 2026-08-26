import assert from "node:assert/strict";
import test from "node:test";
import { buildFamilyRankLookup, groupProductsByFamily } from "./setProductComparison.mjs";

// These fixtures mirror the shape `build_product_family_rankings` (backend)
// actually publishes and `selectRipDecisionContract` actually normalizes —
// NOT invented shapes. See product_family_rankings_service.py `_project()`
// for the canonical field names.

function productFamilyRankingsFixture() {
  return {
    families: {
      elite_trainer_box: {
        family: "elite_trainer_box",
        label: "Elite Trainer Box",
        count: 22,
        products: [
          { sealedProductId: "etb-a", familyRank: 3, familySize: 22, familyTier: "A", overallRipLeaderScore: 91.24, publicTier: "A", productImageUrl: "https://example.test/etb.png", setCanonicalKey: "alphaSet" },
          { sealedProductId: "etb-b", familyRank: 11, familySize: 22, familyTier: "B" },
        ],
      },
      booster_bundle: {
        family: "booster_bundle",
        label: "Booster Bundle",
        count: 21,
        products: [{ sealedProductId: "bundle-a", familyRank: 4, familySize: 21 }],
      },
      booster_box: {
        family: "booster_box",
        label: "Booster Box",
        count: 18,
        products: [{ sealedProductId: "box-a", familyRank: 2, familySize: 18 }],
      },
    },
  };
}

function product(overrides) {
  return {
    key: overrides.sealedProductId,
    sealedProductId: overrides.sealedProductId,
    family: overrides.family,
    label: overrides.label,
    overallRipScore: overrides.overallRipScore ?? null,
    modelEdgePercent: overrides.modelEdgePercent ?? null,
    marketPrice: null,
    packCount: null,
    typicalOpening: null,
    chanceToRecoverCost: null,
    entertainmentCost: { available: false },
  };
}

test("global family cohort: a single-SKU-in-set product still reports the FULL global denominator, not 1", () => {
  const lookup = buildFamilyRankLookup(productFamilyRankingsFixture());
  const products = [product({ sealedProductId: "bundle-a", family: "booster_bundle", label: "Bundle" })];
  const [group] = groupProductsByFamily(products, lookup);
  const info = lookup.get(group.products[0].sealedProductId);
  assert.equal(info.familyRank, 4);
  assert.equal(info.familySize, 21, "denominator is the global cohort (21), never the local set count (1)");
});

test("multiple local SKUs preserve canonical display order and consume global family rank/tier", () => {
  const lookup = buildFamilyRankLookup(productFamilyRankingsFixture());
  const products = [
    product({ sealedProductId: "etb-b", family: "elite_trainer_box", label: "ETB Variant B" }),
    product({ sealedProductId: "etb-a", family: "elite_trainer_box", label: "ETB Variant A" }),
  ];
  const [group] = groupProductsByFamily(products, lookup);
  assert.deepEqual(group.products.map((p) => p.sealedProductId), ["etb-b", "etb-a"]);
  assert.equal(lookup.get("etb-a").familyRank, 3);
  assert.equal(lookup.get("etb-a").familySize, 22);
  assert.equal(lookup.get("etb-b").familyRank, 11);
  assert.equal(lookup.get("etb-b").familySize, 22);
  assert.equal(lookup.get("etb-a").familyTier, "A");
  assert.equal(lookup.get("etb-a").overallRipLeaderScore, 91.24);
  assert.equal(lookup.get("etb-a").publicTier, "A");
  assert.equal(lookup.get("etb-a").setCanonicalKey, "alphaSet");
  assert.equal(lookup.get("etb-b").familyTier, "B");
});

test("different families never share one denominator", () => {
  const lookup = buildFamilyRankLookup(productFamilyRankingsFixture());
  assert.equal(lookup.get("etb-a").familySize, 22);
  assert.equal(lookup.get("bundle-a").familySize, 21);
  assert.equal(lookup.get("box-a").familySize, 18);
  const sizes = new Set([lookup.get("etb-a").familySize, lookup.get("bundle-a").familySize, lookup.get("box-a").familySize]);
  assert.equal(sizes.size, 3, "each family cohort has its own real denominator");
});

test("a product absent from the canonical rankings block has no fabricated rank, and is not dropped from the list", () => {
  const lookup = buildFamilyRankLookup(productFamilyRankingsFixture());
  const products = [
    product({ sealedProductId: "unranked-etb", family: "elite_trainer_box", label: "New ETB", overallRipScore: 50 }),
    product({ sealedProductId: "etb-a", family: "elite_trainer_box", label: "ETB Variant A" }),
  ];
  const [group] = groupProductsByFamily(products, lookup);
  assert.equal(group.products.length, 2, "the unranked product still renders as a row");
  assert.equal(lookup.get("unranked-etb"), undefined, "no rank is invented for a product the canonical block does not carry");
  assert.deepEqual(group.products.map((p) => p.sealedProductId), ["unranked-etb", "etb-a"]);
});

test("an empty or malformed productFamilyRankings payload degrades to an empty lookup, never a thrown error", () => {
  assert.equal(buildFamilyRankLookup(null).size, 0);
  assert.equal(buildFamilyRankLookup(undefined).size, 0);
  assert.equal(buildFamilyRankLookup({}).size, 0);
  assert.equal(buildFamilyRankLookup({ families: null }).size, 0);
  assert.equal(buildFamilyRankLookup({ families: { x: { products: "not-an-array" } } }).size, 0);
});
