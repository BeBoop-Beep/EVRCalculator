import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./PokemonCardDetailClient.jsx", import.meta.url), "utf8");
const tokens = fs.readFileSync(new URL("./cardDetailVisualTokens.mjs", import.meta.url), "utf8");

test("Premium chase precedes standalone Plus products and Collector Intelligence", () => {
  const premium = source.lastIndexOf("<ChaseEfficiencySection");
  const products = source.lastIndexOf("<OpeningProductsSection");
  const collector = source.lastIndexOf("<CollectorIntelligence");
  assert.ok(premium > -1 && premium < products && products < collector);
  assert.doesNotMatch(source, /CardIntelligence|Card Intelligence/);
  assert.match(source, /PlusLock title="Choose How You Open It"/);
});

test("Premium composition is Pull Profile, rank, economics, then one journey", () => {
  const start = source.indexOf("function ChaseEfficiencySection");
  const end = source.indexOf("function CollectorIntelligence", start);
  const section = source.slice(start, end);
  assert.ok(section.lastIndexOf("<PullProfile") < section.indexOf("Rank Context"));
  assert.ok(section.indexOf("Rank Context") < section.indexOf("Economics"));
  assert.ok(section.indexOf("Economics") < section.lastIndexOf("<ProbabilityJourney"));
  assert.doesNotMatch(section, /50% Chase Spend|How rare is this exact printing|Product Chase Economics/);
  assert.match(section, /milestoneDollars=\{dollars\}/);
  assert.match(section, /getRipTierPresentation\(row\.tier, \{ strength: "hero" \}\)/);
  assert.doesNotMatch(section, /topPercentToTier/);
  assert.match(section, /data-rank-context-rail/);
  assert.match(section, /data-chase-economics-matrix/);
  assert.match(source, /h-\[230px\].*sm:h-\[300px\]/s);
});

test("detail and ranking probabilities are validated", () => {
  assert.match(source, /Math\.abs\(rowProbability - detailProbability\) > tolerance/);
  assert.match(source, /exact-printing probabilities disagree/);
  assert.match(source, /modeledProbability: rowProbability/);
});

test("Probability Lavender is centralized and replaces teal series identity", () => {
  assert.match(tokens, /PROBABILITY_ANALYTICS_COLOR = "hsl\(278 72% 70%\)"/);
  const journey = source.slice(source.indexOf("function ProbabilityJourney"), source.indexOf("function ProductEconomics"));
  assert.match(journey, /PROBABILITY_ANALYTICS_COLOR/);
  assert.doesNotMatch(journey, /rgb\(45,212,191\)|rgba\(45,212,191/);
  assert.doesNotMatch(journey, /milestoneDollars[\s\S]*?style=\{\{ color: PROBABILITY_ANALYTICS_COLOR/);
});

test("selected product separates identity from one analytical price", () => {
  const product = source.slice(source.indexOf("function ProductEconomics"), source.indexOf("function PullProfile"));
  assert.match(product, /data-product-analytics-matrix/);
  assert.equal((product.match(/label="Product Price"/g) || []).length, 2, "supported and unsupported branches each retain one analytical price");
  assert.doesNotMatch(product.slice(product.indexOf("Selected format"), product.indexOf("!selected.available")), /productDisplayPrice\(selected\)/);
});

test("Card Treatment explains the dynamic V1 mapping and exclusions", () => {
  assert.match(source, /Current treatment: \$\{rarity\}/);
  for (const value of ["SIR 9.6", "IR 8.4", "Hyper Rare \/ Gold 8.2", "Common 1.8", "Other\/unmatched 3.0"]) assert.ok(source.includes(value));
  for (const excluded of ["market price", "pull odds", "Pokémon popularity", "artwork quality"]) assert.ok(source.includes(excluded));
});

test("Premium inherits centralized Plus access", () => {
  assert.match(source, /hasIndexPlusAccess\(user\?\.index_plan\)/);
  assert.match(source, /hasIndexFeatureAccess\([\s\S]*?user\?\.index_plan,[\s\S]*?FEATURE_CARD_CHASE_EFFICIENCY/);
});
