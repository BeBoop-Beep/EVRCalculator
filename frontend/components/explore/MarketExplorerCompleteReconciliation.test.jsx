import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketExplorerBrowse from "./MarketExplorerBrowse.jsx";
import MarketExplorerActiveMarkets from "./MarketExplorerActiveMarkets.jsx";
import MarketPerformanceChart from "./MarketPerformanceChart.jsx";
import MarketExplorerSealedTypes from "./MarketExplorerSealedTypes.jsx";
import { buildFocusTools } from "./MarketExplorerFocusTools.jsx";
import { resolveFocusToolStates } from "@/lib/explore/marketExplorerAccess.mjs";
import { assetContextLabel, groupPreparedDirectory } from "@/lib/explore/marketExplorerPrepared.mjs";
import { buildConstituentSwitcherEntries } from "@/lib/explore/marketExplorerWorkspace.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.requestAnimationFrame = (callback) => { callback(); return 1; };
const noop = () => {};
const read = (rel) => fs.readFileSync(path.resolve(process.cwd(), rel), "utf8").replace(/\r\n/g, "\n");
const texts = (node) => JSON.stringify(node.toJSON());

// --- Focus tool controls (Demand Pressure / inDex Fair Value) ---------------------------------
const renderTools = async (plan, capabilities) => {
  const states = resolveFocusToolStates(plan, "set:a", capabilities);
  const tools = buildFocusTools({ states, fairValueOn: true, onToggle: noop });
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<div>{tools.map((tool) => <React.Fragment key={tool.id}>{tool.render({})}</React.Fragment>)}</div>); });
  const control = (id) => renderer.root.findByProps({ "data-market-explorer-focus-tool": id });
  return { renderer, control };
};

test("Basic: Demand Pressure and Fair Value are locked, disabled, and never show a value", async () => {
  const { renderer, control } = await renderTools(null);
  assert.equal(control("demand-pressure").props["data-focus-tool-state"], "locked");
  assert.equal(control("fair-value").props["data-focus-tool-state"], "locked");
  assert.match(texts(renderer), /Demand Pressure requires Index\+/);
  assert.match(texts(renderer), /Premium/);
  for (const button of renderer.root.findAll((n) => n.props?.["data-market-explorer-focus-tool-button"])) assert.equal(button.props.disabled, true);
});

test("Index+: Demand Pressure UNAVAILABLE (disabled with reason), Fair Value Premium-locked", async () => {
  const { renderer, control } = await renderTools("plus");
  assert.equal(control("demand-pressure").props["data-focus-tool-state"], "unavailable");
  assert.match(texts(renderer), /Demand Pressure data is not available for this market yet\./);
  assert.equal(control("fair-value").props["data-focus-tool-state"], "locked");
});

test("Premium without published authority: both controls unavailable and disabled", async () => {
  const { renderer, control } = await renderTools("premium");
  assert.equal(control("demand-pressure").props["data-focus-tool-state"], "unavailable");
  assert.equal(control("fair-value").props["data-focus-tool-state"], "unavailable");
  assert.match(texts(renderer), /inDex Fair Value is not available for this market yet\./);
  for (const button of renderer.root.findAll((n) => n.props?.["data-market-explorer-focus-tool-button"])) assert.equal(button.props.disabled, true);
});

test("Premium with an explicitly published Fair Value: control is live and reflects the ON state", async () => {
  const { renderer, control } = await renderTools("premium", { demandPressure: {}, fairValue: { "set:a": { available: true, values: [1, 2] } } });
  assert.equal(control("fair-value").props["data-focus-tool-state"], "available");
  const button = renderer.root.findByProps({ "data-market-explorer-focus-tool-button": "fair-value" });
  assert.equal(button.props.disabled, false);
  assert.equal(button.props["aria-pressed"], true);
});

test("Client wires Fair Value default-ON on entering focus and a per-focus toggle (source contract)", () => {
  const source = read("components/explore/MarketExplorerClient.jsx");
  assert.match(source, /setFocusToolToggles\(\{\}\)/, "toggles reset when focus changes");
  assert.match(source, /focusToolToggles\["fair-value"\] \?\? true/, "Fair Value defaults ON when available");
  assert.match(source, /overlays=\{chartOverlays\}/);
  assert.match(source, /focusTools=\{focusTools\}/);
});

// --- Server-published overlay seam --------------------------------------------------------------
const model = { dates: ["2026-01-01", "2026-01-02", "2026-01-03"], series: [{ key: "set:a", label: "A", color: "#22c55e", values: [100, 101, 103] }] };
test("chart draws a server-published overlay and draws nothing by default", async () => {
  let none; let some;
  await act(async () => { none = TestRenderer.create(<MarketPerformanceChart model={model} timeframe="All" viewMode="index" />); });
  assert.equal(none.root.findAll((n) => n.props?.["data-market-performance-overlay"]).length, 0);
  await act(async () => { some = TestRenderer.create(<MarketPerformanceChart model={model} timeframe="All" viewMode="index" overlays={[{ id: "fair-value:set:a", values: [99, 100, 102] }]} />); });
  assert.equal(some.root.findAll((n) => n.type === "polyline" && n.props["data-market-performance-overlay"] === "fair-value:set:a").length, 1);
  await act(async () => { some.update(<MarketPerformanceChart model={model} timeframe="All" viewMode="index" overlays={[{ id: "bad", values: [1] }]} />); });
  assert.equal(some.root.findAll((n) => n.props?.["data-market-performance-overlay"]).length, 0, "a misaligned series is ignored, never stretched");
});

// --- Active chips recede while another market is focused ----------------------------------------
const series = ["a", "b", "c"].map((id, i) => ({ key: `set:${id}`, label: `Set ${id}`, shortLabel: `Set ${id} — Cards`, color: ["#22c55e", "#38bdf8", "#f59e0b"][i], asset: "cards", trend: [], changes: {} }));
test("focused chip keeps its identity; every other chip is dimmed but stays interactive", async () => {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerActiveMarkets series={series} focusedSeriesKey="set:b" onFocus={noop} onRemove={noop} onInspect={noop} />); });
  const chip = (key) => renderer.root.findByProps({ "data-market-explorer-active-chip": key });
  assert.equal(chip("set:b").props["data-market-explorer-active-chip-dimmed"], "false");
  assert.equal(chip("set:a").props["data-market-explorer-active-chip-dimmed"], "true");
  assert.match(chip("set:a").props.className, /grayscale/);
  assert.doesNotMatch(chip("set:b").props.className, /grayscale/);
  // Dimmed chips remain fully operable.
  assert.equal(renderer.root.findByProps({ "data-market-explorer-active-inspect": "set:a" }).props.disabled, undefined);
  await act(async () => { renderer.update(<MarketExplorerActiveMarkets series={series} focusedSeriesKey={null} onFocus={noop} />); });
  for (const key of ["set:a", "set:b", "set:c"]) assert.equal(chip(key).props["data-market-explorer-active-chip-dimmed"], "false");
});

test("the magnifier is on the LEFT of the chip and reachable without hover (touch)", () => {
  const source = read("components/explore/MarketExplorerActiveMarkets.jsx");
  assert.ok(source.indexOf("data-market-explorer-active-focus=") < source.indexOf("data-market-explorer-active-visibility="), "focus control precedes the rest of the chip");
  assert.match(source, /\[@media\(hover:hover\)\]:opacity-0/, "hover-hiding is scoped to hover-capable devices only");
});

// --- Sealed IA is one structure in V1 and V2 -----------------------------------------------------
const v1Sealed = [["sealed-format:boosterBox", "Booster Boxes"], ["sealed-format:etb", "Elite Trainer Boxes"], ["sealed-format:packs", "Packs"]]
  .map(([market_key, label]) => ({ market_key, market_type: "prepared_format", asset: "sealed", label, source_kind: "prepared_sealed_snapshots" }));
const cards = [{ market_key: "set:a", market_type: "set", asset: "cards", label: "Fossil", parent_era_id: "e1" }, { market_key: "era:e1", market_type: "era", asset: "cards", era_id: "e1", label: "Base" }];
const v2Sealed = [
  { market_key: "sealed-set:a", market_type: "set", scope_kind: "set", asset: "sealed", label: "Fossil", parent_era_id: "e1", surface_version: "v2" },
  { market_key: "sealed-era:e1", market_type: "era", scope_kind: "era", asset: "sealed", label: "Base", era_id: "e1", surface_version: "v2" },
  { market_key: "sealedMarket", market_type: "parent", scope_kind: "parent", asset: "sealed", label: "Total Sealed", surface_version: "v2" },
  { market_key: "raw", market_type: "parent", scope_kind: "parent", asset: "cards", label: "Raw Card Market", surface_version: "v2" },
  { market_key: "sealed-type:case", market_type: "prepared_format", scope_kind: "type", asset: "sealed", label: "Cases", surface_version: "v2" },
];
const mountBrowse = async (directory, extra = {}) => {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse directory={directory} activeKeys={[]} canCompare={false} onSelect={noop} onCompare={noop} onBuild={noop} enableContextualSearch={false} assetLayer="sealed" {...extra} />, { createNodeMock: () => ({ focus: noop }) }); });
  return renderer;
};
const categories = (renderer) => renderer.root.findAll((n) => n.type === "button" && n.props["data-market-directory-category"]).map((n) => n.props["data-market-directory-category"]);
const open = async (renderer, id) => act(async () => renderer.root.findByProps({ "data-market-directory-category": id }).props.onClick());

test("V1 Sealed mode keeps the designed Cards-like IA: Sets, Eras, Quick Markets, Sealed Types (no flat Sealed Markets)", async () => {
  const renderer = await mountBrowse([...cards, ...v1Sealed]);
  assert.deepEqual(categories(renderer), ["sets", "eras", "quick", "types"]);
  assert.doesNotMatch(texts(renderer), /Sealed Markets/);
  await open(renderer, "sets");
  assert.match(texts(renderer), /Sealed Set markets are awaiting the next prepared market generation\./);
  await open(renderer, "eras");
  assert.match(texts(renderer), /Sealed Era markets are awaiting the next prepared market generation\./);
  await open(renderer, "quick");
  assert.match(texts(renderer), /No approved Sealed Quick Markets yet\./);
});

test("V1 Sealed Types category exposes the published V1 sealed formats and never repeats them elsewhere", async () => {
  const selected = [];
  const renderer = await mountBrowse([...cards, ...v1Sealed], {
    onSelect: (key) => selected.push(key),
    sealedTypesPanel: ({ v2Mode, formatMarkets }) => <MarketExplorerSealedTypes v2Mode={v2Mode} formatMarkets={formatMarkets} status="unavailable" onSelect={(key) => selected.push(key)} />,
  });
  await open(renderer, "types");
  const list = renderer.root.findByProps({ "data-sealed-v1-formats": true });
  assert.equal(list.findAll((n) => n.type === "button" && n.props["data-prepared-market"]).length, 3);
  assert.doesNotMatch(texts(renderer), /temporarily unavailable/, "V1 must not show the V2 asset-options failure");
  assert.match(texts(renderer), /Further Sealed Types/);
  await act(async () => list.findAll((n) => n.type === "button")[0].props.onClick());
  assert.deepEqual(selected, ["sealed-format:boosterBox"]);
  // Not duplicated in Sets / Eras / Quick.
  for (const id of ["sets", "eras", "quick"]) {
    await open(renderer, id);
    assert.equal(renderer.root.findAll((n) => n.type === "button" && String(n.props["data-prepared-market"] || "").startsWith("sealed-format:")).length, 0, id);
  }
});

test("V2 Sealed Sets/Eras/Whole-market rows land in the right categories with asset-qualified labels", async () => {
  const renderer = await mountBrowse([...cards, ...v2Sealed]);
  await open(renderer, "sets");
  const keys = () => renderer.root.findAll((n) => n.type === "button" && n.props["data-prepared-market"]).map((n) => n.props["data-prepared-market"]);
  assert.deepEqual(keys().sort(), ["sealed-set:a", "sealedMarket"].sort());
  await open(renderer, "eras");
  assert.deepEqual(keys(), ["sealed-era:e1"]);
  await open(renderer, "quick");
  assert.deepEqual(keys(), []);
  assert.doesNotMatch(texts(renderer), /awaiting the next prepared/, "V2 with data shows no awaiting copy for Sets/Eras");
});

test("Cards mode lists the Raw Card Market parent under Sets, once", async () => {
  const renderer = await mountBrowse([...cards, ...v2Sealed], { assetLayer: "cards" });
  await open(renderer, "sets");
  const keys = renderer.root.findAll((n) => n.type === "button" && n.props["data-prepared-market"]).map((n) => n.props["data-prepared-market"]);
  assert.equal(keys.filter((k) => k === "raw").length, 1);
  assert.equal(keys.includes("sealedMarket"), false);
  assert.equal(groupPreparedDirectory(v2Sealed).parents.length, 2);
});

test("row interaction has no per-row compare/upsell button for Basic; paid rows only offer Remove/Retry", async () => {
  const basic = await mountBrowse([...cards], { assetLayer: "cards", canCompare: false });
  await open(basic, "sets");
  assert.equal(basic.root.findAll((n) => n.props?.["data-compare-market"]).length, 0);
  assert.doesNotMatch(texts(basic), /Compare with Index\+|Sign in to compare/);
  const paid = await mountBrowse([...cards], { assetLayer: "cards", canCompare: true, activeKeys: ["set:a"] });
  await open(paid, "sets");
  const buttons = paid.root.findAll((n) => n.type === "button" && n.props["data-compare-market"]);
  assert.deepEqual(buttons.map((b) => b.props["data-compare-market"]), ["set:a"]);
  assert.match(texts(paid), /Remove/);
});

test("Graded browse shows neither Cards rarity nor Sealed Types", async () => {
  const renderer = await mountBrowse([...cards, ...v1Sealed], { assetLayer: "graded" });
  assert.deepEqual(categories(renderer), []);
  assert.match(texts(renderer), /Graded markets are unavailable/);
});

// --- Asset context labels ------------------------------------------------------------------------
test("asset context labels qualify Set/Era/Rarity/Type identities but leave natural names alone", () => {
  assert.equal(assetContextLabel({ label: "Fossil", market_type: "set", asset: "cards" }), "Fossil — Cards");
  assert.equal(assetContextLabel({ label: "Fossil", market_type: "set", asset: "sealed" }), "Fossil — Sealed");
  assert.equal(assetContextLabel({ label: "Sword & Shield", market_type: "era", asset: "sealed" }), "Sword & Shield — Sealed");
  assert.equal(assetContextLabel({ label: "Rare Ultra", market_type: "prepared_rarity", asset: "cards" }), "Rare Ultra — Cards");
  assert.equal(assetContextLabel({ label: "Booster Boxes", market_type: "prepared_format", asset: "sealed" }), "Booster Boxes — Sealed");
  assert.equal(assetContextLabel({ label: "Total Sealed", market_type: "parent", asset: "sealed" }), "Total Sealed");
  assert.equal(assetContextLabel({ label: "Raw Card Market", market_type: "parent", asset: "cards" }), "Raw Card Market");
  assert.equal(assetContextLabel({ label: "Total Sealed Market", market_type: "prepared_format", asset: "sealed" }), "Total Sealed Market");
});

// --- Constituent switcher ------------------------------------------------------------------------
test("switcher lists every active market; a market without composition is disabled WITH a reason", () => {
  const entries = buildConstituentSwitcherEntries([
    { key: "set:a", label: "Fossil", color: "#fff", compositionKind: "index_and_composition", availability: "available" },
    { key: "raw", label: "Raw Card Market", color: "#000", compositionKind: "index_only", availability: "unavailable", unavailableReason: "Raw composition is not published in this generation." },
  ], { targetKey: "set:a", hiddenKeys: new Set(["raw"]) });
  assert.equal(entries.length, 2);
  assert.equal(entries[0].disabled, false);
  assert.equal(entries[1].disabled, true);
  assert.ok(entries[1].reason && entries[1].reason.length > 10);
  assert.equal(entries[1].isHidden, true, "a chart-hidden market is still listed");
});

test("broken large-image URL falls back to the placeholder in the preview (source contract)", () => {
  const source = read("components/explore/MarketExplorerConstituentPreview.jsx");
  assert.match(source, /onError=\{\(\) => setPreviewFailed\(true\)\}/);
  assert.match(source, /model\.image\.previewUrl && !previewFailed/);
  assert.match(source, /onError=\{\(\) => setFailed\(true\)\}/, "thumbnail fallback is preserved");
  assert.match(source, /target="_blank"/);
  assert.match(source, /rel="noopener noreferrer"/);
});

test("View and Hide Constituents share the violet centred treatment (structure contract)", () => {
  const chart = read("components/explore/MarketExplorerChart.jsx");
  const client = read("components/explore/MarketExplorerClient.jsx");
  const violet = /border-violet-400\/60 bg-violet-500\/\[\.12\] .*shadow-\[0_0_16px_rgba\(139,92,246,0\.35\)\]/;
  assert.match(chart.slice(chart.indexOf("data-market-explorer-view-details")), violet);
  assert.match(client.slice(client.indexOf("data-market-explorer-hide-details")), violet);
  assert.match(chart, /data-market-explorer-chart-bottom-actions className="flex flex-none justify-center/);
  assert.match(client, /flex flex-none flex-col items-center gap-1\.5 border-b/);
  // One workspace Clear All; no Clear Graph label.
  assert.doesNotMatch(client + read("components/explore/MarketExplorerActiveMarkets.jsx"), />\s*Clear Graph\s*</);
});
