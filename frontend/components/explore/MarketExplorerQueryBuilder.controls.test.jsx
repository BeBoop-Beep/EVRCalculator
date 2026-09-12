import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketExplorerQueryBuilder from "./MarketExplorerQueryBuilder.jsx";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const OPTIONS = { eras: [{ id: "sv", label: "Scarlet & Violet", sortOrder: 1 }], sets: [{ id: "sv1", label: "Temporal Forces", eraId: "sv", assets: ["cards", "sealed"] }], cardRarities: { rarities: [{ key: "sir", label: "Special Illustration Rare" }, { key: "legend", label: "LEGEND" }] }, cardSegments: { segments: [{ key: "sir", label: "Special Illustration Rare" }] }, compatibility: { cardRaritySetIds: { sir: ["sv1"], legend: ["sv1"] } }, sealedProductFamilies: { segments: [{ key: "bundle", label: "Booster Bundles" }] } };
const RAW = { key: "raw", available: true };
function mount(props = {}) { let renderer; act(() => { renderer = TestRenderer.create(<MarketExplorerQueryBuilder optionsProvided options={OPTIONS} optionsStatus="ready" currentPlan="premium" preparedSeries={[RAW]} activeSeries={[]} benchmarkEntries={[]} onAddPrepared={() => "added"} onAddQuery={async () => "added"} {...props} />); }); return renderer; }
const byData = (renderer, key) => renderer.root.find((node) => node.props?.[key] !== undefined);
const openDisclosure = (renderer, id) => act(() => renderer.root.findByProps({ "data-explorer-disclosure-toggle": id }).props.onClick());
const textOf = (node) => typeof node === "string" || typeof node === "number" ? String(node) : (node?.children || []).map(textOf).join(" ");
test("editing the builder does not commit", () => {
  let preparedCalls = 0; let queryCalls = 0;
  const renderer = mount({ onAddPrepared: () => { preparedCalls += 1; }, onAddQuery: async () => { queryCalls += 1; } });
  openDisclosure(renderer, "sealedBuilder");
  assert.equal(preparedCalls + queryCalls, 0);
  assert.equal(renderer.root.findByProps({ "data-market-explorer-filters": true }).props["data-market-builder-asset"], "sealed");
});

test("Build Market uses the query contract for the global card authority and retains the draft", async () => {
  const calls = []; const renderer = mount({ onAddQuery: async (spec) => { calls.push(spec.asset); return "added"; } });
  await act(async () => byData(renderer, "data-market-builder-build").props.onClick());
  assert.deepEqual(calls, ["cards"]);
  assert.equal(renderer.root.findByProps({ "data-market-explorer-filters": true }).props["data-market-builder-asset"], "cards");
});

test("a legacy active card parent does not suppress the distinct global query authority", () => {
  const renderer = mount({ activeSeries: [RAW] }); const button = byData(renderer, "data-market-builder-build");
  assert.equal(button.props.disabled, false); assert.equal(button.props.children, "Build Market");
});

test("Clear resets the canonical draft", () => {
  const renderer = mount(); openDisclosure(renderer, "sealedBuilder"); act(() => byData(renderer, "data-market-builder-clear").props.onClick());
  assert.equal(renderer.root.findByProps({ "data-market-explorer-filters": true }).props["data-market-builder-asset"], "cards");
});

test("mobile disclosure exposes the same builder", () => {
  const renderer = mount(); const toggle = byData(renderer, "data-market-builder-mobile-toggle"); assert.equal(toggle.props["aria-expanded"], false); act(() => toggle.props.onClick()); assert.equal(byData(renderer, "data-market-builder-mobile-toggle").props["aria-expanded"], true);
});

// Screens are prepared discovery. Quick Presets own every Builder mutation.

test("Raw Cards starts active and open; asset headers switch and close in one click", () => {
  const renderer = mount();
  assert.equal(renderer.root.findByProps({ "data-explorer-disclosure": "rawCardsBuilder" }).props["data-explorer-disclosure-open"], "true");
  assert.equal(renderer.root.findByProps({ "data-explorer-disclosure": "sealedBuilder" }).props["data-explorer-disclosure-open"], "false");
  openDisclosure(renderer, "sealedBuilder");
  assert.equal(renderer.root.findByProps({ "data-market-explorer-filters": true }).props["data-market-builder-asset"], "sealed");
  assert.equal(renderer.root.findByProps({ "data-explorer-disclosure": "rawCardsBuilder" }).props["data-explorer-disclosure-open"], "false");
  assert.equal(renderer.root.findByProps({ "data-explorer-disclosure": "sealedBuilder" }).props["data-explorer-disclosure-open"], "true");
  openDisclosure(renderer, "rawCardsBuilder");
  assert.equal(renderer.root.findByProps({ "data-market-explorer-filters": true }).props["data-market-builder-asset"], "cards");
});

test("loading options is intentional inside the initially-open Raw Cards section", () => {
  const renderer = mount({ options: null, optionsStatus: "loading" });
  assert.match(textOf(renderer.root.findByProps({ role: "status" })), /Loading canonical filters/);
});

test("toggling a benchmark never touches the Builder draft", () => {
  let toggled = null;
  const benchmark = { key: "topChase", label: "Per-Set Chase Market", selected: false };
  const renderer = mount({ benchmarkEntries: [benchmark], onToggleBenchmark: (key) => { toggled = key; } });
  const draftAssetBefore = renderer.root.findByProps({ "data-market-explorer-filters": true }).props["data-market-builder-asset"];

  openDisclosure(renderer, "cardsReference");
  const benchmarkOption = renderer.root.find(
    (node) => node.props?.entry?.key === "topChase"
  );
  act(() => benchmarkOption.props.onToggle(benchmark.key));

  assert.equal(toggled, "topChase");
  // The draft (asset=sealed, from the earlier click) must be completely
  // unaffected by a benchmark toggle -- onToggleBenchmark is wired straight
  // to the parent's prepared-selection reducer, never into this component's
  // own useMarketExplorerBuilderDraft state.
  assert.equal(
    renderer.root.findByProps({ "data-market-explorer-filters": true }).props["data-market-builder-asset"],
    draftAssetBefore,
  );
});

test("Cards Rarity uses the full locally searchable filter taxonomy", () => {
  const renderer = mount({ currentPlan: "premium" });
  openDisclosure(renderer, "cardsSegments");
  const rarity = renderer.root.find((node) => node.props?.name === "cards-segment");
  assert.equal(rarity.props.searchable, true);
  assert.deepEqual(rarity.props.options.map((row) => row.id), ["sir", "legend"]);
  assert.equal(rarity.props.searchPlaceholder, "Search raritiesâ€¦");
});

test("a truthful empty preflight disables Build without executing the expensive query", async () => {
  let builds = 0;
  const renderer = mount({
    preflightResult: { state: "empty", message: "No cards currently match these filters." },
    onAddQuery: async () => { builds += 1; return "added"; },
  });
  const button = renderer.root.findByProps({ "data-market-builder-build": true });
  assert.equal(button.props.disabled, true);
  await act(async () => button.props.onClick());
  assert.equal(builds, 0);
  assert.match(textOf(renderer.root.findByProps({ "data-market-builder-preflight": "empty" })), /No cards currently match/);
});

test("projection lag is unavailable and never presented as zero matches", () => {
  const renderer = mount({ preflightResult: { state: "unavailable", message: "Matching-card availability is temporarily unavailable. This is not a zero-match result." } });
  const text = textOf(renderer.root.findByProps({ "data-market-builder-preflight": "unavailable" }));
  assert.match(text, /temporarily unavailable/);
  assert.doesNotMatch(text, /0 matching|No cards currently match/);
});
