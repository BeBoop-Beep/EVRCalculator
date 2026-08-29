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

test("desktop and mobile Set Market use the exact published sealed product id", () => {
  const desktop = read("../../components/explore/RipStatisticsPageClient.jsx");
  const mobile = read("../../components/pokemon/set-page/Market/SetMarketMobileTopChase.jsx");
  assert.match(desktop, /buildSealedProductHref\(selectedCard\.sealedProductId\)/);
  assert.match(mobile, /buildSealedProductHref\(row\.sealedProductId\)/);
  assert.match(mobile, /buildSealedProductHref\(model\.featured\?\.sealedProductId\)/);
  assert.doesNotMatch(desktop, /buildSealedProductHref\(selectedCard\.name\)/);
  assert.doesNotMatch(mobile, /buildSealedProductHref\(row\.name\)/);
});

test("canonical page and loaders use only real backend data", () => {
  const page = read("../../app/sealed-products/[productId]/page.js");
  const server = read("./sealedProductDetailServer.js");
  assert.match(page, /getSealedProductDetailServer/);
  assert.doesNotMatch(page, /marketDataLoader|MarketModule/);
  assert.match(server, /revalidate: DETAIL_REVALIDATE_SECONDS/);
  assert.match(server, /pokemon-sealed-product-detail:\$\{id\}/);
  assert.doesNotMatch(server, /cache: "no-store"/);
});
