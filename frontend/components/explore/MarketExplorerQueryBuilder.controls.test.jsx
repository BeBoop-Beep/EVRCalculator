import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketExplorerQueryBuilder from "./MarketExplorerQueryBuilder.jsx";
import MarketExplorerExactItemPicker from "./MarketExplorerExactItemPicker.jsx";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const OPTIONS = { eras: [{ id: "sv", label: "Scarlet & Violet", sortOrder: 1 }], sets: [{ id: "sv1", label: "Temporal Forces", eraId: "sv", assets: ["cards", "sealed"] }], cardRarities: { rarities: [{ key: "sir", label: "Special Illustration Rare" }, { key: "legend", label: "LEGEND" }] }, cardSegments: { segments: [{ key: "sir", label: "Special Illustration Rare" }] }, compatibility: { cardRaritySetIds: { sir: ["sv1"], legend: ["sv1"] } }, sealedProductFamilies: { segments: [{ key: "bundle", label: "Booster Bundles" }] } };
const RAW = { key: "raw", available: true };
function mount(props = {}) { let renderer; act(() => { renderer = TestRenderer.create(<MarketExplorerQueryBuilder optionsProvided options={OPTIONS} optionsStatus="ready" currentPlan="premium" preparedSeries={[RAW]} activeSeries={[]} benchmarkEntries={[]} onAddPrepared={() => "added"} onAddQuery={async () => "added"} {...props} />); }); return renderer; }
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
const EDIT_ITEM = { asset: "cards", instrumentId: "card-v1", name: "Charizard", setName: "Base Set", edition: "Unlimited" };
const EDIT_SERIES = { instanceId: "instance-1", key: "query:one", label: "Exact Charizard", spec: { asset: "cards", membershipMode: "explicit", instrumentIds: ["card-v1"], mode: "all" }, exactItems: [EDIT_ITEM] };

async function changeExactEdit(renderer) {
  const next = { asset: "cards", instrumentId: "card-v2", name: "Blastoise", setName: "Base Set", edition: "Unlimited" };
  await act(async () => renderer.root.findByType(MarketExplorerExactItemPicker).props.onChange([EDIT_ITEM, next]));
}

test("closing Exact workspace preserves edit session while explicit Cancel edits exits it", async () => {
  let cancels = 0;
  const renderer = mount({ editingSeries: EDIT_SERIES, onCancelEdit: () => { cancels += 1; } });
  await act(async () => renderer.root.findByProps({ "aria-label": "Close exact item workspace" }).props.onClick());
  assert.equal(cancels, 0);
  await act(async () => renderer.root.findByProps({ "data-market-exact-open": true }).props.onClick());
  await act(async () => renderer.root.findAllByType("button").find((node) => node.children.includes("Cancel edits")).props.onClick());
  assert.equal(cancels, 1);
});

for (const outcome of ["duplicate", "unchanged"]) {
  test(`${outcome} update keeps Exact workspace and selected definition open`, async () => {
    const renderer = mount({ editingSeries: EDIT_SERIES, onUpdateQuery: async () => outcome });
    await changeExactEdit(renderer);
    await act(async () => renderer.root.findAllByType("button").find((node) => node.children.includes("Update Market")).props.onClick());
    assert.ok(renderer.root.findByProps({ "data-market-explorer-exact-workspace": true }));
    assert.equal(renderer.root.findAllByProps({ "data-exact-selected-items": true })[0].findAllByType("li").length, 2);
  });
}

test("successful update closes workspace and exits the same edit instance", async () => {
  const calls = []; let cancels = 0;
  const renderer = mount({ editingSeries: EDIT_SERIES, onUpdateQuery: async (instanceId) => { calls.push(instanceId); return "updated"; }, onCancelEdit: () => { cancels += 1; } });
  await changeExactEdit(renderer);
  await act(async () => renderer.root.findAllByType("button").find((node) => node.children.includes("Update Market")).props.onClick());
  assert.deepEqual(calls, ["instance-1"]);
  assert.equal(cancels, 1);
  assert.equal(renderer.root.findAllByProps({ "data-market-explorer-exact-workspace": true }).length, 0);
});

test("failed update keeps workspace and exact selections intact", async () => {
  const renderer = mount({ editingSeries: EDIT_SERIES, onUpdateQuery: async () => { throw new Error("Canonical update failed"); } });
  await changeExactEdit(renderer);
  await act(async () => renderer.root.findAllByType("button").find((node) => node.children.includes("Update Market")).props.onClick());
  assert.ok(renderer.root.findByProps({ "data-market-explorer-exact-workspace": true }));
  assert.match(textOf(renderer.root), /Canonical update failed/);
  assert.equal(renderer.root.findAllByProps({ "data-exact-selected-items": true })[0].findAllByType("li").length, 2);
});

test("successful new exact Build closes after one semantic query", async () => {
  const calls = [];
  const renderer = mount({ onAddQuery: async (spec, detail) => { calls.push({ spec, detail }); return "added"; } });
  await act(async () => renderer.root.findAll((node) => node.props?.role === "radio").find((node) => textOf(node).includes("Exact Items")).props.onClick());
  await act(async () => renderer.root.findByType(MarketExplorerExactItemPicker).props.onChange([EDIT_ITEM]));
  await act(async () => renderer.root.findByType(MarketExplorerExactItemPicker).findAllByType("button").find((node) => node.children.includes("Build Market")).props.onClick());
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].spec.instrumentIds, ["card-v1"]);
  assert.equal(renderer.root.findAllByProps({ "data-market-explorer-exact-workspace": true }).length, 0);
});

test("Save as new uses one add request, keeps the edited instance untouched, and closes", async () => {
  const addCalls = []; let updateCalls = 0;
  const renderer = mount({ editingSeries: EDIT_SERIES, onAddQuery: async (spec) => { addCalls.push(spec); return "added"; }, onUpdateQuery: async () => { updateCalls += 1; } });
  await changeExactEdit(renderer);
  await act(async () => renderer.root.findByType(MarketExplorerExactItemPicker).findAllByType("button").find((node) => node.children.includes("Save as new")).props.onClick());
  assert.equal(addCalls.length, 1);
  assert.equal(updateCalls, 0);
  assert.equal(renderer.root.findAllByProps({ "data-market-explorer-exact-workspace": true }).length, 0);
});

test("Clear narrowing preserves asset, explicit mode, and selected exact items", async () => {
  const scopedEdit = { ...EDIT_SERIES, spec: { ...EDIT_SERIES.spec, setIds: ["sv1"] } };
  const renderer = mount({ editingSeries: scopedEdit });
  const picker = renderer.root.findByType(MarketExplorerExactItemPicker);
  assert.match(picker.props.narrowingSummary.join(" "), /Temporal Forces/);
  await act(async () => picker.props.onClearNarrowing());
  const next = renderer.root.findByType(MarketExplorerExactItemPicker);
  assert.equal(next.props.asset, "cards");
  assert.deepEqual(next.props.selectedItems.map((item) => item.instrumentId), ["card-v1"]);
  assert.deepEqual(next.props.narrowingSummary, []);
});

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
  assert.match(textOf(renderer.root.findByProps({ role: "status" })), /Loading canonical filters/);
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

test("Sealed context excludes card-only Screens and generic composition membership", () => {
  const renderer = mount();
  openDisclosure(renderer, "sealedBuilder");
  openDisclosure(renderer, "sealedScreens");
  assert.equal(renderer.root.findAllByProps({ "data-market-screen": "rarity-leaders" }).length, 0);
  assert.ok(renderer.root.findByProps({ "data-market-screen": "sealed-format-leaders" }));
  assert.equal(renderer.root.findAllByProps({ "data-explorer-disclosure-toggle": "sealedComposition" }).length, 0);
  assert.match(textOf(renderer.root.findByProps({ "data-explorer-disclosure": "sealedBuilder" })), /Scope.*Filters/);
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
