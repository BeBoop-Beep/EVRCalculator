import assert from "node:assert/strict";
import test from "node:test";
import { buildSealedProductHref } from "./sealedProductRoutes.mjs";

test("buildSealedProductHref is canonical, encoded, and object-aware", () => {
  assert.equal(buildSealedProductHref("sku/id"), "/sealed-products/sku%2Fid");
  assert.equal(buildSealedProductHref({ sealedProductId: "p 1" }), "/sealed-products/p%201");
  assert.equal(buildSealedProductHref({ productPageId: "p2" }), "/sealed-products/p2");
});

test("buildSealedProductHref fails safely without an id", () => {
  assert.equal(buildSealedProductHref(), null);
  assert.equal(buildSealedProductHref("  "), null);
  assert.equal(buildSealedProductHref({ name: "No identity" }), null);
});
