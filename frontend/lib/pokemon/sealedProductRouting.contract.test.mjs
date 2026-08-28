import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("product surfaces delegate to the canonical helper", () => {
  const setRip = read("../../components/explore/setProductComparison.mjs");
  const card = read("../../components/pokemon/card-detail/productPresentation.mjs");
  const rankings = read("../../components/explore/ProductFamilyRankingsClient.jsx");
  assert.match(setRip, /sealedProductRoutes/);
  assert.match(card, /sealedProductRoutes/);
  assert.match(rankings, /buildSealedProductHref/);
  assert.doesNotMatch(rankings, /\?sealedProduct=/);
});

test("set market exposes intentional drilldown and legacy redirect remains", () => {
  const market = read("../../components/pokemon/set-page/Overview/SealedMarketTrendCard.jsx");
  const legacy = read("../../app/products/details/page.js");
  assert.match(market, /View Product/);
  assert.match(market, /buildSealedProductHref\(product\)/);
  assert.match(legacy, /redirect\(href\)/);
});

test("canonical page and loaders use only real backend data", () => {
  const page = read("../../app/sealed-products/[productId]/page.js");
  const server = read("./sealedProductDetailServer.js");
  assert.match(page, /getSealedProductDetailServer/);
  assert.doesNotMatch(page, /marketDataLoader|MarketModule/);
  assert.match(server, /cache: "no-store"/);
});
