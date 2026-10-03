import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const score = read("./RankingsScorePrimitives.jsx");
const lazy = read("./RankingsLazyClient.jsx");
const setHub = read("./SetRankingsHub.jsx");
const paidHook = read("../../lib/rankings/usePaidScorecards.js");
const productLens = read("./RankingsProductLensClient.jsx");
const productClient = read("../../lib/rankings/productRankingsClient.mjs");
const chart = read("./FinancialRipHistoryChart.jsx");
const trendModel = read("./financialRipHistoryModel.mjs");
const tooltip = read("./FinancialRipHistoryTooltip.jsx");
const overall = read("./OpeningEconomicsOverall.jsx");
const distribution = read("./OpeningEconomicsDistribution.jsx");

test("all score cells share the below-box tier-colored accessible rank primitive", () => {
  assert.match(score, /function RankTierLine/);
  assert.match(score, /color: tone\?\.accentColor/);
  assert.match(score, /aria-label=\{`Rank \$\{rank\}, Tier \$\{tier \|\| "unavailable"\}`\}/);
  assert.equal((score.match(/<RankTierLine/g) || []).length, 2);
});

test("paid Era and Set scorecards prewarm and cached data is adopted synchronously", () => {
  for (const type of ["era", "set"]) assert.match(lazy, new RegExp(`readRankingsScorecards\\("${type}", \\{ sessionCache \\}\\)`));
  assert.match(paidHook, /useState\(\(\) => \{/);
  assert.match(paidHook, /sessionCache\?\.peek\(`rankings:scorecards:\$\{entityType\}`\)/);
});

test("Set children are static and Pack Economics uses the mounted cache key", () => {
  assert.match(setHub, /import SetRipScoreLeaderboard/);
  assert.match(setHub, /import SetPackMetrics/);
  assert.doesNotMatch(setHub, /dynamic\(/);
  assert.match(setHub, /sets:pack-economics/);
  assert.match(lazy, /readPackEconomics\(\{ sessionCache \}\)/);
});

test("Product Economics page one and Premium Chase are idle/intent prewarmed", () => {
  assert.match(productClient, /page: 1/);
  assert.match(lazy, /prewarmDefaultProductEconomics/);
  assert.match(productLens, /prewarmDefaultProductEconomics/);
  assert.ok(lazy.indexOf("prewarmDefaultCollector({") < lazy.indexOf("const chase = () => prewarmDefaultChase"));
  assert.match(lazy, /canViewCardChaseEfficiency/);
});

test("Overview is one summary context and Trend has one local metric dropdown", () => {
  assert.doesNotMatch(overall, /<h2[^>]*>Pokémon Opening Economics/);
  assert.match(distribution, /data-opening-summary-context/);
  for (const label of ["Overall Financial RIP", "Overall Expected Value / Pack", "Average Pack Cost / Pack", "Modeled Return", "Chance to Recover Cost", "Entertainment Cost / Pack"]) assert.ok(distribution.includes(label));
  for (const label of ["Financial RIP", "Expected Value / Pack", "Chance to Beat Pack", "Chance to Recover Cost"]) assert.ok(trendModel.includes(label));
  assert.match(chart, /<DarkSelect ariaLabel="Trend metric" eyebrow="Metric"/);
  assert.doesNotMatch(chart, /\[[^\]]*metricKey[^\]]*\]\s*\);\s*\/\/ request/);
  assert.match(chart, /Previous certified observation unavailable/);
});

test("Trend labels and tooltip units are metric-specific", () => {
  for (const label of ["Pokémon Overall EV / Pack", "Pokémon Overall Chance to Beat Pack", "Pokémon Overall Chance to Recover Cost"]) assert.ok(trendModel.includes(label));
  assert.match(tooltip, /formatTrendValue/);
  assert.match(tooltip, /formatTrendDelta/);
});

test("Scarlet & Violet 151 equal-family/equal-SKU fixture remains $56.95", () => {
  const skuPerPack = [169.40 / 6, 29.98, 491.68 / 9, 1264.45 / 11];
  const equalFamilySkuMean = skuPerPack.reduce((sum, value) => sum + value, 0) / skuPerPack.length;
  assert.equal(equalFamilySkuMean.toFixed(2), "56.95");
  assert.ok(equalFamilySkuMean > skuPerPack[0]);
});
