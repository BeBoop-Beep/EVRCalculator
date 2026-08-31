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

test("rich Pull Rates resource ownership is isolated without moving its presentation", () => {
  const rich = read("../../../explore/RipStatisticsPageClient.jsx");
  const richPullRates = read("../rich/RichPullRatesSetTab.jsx");
  const controller = read("../../../../hooks/pokemon/useSetPullRatesController.js");
  assert.match(rich, /dynamic\(\(\) => import\(["']@\/components\/pokemon\/set-page\/rich\/RichPullRatesSetTab["']\)\)/);
  assert.match(richPullRates, /useSetPullRatesController\(\{/);
  assert.match(richPullRates, /<PullRatesTab/);
  assert.doesNotMatch(rich, /getPokemonSetPullRates\(/);
  assert.doesNotMatch(rich, /\[pullRatesState, setPullRatesState\]/);
  assert.match(controller, /pokemonSetPullRatesClient/);
  assert.match(controller, /activeSetIdRef\.current !== setId/);
  assert.match(controller, /previous\.setId === setId && previous\.pullRateAssumptions \? "success_stale"/);
});

test("rich Cards resource ownership is isolated without moving its presentation", () => {
  const rich = read("../../../explore/RipStatisticsPageClient.jsx");
  const controller = read("../../../../hooks/pokemon/useSetCardsController.js");
  assert.match(rich, /useSetCardsController\(\{/);
  assert.doesNotMatch(rich, /getPokemonSetCardsPage\(/);
  assert.doesNotMatch(rich, /\[cardsPageState, setCardsPageState\]/);
  assert.match(controller, /activeRequestKeyRef\.current !== requestKey/);
  assert.match(controller, /activeSetIdRef\.current !== setId/);
  assert.match(controller, /buildCardsRequestKey/);
});

test("rich Market resources are isolated without moving Market presentation", () => {
  const rich = read("../../../explore/RipStatisticsPageClient.jsx");
  const controller = read("../../../../hooks/pokemon/useSetMarketController.js");
  assert.match(rich, /useSetMarketController\(\{/);
  assert.doesNotMatch(rich, /getPokemonSetOverview\(/);
  assert.doesNotMatch(rich, /getPokemonSetTopChase\(/);
  assert.doesNotMatch(rich, /getPokemonSetMarketMovers\(/);
  assert.match(controller, /activeRequestKeyRef\.current !== requestKey/);
  assert.match(controller, /activeSetIdRef\.current !== setId/);
  assert.match(controller, /topChasePreviewOnly/);
  assert.doesNotMatch(controller, /SetMarketMobile|SetMarketSignals/);
});

test("rich RIP progressive resources are isolated and retain same-run and access gates", () => {
  const rich = read("../../../explore/RipStatisticsPageClient.jsx");
  const controller = read("../../../../hooks/pokemon/useSetRipProgressiveController.js");
  assert.match(rich, /useSetRipProgressiveController\(\{/);
  assert.doesNotMatch(rich, /getPokemonSetRipRankContext\(/);
  assert.doesNotMatch(rich, /getPokemonSetRipSimulationEvidence\(/);
  assert.doesNotMatch(rich, /getPokemonSetRipAdvanced\(/);
  assert.match(controller, /activeIdentityRef\.current !== identity/);
  assert.match(controller, /selectSameRunRipSimulation/);
  assert.match(controller, /selectSameRunRipAdvanced/);
  assert.match(controller, /!canViewProductRipIntelligence/);
  assert.doesNotMatch(controller, /RipDecisionPage/);
});
