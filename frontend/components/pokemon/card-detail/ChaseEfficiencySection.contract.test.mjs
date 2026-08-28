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
});

test("Premium inherits centralized Plus access", () => {
  assert.match(source, /hasIndexPlusAccess\(user\?\.index_plan\)/);
  assert.match(source, /hasIndexFeatureAccess\([\s\S]*?user\?\.index_plan,[\s\S]*?FEATURE_CARD_CHASE_EFFICIENCY/);
});
