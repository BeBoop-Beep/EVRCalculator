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

test("prepared categories populate, filter, switch, select, and preserve active feedback", async () => {
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
    assert.equal(rows(renderer)[0].props.children[0].props.children[0], "Global Top 10");
    await act(async () => rows(renderer)[0].props.onClick());
    assert.deepEqual(selected, ["curated:global-top10"]);
    assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 1);
    assert.equal(renderer.root.findByProps({ "data-market-browser-search": true }).props.value, "top");
    assert.equal(category(renderer, "quick").props["aria-expanded"], true);

    await act(async () => { renderer.update(<MarketExplorerBrowse {...props} activeKeys={["curated:global-top10"]} />); });
    assert.equal(rows(renderer).find((row) => row.props["data-prepared-market"] === "curated:global-top10").props["aria-pressed"], true);
    const keyboard = renderer.root.findByProps({ "data-market-browser-search": true });
    assert.equal(keyboard.props.value, "top");
    assert.equal(keyboard.props["aria-activedescendant"], undefined);
    let spacePrevented = false;
    await act(async () => keyboard.props.onKeyDown({ key: " ", preventDefault: () => { spacePrevented = true; } }));
    assert.equal(spacePrevented, false, "Space remains text input in the search field; focused row buttons use native Space activation");
    await act(async () => keyboard.props.onKeyDown({ key: "ArrowDown", preventDefault: noop }));
    assert.equal(rows(renderer)[0].props["data-search-highlighted"], "true");
    await act(async () => keyboard.props.onKeyDown({ key: "Enter", preventDefault: noop }));
    assert.equal(selected.at(-1), "curated:global-top10");
    assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 1);
    assert.equal(renderer.root.findByProps({ "data-market-browser-search": true }).props.value, "top");
    assert.equal(fetches, 0);
  } finally {
    globalThis.fetch = originalFetch;
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

test("selection and Compare keep the open category, filtered list, and list instance", async () => {
  const selected = [];
  const compared = [];
  let renderer;
  const props = { directory, activeKeys: [], canCompare: false,
    onSelect: (key) => selected.push(key), onCompare: (key) => compared.push(key), onBuild: noop };
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse {...props} />); });
  await act(async () => category(renderer, "sets").props.onClick());
  const search = renderer.root.findByProps({ "data-market-browser-search": true });
  await act(async () => search.props.onChange({ target: { value: "Set 08" } }));
  const list = renderer.root.findByProps({ role: "listbox" });
  const key = rows(renderer)[3].props["data-prepared-market"];
  await act(async () => rows(renderer)[3].props.onClick());
  assert.deepEqual(selected, [key]);
  assert.equal(category(renderer, "sets").props["aria-expanded"], true);
  assert.equal(renderer.root.findByProps({ "data-market-browser-search": true }).props.value, "Set 08");
  assert.equal(renderer.root.findByProps({ role: "listbox" }), list);
  await act(async () => { renderer.update(<MarketExplorerBrowse {...props} activeKeys={[key]} />); });
  assert.equal(renderer.root.findByProps({ role: "listbox" }), list);
  assert.equal(rows(renderer).find((row) => row.props["data-prepared-market"] === key).props["aria-pressed"], true);
  const compare = renderer.root.findByProps({ "data-compare-market": key });
  assert.match(JSON.stringify(compare.children), /Index\+/);
  await act(async () => compare.props.onClick());
  assert.deepEqual(compared, [key]);
  assert.equal(renderer.root.findByProps({ role: "listbox" }), list);
  assert.equal(renderer.root.findByProps({ "data-market-browser-search": true }).props.value, "Set 08");
  renderer.unmount();
});

test("Base Set 2 alone is active; opening does not highlight the first row", async () => {
  const baseDirectory = [
    { market_key: "set:first", market_type: "set", parent_era_id: "e0", label: "Another Set" },
    { market_key: "set:base", market_type: "set", parent_era_id: "e0", label: "Base Set" },
    { market_key: "set:base-2", market_type: "set", parent_era_id: "e0", label: "Base Set 2" },
  ];
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse directory={baseDirectory} activeKeys={["set:base-2"]} onSelect={noop} onCompare={noop} onBuild={noop} />); });
  await act(async () => category(renderer, "sets").props.onClick());
  const byKey = Object.fromEntries(rows(renderer).map((row) => [row.props["data-prepared-market"], row]));
  assert.equal(byKey["set:base-2"].props["aria-pressed"], true);
  assert.equal(byKey["set:base"].props["aria-pressed"], false);
  assert.equal(byKey["set:first"].props["aria-pressed"], false);
  assert.equal(byKey["set:first"].props["data-search-highlighted"], "false");
  assert.doesNotMatch(byKey["set:first"].parent.props.className, /bg-sky-400/);
  assert.equal(byKey["set:base-2"].parent.props["aria-selected"], true);
  assert.equal(byKey["set:base"].parent.props["aria-selected"], false);
  assert.equal(renderer.root.findByProps({ "data-market-browser-search": true }).props["aria-activedescendant"], undefined);
  await act(async () => renderer.root.findByProps({ "data-market-browser-search": true }).props.onKeyDown({ key: "ArrowDown", preventDefault: noop }));
  assert.equal(byKey["set:first"].props["data-search-highlighted"], "true");
  assert.equal(byKey["set:first"].props["aria-pressed"], false);
  renderer.unmount();
});

test("Era and Quick Market selections preserve their categories", async () => {
  const selected = [];
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse directory={directory} onSelect={(key) => selected.push(key)} onCompare={noop} onBuild={noop} />); });
  for (const id of ["eras", "quick"]) {
    await act(async () => category(renderer, id).props.onClick());
    const key = rows(renderer)[0].props["data-prepared-market"];
    await act(async () => rows(renderer)[0].props.onClick());
    assert.equal(selected.at(-1), key);
    assert.equal(category(renderer, id).props["aria-expanded"], true);
    assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 1);
  }
  await act(async () => renderer.unmount());
});

test("Escape restores trigger focus and outside click closes Browse", async () => {
  const originalDocument = globalThis.document;
  let outside;
  let focused = 0;
  globalThis.document = {
    addEventListener: (name, handler) => { if (name === "pointerdown") outside = handler; },
    removeEventListener: noop,
  };
  let renderer;
  try {
    await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse directory={directory} onSelect={noop} onCompare={noop} onBuild={noop} />,
      { createNodeMock: () => ({ focus: () => { focused += 1; }, contains: () => false }) }); });
    await act(async () => category(renderer, "eras").props.onClick());
    await act(async () => renderer.root.findByProps({ "data-market-browser-search": true }).props.onKeyDown({ key: "Escape", preventDefault: noop }));
    assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 0);
    assert.ok(focused >= 2);
    await act(async () => category(renderer, "quick").props.onClick());
    await act(async () => outside({ target: {} }));
    assert.equal(renderer.root.findAllByProps({ "data-market-directory-popover": true }).length, 0);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.document = originalDocument;
  }
});
