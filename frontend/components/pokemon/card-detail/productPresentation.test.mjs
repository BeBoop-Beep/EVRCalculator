import assert from "node:assert/strict";
import test from "node:test";
import {
  buildSealedProductHref,
  expectedProductsCopy,
  orderCardProducts,
  productDisplayPrice,
} from "./productPresentation.mjs";

test("supported products lead in authoritative input order and catalog IDs deduplicate", () => {
  const products = orderCardProducts([
    {
      sealedProductId: "u",
      productName: "Three-Pack Blister",
      available: false,
    },
    {
      sealedProductId: "b",
      productName: "Bundle",
      productFamily: "booster_bundle",
      available: true,
    },
    {
      sealedProductId: "p",
      productName: "Pack",
      productFamily: "loose_booster_pack",
      available: true,
    },
    { sealedProductId: "u", productName: "Duplicate", available: false },
  ]);
  assert.deepEqual(
    products.map((product) => product.sealedProductId),
    ["b", "p", "u"],
  );
  assert.equal(products[2].productName, "Three-Pack Blister");
});

test("display price prefers supported model price, falls back to catalog price, and rejects zero", () => {
  assert.equal(productDisplayPrice({ productPrice: 12.5, currentPrice: 34.99 }), 12.5);
  assert.equal(productDisplayPrice({ available: false, currentPrice: 34.99 }), 34.99);
  assert.equal(productDisplayPrice({ currentPrice: 0 }), null);
  assert.equal(productDisplayPrice({}), null);
});

test("expected-product labels use canonical plurals and always explain TO PULL", () => {
  assert.equal(
    expectedProductsCopy({ productFamily: "elite_trainer_box" }).label,
    "Expected ETBs to Pull",
  );
  assert.equal(
    expectedProductsCopy({ productFamily: "other" }).label,
    "Expected Products to Pull",
  );
  assert.match(
    expectedProductsCopy({ productFamily: "booster_bundle" }).tooltip,
    /average, not a guarantee/i,
  );
});

test("product navigation uses only the canonical product page ID", () => {
  assert.equal(
    buildSealedProductHref({
      productPageId: "sku/id",
      productName: "Do Not Slugify Me",
    }),
    "/sealed-products/sku%2Fid",
  );
  assert.equal(buildSealedProductHref({ productName: "No ID" }), null);
});
