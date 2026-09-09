import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketExplorerQueryBuilder from "./MarketExplorerQueryBuilder.jsx";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const OPTIONS = { eras: [{ id: "sv", label: "Scarlet & Violet", sortOrder: 1 }], sets: [{ id: "sv1", label: "Temporal Forces", eraId: "sv", assets: ["cards", "sealed"] }], cardSegments: { segments: [{ key: "sir", label: "Special Illustration Rare" }] }, sealedProductFamilies: { segments: [{ key: "bundle", label: "Booster Bundles" }] } };
const RAW = { key: "raw", available: true };
function mount(props = {}) { let renderer; act(() => { renderer = TestRenderer.create(<MarketExplorerQueryBuilder options={OPTIONS} optionsStatus="ready" currentPlan="premium" preparedSeries={[RAW]} activeSeries={[]} benchmarkEntries={[]} onAddPrepared={() => "added"} onAddQuery={async () => "added"} {...props} />); }); return renderer; }
const byData = (renderer, key) => renderer.root.find((node) => node.props?.[key] !== undefined);
const openDisclosure = (renderer, id) => act(() => renderer.root.findByProps({ "data-explorer-disclosure-toggle": id }).props.onClick());
const textOf = (node) => typeof node === "string" || typeof node === "number" ? String(node) : (node?.children || []).map(textOf).join(" ");
const CARD_PREPARED = [
  { key: "sir", label: "Special Illustration Rare", group: "card", available: true, changes: { "30D": { percent: 8.2 } }, trend: [{ value: 100 }, { value: 108.2 }] },
  { key: "ir", label: "Illustration Rare", group: "card", available: true, changes: { "30D": { percent: 5.3 } }, trend: [{ value: 100 }, { value: 90 }] },
];
const SEALED_PREPARED = [
  { key: "booster-box", label: "Booster Box", group: "sealed", available: true, changes: { "30D": { percent: 7.1 } }, trend: [{ value: 100 }, { value: 107.1 }] },
];

test("Screen selection is immediate, transfers visibly, and leaves Builder output unchanged", () => {
  const renderer = mount({ preparedSeries: [...CARD_PREPARED, ...SEALED_PREPARED] });
  openDisclosure(renderer, "cardsScreens");
  const previewBefore = textOf(byData(renderer, "data-current-market-preview"));
  const rarity = renderer.root.findByProps({ "data-market-screen": "rarity-leaders" });
  act(() => rarity.props.onClick());
  assert.equal(renderer.root.find((node) => node.type === "button" && node.props?.["data-market-screen"] === "rarity-leaders").props["aria-pressed"], true);
  assert.equal(renderer.root.findByProps({ "data-market-screen": "rarity-leaders" }).findByProps({ "data-explorer-selection-check": "selected" }).props["aria-hidden"], "true");
  assert.deepEqual(renderer.root.findAll((node) => node.props?.["data-market-screen-result"] !== undefined).map((node) => node.props["data-market-screen-result"]), ["sir", "ir"]);
  assert.equal(textOf(byData(renderer, "data-current-market-preview")), previewBefore);
  act(() => renderer.root.findByProps({ "data-market-screen": "largest-drawdowns" }).props.onClick());
  assert.equal(renderer.root.find((node) => node.type === "button" && node.props?.["data-market-screen"] === "rarity-leaders").props["aria-pressed"], false);
  assert.equal(renderer.root.find((node) => node.type === "button" && node.props?.["data-market-screen"] === "largest-drawdowns").props["aria-pressed"], true);
});

test("Screen result Add calls only onAddPrepared and Active remains an explicit non-removal state", () => {
  const calls = []; let queryCalls = 0;
  const renderer = mount({ preparedSeries: CARD_PREPARED, activeSeries: [CARD_PREPARED[1]], onAddPrepared: (key) => calls.push(key), onAddQuery: async () => { queryCalls += 1; } });
  openDisclosure(renderer, "cardsScreens");
  act(() => renderer.root.findByProps({ "data-market-screen": "momentum-leaders" }).props.onClick());
  const add = renderer.root.findByProps({ "data-market-screen-result": "sir" });
  const active = renderer.root.findByProps({ "data-market-screen-result": "ir" });
  assert.equal(add.props["aria-label"], "Add Special Illustration Rare");
  assert.equal(active.props["aria-label"], "Active Illustration Rare");
  assert.equal(active.props.disabled, undefined);
  act(() => add.props.onClick());
  act(() => active.props.onClick());
  assert.deepEqual(calls, ["sir"]);
  assert.equal(queryCalls, 0);
});

test("Screen asset context is isolated and invalid asset-specific selection clears", () => {
  const renderer = mount({ preparedSeries: [...CARD_PREPARED, ...SEALED_PREPARED] });
  openDisclosure(renderer, "cardsScreens");
  assert.equal(renderer.root.findAllByProps({ "data-market-screen": "sealed-format-leaders" }).length, 0);
  act(() => renderer.root.findByProps({ "data-market-screen": "rarity-leaders" }).props.onClick());
  openDisclosure(renderer, "sealedBuilder");
  openDisclosure(renderer, "sealedScreens");
  assert.equal(renderer.root.findAllByProps({ "data-market-screen": "rarity-leaders" }).length, 0);
  assert.ok(renderer.root.findByProps({ "data-market-screen": "sealed-format-leaders" }));
  act(() => renderer.root.findByProps({ "data-market-screen": "momentum-leaders" }).props.onClick());
  assert.deepEqual(renderer.root.findAll((node) => node.props?.["data-market-screen-result"] !== undefined).map((node) => node.props["data-market-screen-result"]), ["booster-box"]);
});

test("Quick Preset labels never render inside Screens", () => {
  const renderer = mount({ preparedSeries: CARD_PREPARED });
  openDisclosure(renderer, "cardsScreens");
  const screens = renderer.root.findByProps({ "data-explorer-disclosure": "cardsScreens" });
  assert.doesNotMatch(textOf(screens), /Obtainable|Intermediate|Premium|New Release|Established|Top 10 in Selected Set/);
});

test("an unlocked empty Screen stays selected and explains the empty prepared scan", () => {
  const renderer = mount({ preparedSeries: [] });
  openDisclosure(renderer, "cardsScreens");
  act(() => renderer.root.findByProps({ "data-market-screen": "momentum-leaders" }).props.onClick());
  assert.match(textOf(renderer.root.findByProps({ "data-market-screen-results": true })), /No prepared markets currently qualify for this Screen/);
  assert.equal(renderer.root.find((node) => node.type === "button" && node.props?.["data-market-screen"] === "momentum-leaders").props["aria-pressed"], true);
});

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
  assert.match(renderer.root.findByProps({ role: "status" }).children.join(""), /Loading canonical filters/);
});

test("Quick Preset applies immediately and preserves multi-set scope", () => {
  const renderer = mount({ options: { ...OPTIONS, sets: [
    ...OPTIONS.sets, { id: "sv2", label: "Paldea Evolved", eraId: "sv", assets: ["cards"] },
  ] } });
  openDisclosure(renderer, "cardsEraSets");
  act(() => renderer.root.find((node) => node.props?.name === "cards-set").props.onChange(["sv1", "sv2"]));
  openDisclosure(renderer, "cardsQuickPresets");
  act(() => renderer.root.findByProps({ "data-market-preset": "obtainable-market" }).props.onClick());
  assert.match(byData(renderer, "data-current-market-preview").children.join(""), /obtainable/i);
});

test("Sealed context excludes card-only Screens and uses asset-specific composition", () => {
  const renderer = mount();
  openDisclosure(renderer, "sealedBuilder");
  openDisclosure(renderer, "sealedScreens");
  assert.equal(renderer.root.findAllByProps({ "data-market-screen": "rarity-leaders" }).length, 0);
  assert.ok(renderer.root.findByProps({ "data-market-screen": "sealed-format-leaders" }));
  openDisclosure(renderer, "sealedComposition");
  assert.ok(renderer.root.find((node) => node.props?.ariaLabel === "Market Mode").props.options.some((row) => row.label === "Top N by Price"));
});

test("Top 10 in Selected Set remains a Quick Preset", () => {
  const renderer = mount({ currentPlan: "premium" });
  openDisclosure(renderer, "cardsEraSets");
  act(() => byData(renderer, "data-market-builder-scroll-region"));
  // Select the one available set directly via the MultiSelectFilter's onChange.
  const setFilter = renderer.root.find(
    (node) => node.props?.name === "cards-set"
  );
  act(() => setFilter.props.onChange(["sv1"]));
  openDisclosure(renderer, "cardsQuickPresets");
  act(() => renderer.root.find(
    (node) => node.props?.["data-market-preset"] === "set-top-ten"
  ).props.onClick());
  assert.match(byData(renderer, "data-current-market-preview").children.join(""), /Top 10/);
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
