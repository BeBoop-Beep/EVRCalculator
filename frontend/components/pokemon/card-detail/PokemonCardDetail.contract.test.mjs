import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.join(process.cwd(), "components/pokemon/card-detail/PokemonCardDetailClient.jsx"), "utf8");
const market = fs.readFileSync(path.join(process.cwd(), "components/pokemon/card-detail/AssetMarketPanel.jsx"), "utf8");
const marketModel = fs.readFileSync(path.join(process.cwd(), "components/pokemon/card-detail/assetMarketModel.mjs"), "utf8");
const page = fs.readFileSync(path.join(process.cwd(), "app/TCGs/Pokemon/Sets/[setSlug]/Cards/[cardId]/page.js"), "utf8");

test("variant selection preserves canonical route and accessible radio state", () => {
  assert.match(source, /getPokemonCardDetail\(detail\.set\.id, detail\.card\.id, variantId\)/);
  assert.match(source, /\?variant=\$\{encodeURIComponent\(variantId\)\}/);
  assert.match(source, /role="radiogroup"/);
  assert.match(source, /aria-checked=/);
});

test("unsupported cards retain public market identity without fake intelligence", () => {
  assert.match(source, /Modeled Card Intelligence is not currently available for this card/);
  assert.match(source, /Card artwork unavailable/);
  assert.match(source, /hasIndexPlusAccess\(user\?\.index_plan\)/);
  assert.doesNotMatch(source, /plan\s*===\s*["']plus["']/);
});

test("identity is rarity plus number and excludes subtype metadata", () => {
  assert.match(source, /detail\.card\.rarity, detail\.card\.printedNumber \|\| detail\.card\.cardNumber/);
  assert.doesNotMatch(source, /subtypes\?\.join|detail\.card\.subtypes/);
});

test("market shell exposes raw, disabled graded, canonical windows, chart and truthful fallback", () => {
  for (const label of ["Raw", "Graded · Coming Soon", "Showing history since tracking began"]) assert.ok(market.includes(label), `missing ${label}`);
  for (const label of ["1D", "7D", "30D", "3M", "6M", "1Y", "ALL"]) assert.ok(marketModel.includes(label), `missing ${label}`);
  assert.match(market, /disabled title="Graded market data is coming soon"/);
  assert.match(market, /MarketMobileChart/);
  assert.doesNotMatch(market, /PSA|BGS|CGC/);
});

test("journey and product economics use canonical fields with recovery disclosure", () => {
  for (const label of ["50%", "75%", "90%", "95%", "Choose How You Open It", "Gross Chase Spend", "Recovery-adjusted Cost"]) assert.ok(source.includes(label), `missing ${label}`);
  assert.match(source, /fees, shipping, condition discounts, liquidity, or sell-through/);
  assert.doesNotMatch(source, /Overall RIP|Financial RIP|Collector Appeal|RIP Tier/);
});

test("product economics read the canonical productPrice contract field", () => {
  assert.match(source, /selected\.productPrice/);
  assert.doesNotMatch(source, /selected\.productMarketCost/);
});

test("canonical metadata excludes variant query", () => {
  assert.match(page, /const path = `\/TCGs\/Pokemon\/Sets\/\$\{encodeURIComponent\(detail\.set\.slug\)\}\/Cards\/\$\{encodeURIComponent\(detail\.card\.id\)\}`/);
  assert.doesNotMatch(page, /path.*variant/);
  assert.match(page, /notFound\(\)/);
});
