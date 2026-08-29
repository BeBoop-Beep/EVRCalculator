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

test("editing the builder does not commit", () => {
  let preparedCalls = 0; let queryCalls = 0;
  const renderer = mount({ onAddPrepared: () => { preparedCalls += 1; }, onAddQuery: async () => { queryCalls += 1; } });
  openDisclosure(renderer, "sealedBuilder");
  act(() => byData(renderer, "data-builder-all-sealed").props.onClick());
  assert.equal(preparedCalls + queryCalls, 0);
  assert.equal(renderer.root.findByProps({ "data-market-explorer-filters": true }).props["data-market-builder-asset"], "sealed");
});

test("Build Market reuses a prepared parent and retains the draft", async () => {
  const calls = []; const renderer = mount({ onAddPrepared: (key) => { calls.push(key); return "added"; } });
  await act(async () => byData(renderer, "data-market-builder-build").props.onClick());
  assert.deepEqual(calls, ["raw"]);
  assert.equal(renderer.root.findByProps({ "data-market-explorer-filters": true }).props["data-market-builder-asset"], "cards");
});

test("an already-active parent is a clear non-action", () => {
  const renderer = mount({ activeSeries: [RAW] }); const button = byData(renderer, "data-market-builder-build");
  assert.equal(button.props.disabled, true); assert.equal(button.props.children, "Already Active");
});

test("Clear resets the canonical draft", () => {
  const renderer = mount(); openDisclosure(renderer, "sealedBuilder"); act(() => byData(renderer, "data-builder-all-sealed").props.onClick()); act(() => byData(renderer, "data-market-builder-clear").props.onClick());
  assert.equal(renderer.root.findByProps({ "data-market-explorer-filters": true }).props["data-market-builder-asset"], "cards");
});

test("mobile disclosure exposes the same builder", () => {
  const renderer = mount(); const toggle = byData(renderer, "data-market-builder-mobile-toggle"); assert.equal(toggle.props["aria-expanded"], false); act(() => toggle.props.onClick()); assert.equal(byData(renderer, "data-market-builder-mobile-toggle").props["aria-expanded"], true);
});
