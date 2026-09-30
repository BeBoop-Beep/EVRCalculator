import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { MARKET_EXPLORER_SCREENS, screenResultLabel } from "../../lib/explore/marketExplorerScreens.mjs";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("every discovery Screen requests one global top-ten authority", async () => {
  const source = await read("./MarketExplorerScreens.jsx");
  assert.ok(MARKET_EXPLORER_SCREENS.every((screen) => screen.limit === 10));
  assert.match(source, /new URLSearchParams\(\{ kind: "screen", screen: screen\.id, limit:/);
  assert.doesNotMatch(source, /asset \}/);
  assert.match(source, /results\.slice\(0, 10\)/);
});

test("mixed Screen rows use backend asset identity and an inline action region", async () => {
  assert.equal(screenResultLabel({ label: "New Releases", asset: "cards" }), "New Releases — Cards");
  assert.equal(screenResultLabel({ label: "Multi-Product Bundle", asset: "sealed" }), "Multi-Product Bundle — Sealed");
  assert.equal(screenResultLabel({ label: "PSA 10 Market", asset: "graded" }), "PSA 10 Market — Graded");
  const source = await read("./MarketExplorerScreens.jsx");
  assert.match(source, /flex-none whitespace-nowrap/);
});

test("Sealed Types is a compact searchable DB-driven disclosure", async () => {
  const source = await read("./MarketExplorerSealedTypes.jsx");
  const shared = await read("./MarketExplorerAssetMarketSelector.jsx");
  assert.match(shared, /data-sealed-types-trigger/);
  assert.match(shared, /aria-expanded=\{open\}/);
  assert.match(source, /normalizeSealedTypeOptions\(options\)/);
  assert.match(shared, /data-sealed-type-search/);
  assert.match(shared, /aria-disabled=\{option\.unavailable \|\| option\.pending\}/);
  for (const forbidden of ["booster_box", "elite_trainer_box", "pokemon_center_elite_trainer_box"]) {
    assert.doesNotMatch(source, new RegExp(forbidden));
  }
});

test("Methodology is an in-place reversible takeover and not a standing page block", async () => {
  const source = await read("./MarketExplorerClient.jsx");
  assert.match(source, /data-market-explorer-methodology-trigger/);
  assert.match(source, /aria-expanded=\{methodologyOpen\}/);
  assert.match(source, /data-market-explorer-methodology-takeover/);
  assert.match(source, /data-market-explorer-close-methodology/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /methodologyCloseRef\.current\?\.focus/);
  assert.match(source, /methodologyRestoreFocusRef/);
  assert.match(source, /data-market-explorer-compare-results[\s\S]*aria-hidden=\{methodologyOpen \? "true" : undefined\}/);
  assert.match(source, /data-market-explorer-compare-results[\s\S]*inert=\{methodologyOpen \? true : undefined\}/);
  assert.equal(source.match(/<MarketExplorerMethodology/g)?.length, 1);
});

test("V2 Browse layers use exact backend asset identity", async () => {
  const source = await read("./MarketExplorerBrowse.jsx");
  assert.match(source, /if \(v2Mode\) return row\?\.asset === assetLayer/);
  assert.match(source, /\[directory, assetLayer, v2Mode\]/);
});

test("paged mobile constituents render their own selected-window ChangeCell", async () => {
  const source = await read("./MarketExplorerConstituents.jsx");
  const pagedMobile = source.slice(source.indexOf("data-market-constituents-cards"), source.indexOf("data-market-constituents-movement-unavailable"));
  assert.match(pagedMobile, /<ChangeCell[\s\S]*row=\{row\}[\s\S]*window=\{movementWindow\}/);
});
