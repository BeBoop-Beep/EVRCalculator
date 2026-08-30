import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createMarketModuleState, marketSeedMatchesSet, readLatestSetValue, selectMarketAsOfDate } from "./marketRuntimeState.mjs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("Market tab owns endpoint clients while the shell stays dependency-light", () => {
  const shell = read("../runtime/PokemonSetRuntimeShell.jsx");
  const market = read("./MarketSetTab.jsx");
  assert.doesNotMatch(shell, /pokemonSetMarketClient|recharts|SetMarketMobile|MarketMobileChart/);
  for (const endpoint of ["getPokemonSetOverview", "getPokemonSetMarketMovers", "getPokemonSetTopChase", "getPokemonSetValueHistory", "getPokemonSetConsumerSealedMarket"]) {
    assert.match(market, new RegExp(endpoint));
  }
  assert.match(shell, /dynamic\(\(\) => import\(["']\.\.\/tabs\/MarketSetTab["']\)/);
});

test("valid server seeds hydrate successful state without losing identity", () => {
  const seed = { set: { id: "sv8", slug: "surging-sparks" }, latestMarketDate: "2026-08-29" };
  assert.equal(marketSeedMatchesSet(seed, "sv8"), true);
  assert.equal(marketSeedMatchesSet(seed, "other"), false);
  assert.deepEqual(createMarketModuleState("sv8", seed), { status: "success", setId: "sv8", payload: seed, error: null });
});

test("market selectors preserve published values and as-of metadata", () => {
  assert.equal(readLatestSetValue([{ setValue: 10 }, { set_value: 12.5 }]), 12.5);
  assert.equal(selectMarketAsOfDate({ latestMarketDate: "2026-08-27" }, { meta: { snapshot: { marketAsOfDate: "2026-08-29" } } }), "2026-08-29");
});

test("Top Chase and sealed histories remain progressive", () => {
  const market = read("./MarketSetTab.jsx");
  assert.match(market, /topChaseCards/);
  assert.match(market, /window\.setTimeout/);
  assert.match(market, /const warmSealedMarket = useCallback/);
  assert.match(market, /navigator\.connection\?\.saveData === true/);
});

test("set-switch guards reject stale async responses", () => {
  const market = read("./MarketSetTab.jsx");
  assert.match(market, /activeSetRef\.current !== setId/);
  assert.match(market, /overview\.setId === setId/);
  assert.match(market, /movers\.setId === setId/);
  assert.match(market, /topChase\.setId === setId/);
});
