import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.join(process.cwd(), "components/pokemon/card-detail/PokemonCardDetailClient.jsx"), "utf8");
const market = fs.readFileSync(path.join(process.cwd(), "components/pokemon/card-detail/AssetMarketPanel.jsx"), "utf8");
const marketModel = fs.readFileSync(path.join(process.cwd(), "components/pokemon/card-detail/assetMarketModel.mjs"), "utf8");
const page = fs.readFileSync(path.join(process.cwd(), "app/TCGs/Pokemon/Sets/[setSlug]/Cards/[cardId]/page.js"), "utf8");
const styles = fs.readFileSync(path.join(process.cwd(), "app/styles/globals.css"), "utf8");

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

test("probability journey renders its canonical curve and all milestone markers", () => {
  assert.match(source, /chase\.modeledProbability/);
  assert.match(source, /1 - Math\.pow\(1 - probability, packs\)/);
  assert.match(source, /data-probability-journey-chart/);
  assert.match(source, /data-probability-curve/);
  assert.match(source, /data-probability-marker=/);
  for (const label of ["50%", "75%", "90%", "95%"] ) assert.ok(source.includes(label));
});

test("card detail shares the dynamic set atmosphere and establishes its stacking context", () => {
  assert.match(source, /optimizedImageUrl\(detail\.set\.heroImageUrl \|\| detail\.set\.logoImageUrl \|\| detail\.set\.symbolImageUrl, SET_LOGO_WIDTH\)/);
  assert.match(source, /PageArtworkAtmosphere src=\{artwork\}/);
  assert.match(source, /relative isolate/);
  assert.doesNotMatch(source, /Ascended Heroes.*artwork|Black Bolt.*artwork/);
});

test("normal card-detail interactions use Market teal while the lock remains amber", () => {
  assert.match(styles, /\.card-detail-environment[\s\S]*--accent: rgb\(45, 212, 191\)/);
  assert.match(source, /text-amber-300/);
  assert.match(source, /border-amber-300\/40/);
});

test("product choices use canonical compact labels and a responsive four-column desktop grid", () => {
  assert.match(source, /compactSealedProductLabel\(p\)/);
  assert.match(source, /sm:grid-cols-2 lg:grid-cols-4/);
  assert.match(source, /selected\.sealedProductId === p\.sealedProductId/);
});

test("collector hierarchy keeps actual scores and honest unavailable scarcity", () => {
  assert.match(source, /primary=\{?true\}?|primary\/>/);
  assert.match(source, /intelligence\?\.cardAppeal/);
  assert.match(source, /intelligence\?\.pokemonDemand/);
  assert.match(source, /intelligence\?\.treatment/);
  assert.match(source, /intelligence\?\.scarcity/);
  assert.match(source, /"Unavailable"/);
  assert.doesNotMatch(source, /0 \/ 10/);
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
