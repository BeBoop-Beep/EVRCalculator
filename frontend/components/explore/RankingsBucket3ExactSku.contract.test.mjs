import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const pack = read("./SetPackMetrics.jsx");
const service = fs.readFileSync(new URL("../../../backend/db/services/rankings_redesign_contract_service.py", import.meta.url), "utf8");
const publicAccess = read("./RankingsBucket1PublicAccess.contract.test.mjs");
const b2 = read("./RankingsBucket2Presentation.contract.test.mjs");

test("paid Set expansion is Set to exact Products with no visible family layer", () => {
  assert.match(pack, /\(row\.products \|\| \[\]\)\.map\(\(product/);
  assert.match(pack, /data-pack-product-row=\{product\.sealedProductId\}/);
  assert.match(pack, /data-pack-product-mobile=\{product\.sealedProductId\}/);
  assert.doesNotMatch(pack, /data-pack-family-row|data-pack-family-mobile|<FamilyRow|└/);
});

test("exact Product rows align authoritative economics and route by sealedProductId", () => {
  assert.match(pack, /buildSealedProductHref\(product\)/);
  assert.match(pack, /ECONOMIC_KEYS\.map\(\(key\).*product\[key\]/s);
  assert.match(pack, /product\.bestOpenPrice/);
  assert.match(pack, /<BestOpenDetailsPopover row=\{product\}/);
  assert.match(pack, /product\.packCount/);
});

test("backend joins exact evidence only by canonical IDs and batches every authority", () => {
  assert.ok(service.includes('exact_economics = {(str(row["sealed_product_id"]), str(row["calculation_run_id"])): row'));
  assert.match(service, /\.in_\("sealed_product_id", product_ids\)\.in_\("calculation_run_id", source_run_ids\)/);
  assert.match(service, /products_by_set\.setdefault\(str\(row\["set_id"\]\), \[\]\)\.append\(item\)/);
  assert.doesNotMatch(service, /productName.*==|familyName.*==/);
});

test("B1 and B2 regression contracts remain in the focused suite", () => {
  assert.match(publicAccess, /anonymous Era and Set headlines/);
  assert.match(publicAccess, /Set Pack Economics preview exposes cost and locks protected/);
  assert.match(b2, /benchmark \/10 badge hides its redundant caption/);
  assert.match(b2, /Product calibration remains pending/);
});
