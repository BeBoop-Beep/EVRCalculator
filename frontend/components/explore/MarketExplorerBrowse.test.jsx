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
const directory = [...eras, ...sets, ...quick];
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
    assert.equal(selected.at(-1), "curated:intermediate");
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
