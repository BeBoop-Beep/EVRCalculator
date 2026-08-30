import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { buildCardsRequestKey } from "../tabs/cardsRequestKey.mjs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("Pokemon Set entrypoint preserves the established rich Set UI", () => {
  const entrypoint = read("../PokemonSetPageClient.jsx");
  assert.match(entrypoint, /dynamic\(\s*\(\) => import\(["']@\/components\/explore\/RipStatisticsPageClient["']\)/);
  assert.match(entrypoint, /<RipStatisticsPageClient \{\.\.\.props\} setDetailMode \/>/);
  assert.doesNotMatch(entrypoint, /PokemonSetRuntimeShell/);
});

test("Set runtime shell remains dependency-light and tabs own endpoint imports", () => {
  const shell = read("./PokemonSetRuntimeShell.jsx");
  const fallback = read("../../../explore/RipStatisticsPageClient.jsx");
  const cards = read("../tabs/CardsSetTab.jsx");
  const pullRates = read("../tabs/PullRatesSetTab.jsx");
  assert.doesNotMatch(shell, /from ["']recharts["']/);
  assert.doesNotMatch(shell, /from ["']@\/lib\/pokemon\/pokemonSetCardsClient["']/);
  assert.doesNotMatch(shell, /from ["']@\/lib\/pokemon\/pokemonSetPullRatesClient["']/);
  assert.match(cards, /from ["']@\/lib\/pokemon\/pokemonSetCardsClient["']/);
  assert.match(pullRates, /from ["']@\/lib\/pokemon\/pokemonSetPullRatesClient["']/);
  assert.match(shell, /dynamic\(\(\) => import\(["']\.\.\/tabs\/CardsSetTab["']\)/);
  assert.match(shell, /dynamic\(\(\) => import\(["']\.\.\/tabs\/PullRatesSetTab["']\)/);
  assert.match(shell, /dynamic\(\(\) => import\(["']\.\.\/tabs\/MarketSetTab["']\)/);
  assert.doesNotMatch(shell, /from ["']@\/lib\/pokemon\/pokemonSetMarketClient["']/);
  assert.doesNotMatch(fallback, /from ["']@\/lib\/pokemon\/pokemonSetCardsClient["']/);
  assert.doesNotMatch(fallback, /from ["']@\/lib\/pokemon\/pokemonSetPullRatesClient["']/);
});

test("Cards request identity includes every result-changing control", () => {
  const base = { setId: "sv8", pricingContractVersion: "v1", section: "all-cards", sort: "set-number", sortDirection: "asc", query: null, rarity: null, movementFilter: "all", movementSort: null, movementMetric: null, page: 1, pageSize: 60 };
  const keys = Object.keys(base);
  const baseline = buildCardsRequestKey(base);
  for (const key of keys) {
    const changed = { ...base, [key]: typeof base[key] === "number" ? base[key] + 1 : `${base[key] || "none"}-changed` };
    assert.notEqual(buildCardsRequestKey(changed), baseline, `${key} must participate in request identity`);
  }
});

test("set switches are guarded by set-scoped runtime state", () => {
  const cards = read("../tabs/CardsSetTab.jsx");
  const pullRates = read("../tabs/PullRatesSetTab.jsx");
  assert.match(cards, /state\.setId === setId/);
  assert.match(cards, /activeRequestRef\.current !== requestKey/);
  assert.match(pullRates, /state\.setId === setId/);
  assert.match(pullRates, /cancelled/);
});
