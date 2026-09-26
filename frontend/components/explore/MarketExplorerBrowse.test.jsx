import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketExplorerBrowse from "./MarketExplorerBrowse.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.requestAnimationFrame = (callback) => { callback(); return 1; };

const eras = Array.from({ length: 17 }, (_, index) => ({ market_key: `era:${index}`, market_type: "era", era_id: `e${index}`, label: index === 0 ? "Sword and Shield" : `Era ${index}` }));
const sets = Array.from({ length: 106 }, (_, index) => ({ market_key: `set:${index}`, market_type: "set", parent_era_id: `e${index % 17}`, label: index === 0 ? "Evolving Skies" : index === 1 ? "Temporal Forces" : `Set ${String(index).padStart(3, "0")}` }));
const quick = ["Obtainable", "Intermediate", "Premium", "New Releases", "Established", "Global Top 10"].map((label, index) => ({ market_key: ["curated:obtainable", "curated:intermediate", "curated:premium", "curated:new-releases", "curated:established", "curated:global-top10"][index], market_type: "curated", label }));
const sealed = [["format:booster-box", "Booster Boxes"], ["format:etb", "Elite Trainer Boxes"], ["format:pack", "Packs"]].map(([market_key, label]) => ({ market_key, market_type: "prepared_format", asset: "sealed", label }));
const directory = [...eras, ...sets, ...quick, ...sealed];
const noop = () => {};

function category(renderer, id) { return renderer.root.findByProps({ "data-market-directory-category": id }); }
function rows(renderer) { return renderer.root.findAll((node) => node.type === "button" && node.props?.["data-prepared-market"]); }

test("prepared categories populate, filter, switch, select, stay open, and preserve active feedback", async () => {
  const selected = [];
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => { fetches += 1; throw new Error("category interaction must not fetch"); };
  let renderer;
  const props = { directory, activeKeys: [], canCompare: true, onSelect: (key) => selected.push(key), onCompare: noop, onBuild: noop };
  try {
    await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse {...props} />, { createNodeMock: () => ({ focus: noop }) }); });
    await act(async () => category(renderer, "sets").props.onClick());
    assert.equal(rows(renderer).length, 106);
    const search = renderer.root.findByProps({ "data-market-browser-search": true });
    await act(async () => search.props.onChange({ target: { value: "evolv" } }));
    assert.equal(rows(renderer).length, 1);

    await act(async () => category(renderer, "eras").props.onClick());
    assert.equal(renderer.root.findByProps({ "data-market-browser-search": true }).props.value, "");
    assert.equal(rows(renderer).length, 17);
    await act(async () => category(renderer, "quick").props.onClick());
    assert.equal(rows(renderer).length, 6);
    const quickSearch = renderer.root.findByProps({ "data-market-browser-search": true });
    await act(async () => quickSearch.props.onChange({ target: { value: "top" } }));
    assert.equal(rows(renderer)[0].props.children[0].props.children[0], "Global Top 10 Cards");
    await act(async () => rows(renderer)[0].props.onClick());
    assert.deepEqual(selected, ["curated:global-top10"]);
    // Selecting a market must NOT close the menu: this is the additive
    // multi-select workflow (open Sets -> click Base -> stays open -> click
    // Fossil -> stays open). Only outside-click/Escape/toggle should close it.
    assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 1);

    await act(async () => { renderer.update(<MarketExplorerBrowse {...props} activeKeys={["curated:global-top10"]} />); });
    // The menu is still open on "quick" (selecting no longer auto-closes it),
    // so re-clicking the same category button would toggle it closed instead
    // of reopening it — no click needed here.
    assert.equal(rows(renderer).find((row) => row.props["data-prepared-market"] === "curated:global-top10").props["aria-pressed"], true);
    // Search is deliberately preserved across a selection (mid multi-select),
    // so clear it explicitly before exercising keyboard nav over the full list.
    const keyboard = renderer.root.findByProps({ "data-market-browser-search": true });
    await act(async () => keyboard.props.onChange({ target: { value: "" } }));
    await act(async () => keyboard.props.onKeyDown({ key: "ArrowDown", preventDefault: noop }));
    await act(async () => keyboard.props.onKeyDown({ key: "Enter", preventDefault: noop }));
    // No highlight exists until the first ArrowDown, which lands on row 0.
    assert.equal(selected.at(-1), "curated:obtainable");
    assert.equal(fetches, 0);
  } finally {
    globalThis.fetch = originalFetch;
    renderer?.unmount();
  }
});

test("multiple Sets remain selected across successive picks without the menu closing", async () => {
  const selected = [];
  let renderer;
  const props = { directory, activeKeys: [], canCompare: true, onSelect: (key) => selected.push(key), onCompare: noop, onBuild: noop };
  try {
    await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse {...props} />, { createNodeMock: () => ({ focus: noop }) }); });
    await act(async () => category(renderer, "sets").props.onClick());
    const firstKey = rows(renderer)[0].props["data-prepared-market"];
    await act(async () => rows(renderer)[0].props.onClick());
    assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 1);
    const secondKey = rows(renderer)[1].props["data-prepared-market"];
    await act(async () => rows(renderer)[1].props.onClick());
    assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 1);
    const thirdKey = rows(renderer)[2].props["data-prepared-market"];
    await act(async () => rows(renderer)[2].props.onClick());
    assert.deepEqual(selected, [firstKey, secondKey, thirdKey]);
    assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 1);
  } finally {
    renderer?.unmount();
  }
});

test("Quick Markets stay selected together and do not delete prior selections", async () => {
  const selected = [];
  let renderer;
  const props = { directory, activeKeys: [], canCompare: true, onSelect: (key) => selected.push(key), onCompare: noop, onBuild: noop };
  try {
    await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse {...props} />, { createNodeMock: () => ({ focus: noop }) }); });
    await act(async () => category(renderer, "quick").props.onClick());
    await act(async () => rows(renderer)[0].props.onClick());
    await act(async () => rows(renderer)[1].props.onClick());
    assert.deepEqual(selected, ["curated:obtainable", "curated:intermediate"]);
    assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 1);
  } finally {
    renderer?.unmount();
  }
});

test("unmatched query is category-specific while unavailable never masquerades as no-match", async () => {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse directory={directory} onSelect={noop} onCompare={noop} onBuild={noop} />); });
  await act(async () => category(renderer, "sets").props.onClick());
  await act(async () => renderer.root.findByProps({ "data-market-browser-search": true }).props.onChange({ target: { value: "none-such" } }));
  assert.match(JSON.stringify(renderer.toJSON()), /No matching Sets\./);
  await act(async () => { renderer.update(<MarketExplorerBrowse directory={[]} directoryStatus="unavailable" onSelect={noop} onCompare={noop} onBuild={noop} />); });
  assert.match(JSON.stringify(renderer.toJSON()), /Market directory is temporarily unavailable\./);
  assert.doesNotMatch(JSON.stringify(renderer.toJSON()), /No matching Sets\./);
  renderer.unmount();
});

const highlightedRows = (renderer) => rows(renderer).filter((row) => row.props["data-search-highlighted"] === "true");
const options = (renderer) => renderer.root.findAll((node) => node.type === "li" && node.props?.role === "option");
const rowStates = (renderer) => options(renderer).map((node) => node.props["data-market-row-state"]);
const searchOf = (renderer) => renderer.root.findByProps({ "data-market-browser-search": true });
const key = (renderer, name) => act(async () => searchOf(renderer).props.onKeyDown({ key: name, preventDefault: noop }));
async function mount(props = {}) {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse directory={directory} activeKeys={[]} canCompare onSelect={noop} onCompare={noop} onBuild={noop} {...props} />, { createNodeMock: () => ({ focus: noop }) }); });
  return renderer;
}

test("opening Sets, Eras and Quick Markets highlights nothing (no false first-row selection)", async () => {
  const renderer = await mount();
  for (const id of ["sets", "eras", "quick"]) {
    await act(async () => category(renderer, id).props.onClick());
    assert.ok(rows(renderer).length > 0);
    assert.equal(highlightedRows(renderer).length, 0, id);
    assert.ok(rowStates(renderer).every((state) => state === "idle"), id);
    assert.equal(searchOf(renderer).props["aria-activedescendant"], undefined, id);
    await act(async () => category(renderer, id).props.onClick());
  }
  renderer.unmount();
});

test("only activeKeys drive active styling", async () => {
  const renderer = await mount({ activeKeys: ["set:5"] });
  await act(async () => category(renderer, "sets").props.onClick());
  assert.equal(rowStates(renderer).filter((state) => state === "active").length, 1);
  assert.equal(rows(renderer).find((row) => row.props["aria-pressed"] === true).props["data-prepared-market"], "set:5");
  renderer.unmount();
});

test("arrow navigation creates a keyboard highlight without changing activeKeys or selecting", async () => {
  const selected = [];
  const renderer = await mount({ activeKeys: ["curated:premium"], onSelect: (k) => selected.push(k) });
  await act(async () => category(renderer, "quick").props.onClick());
  await key(renderer, "ArrowDown");
  assert.equal(highlightedRows(renderer).length, 1);
  assert.equal(highlightedRows(renderer)[0].props["data-prepared-market"], "curated:obtainable");
  assert.match(searchOf(renderer).props["aria-activedescendant"], /-0$/);
  assert.deepEqual(selected, []);
  assert.equal(rows(renderer).filter((row) => row.props["aria-pressed"] === true).length, 1, "active set unchanged");
  await key(renderer, "ArrowUp");
  await key(renderer, "ArrowUp");
  assert.equal(highlightedRows(renderer).length, 1);
  renderer.unmount();
});

test("active, keyboard-highlighted and hover are three distinct visual states", async () => {
  const renderer = await mount({ activeKeys: ["curated:obtainable"] });
  await act(async () => category(renderer, "quick").props.onClick());
  await key(renderer, "ArrowDown");
  await key(renderer, "ArrowDown");
  const states = rowStates(renderer);
  assert.equal(states[0], "active");
  assert.equal(states[1], "keyboard");
  const items = options(renderer);
  assert.match(items[0].props.className, /border-\[rgb\(45,212,191\)\]/);
  assert.doesNotMatch(items[0].props.className, /ring-sky/);
  assert.match(items[1].props.className, /ring-sky-400/);
  assert.doesNotMatch(items[1].props.className, /rgb\(45,212,191\)/);
  assert.match(items[2].props.className, /hover:bg-white/);
  renderer.unmount();
});

test("search reset and category switch clear the keyboard highlight and invent no first row", async () => {
  const renderer = await mount();
  await act(async () => category(renderer, "eras").props.onClick());
  await key(renderer, "ArrowDown");
  assert.equal(highlightedRows(renderer).length, 1);
  await act(async () => searchOf(renderer).props.onChange({ target: { value: "era 1" } }));
  assert.equal(highlightedRows(renderer).length, 0);
  assert.ok(rowStates(renderer).every((state) => state === "idle"));
  await key(renderer, "ArrowDown");
  await act(async () => category(renderer, "quick").props.onClick());
  assert.equal(highlightedRows(renderer).length, 0);
  renderer.unmount();
});

test("Enter without a highlight selects nothing unless the search has exactly one match", async () => {
  const selected = [];
  const renderer = await mount({ onSelect: (k) => selected.push(k) });
  await act(async () => category(renderer, "quick").props.onClick());
  await key(renderer, "Enter");
  assert.deepEqual(selected, []);
  await act(async () => searchOf(renderer).props.onChange({ target: { value: "global" } }));
  await key(renderer, "Enter");
  assert.deepEqual(selected, ["curated:global-top10"]);
  renderer.unmount();
});

test("directory has Cards | Sealed | Graded; Cards shows Sets/Eras/Quick/Build", async () => {
  const renderer = await mount();
  const layers = renderer.root.findAll((node) => node.type === "button" && node.props?.["data-market-directory-asset"]);
  assert.deepEqual(layers.map((node) => node.props["data-market-directory-asset"]), ["cards", "sealed", "graded"]);
  assert.equal(layers[0].props["aria-pressed"], true);
  for (const id of ["sets", "eras", "quick"]) assert.equal(renderer.root.findAllByProps({ "data-market-directory-category": id }).length, 1);
  assert.equal(renderer.root.findAllByProps({ "data-market-explorer-build-trigger": true }).length, 1);
  renderer.unmount();
});

test("Sealed lists the real prepared sealed rows and no card Sets/Eras", async () => {
  const renderer = await mount();
  await act(async () => renderer.root.findByProps({ "data-market-directory-asset": "sealed" }).props.onClick());
  // V1 COMPATIBILITY: the flat "Sealed Markets" list is the only sealed category (no V2 rows).
  assert.equal(renderer.root.findAllByProps({ "data-market-directory-category": "sets" }).length, 0);
  assert.equal(renderer.root.findAllByProps({ "data-market-directory-category": "types" }).length, 0);
  await act(async () => category(renderer, "sealed").props.onClick());
  assert.deepEqual(rows(renderer).map((row) => row.props["data-prepared-market"]).sort(), ["format:booster-box", "format:etb", "format:pack"]);
  await act(async () => searchOf(renderer).props.onChange({ target: { value: "elite" } }));
  assert.deepEqual(rows(renderer).map((row) => row.props["data-prepared-market"]), ["format:etb"]);
  renderer.unmount();
});

test("Sealed with no published sealed rows is honestly empty, never fabricated", async () => {
  const renderer = await mount({ directory: [...eras, ...sets, ...quick] });
  await act(async () => renderer.root.findByProps({ "data-market-directory-asset": "sealed" }).props.onClick());
  await act(async () => category(renderer, "sealed").props.onClick());
  assert.equal(rows(renderer).length, 0);
  assert.match(JSON.stringify(renderer.toJSON()), /No canonical Sealed Markets are currently published\./);
  renderer.unmount();
});

test("Graded is selectable but publishes no markets: it shows the unavailable reason and cannot select anything", async () => {
  const selected = [];
  const renderer = await mount({ onSelect: (k) => selected.push(k), gradedReason: "Graded production coverage is not yet broad enough." });
  const graded = renderer.root.findByProps({ "data-market-directory-asset": "graded" });
  assert.notEqual(graded.props.disabled, true);
  await act(async () => graded.props.onClick());
  assert.match(JSON.stringify(renderer.toJSON()), /Graded production coverage is not yet broad enough\./);
  assert.equal(renderer.root.findAllByProps({ "data-market-directory-category": "sets" }).length, 0);
  assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 0);
  assert.equal(renderer.root.findAllByProps({ "data-market-explorer-build-trigger": true }).length, 0);
  assert.deepEqual(selected, []);
  renderer.unmount();
});

test("changing the directory asset is browsing state only: no callbacks, active keys untouched", async () => {
  const calls = [];
  const renderer = await mount({ activeKeys: ["set:1", "format:booster-box"], onSelect: (k) => calls.push(["select", k]), onCompare: (k) => calls.push(["compare", k]) });
  await act(async () => renderer.root.findByProps({ "data-market-directory-asset": "sealed" }).props.onClick());
  await act(async () => renderer.root.findByProps({ "data-market-directory-asset": "cards" }).props.onClick());
  assert.deepEqual(calls, []);
  await act(async () => renderer.root.findByProps({ "data-market-directory-asset": "sealed" }).props.onClick());
  await act(async () => category(renderer, "sealed").props.onClick());
  assert.equal(rows(renderer).find((row) => row.props["data-prepared-market"] === "format:booster-box").props["aria-pressed"], true);
  renderer.unmount();
});
