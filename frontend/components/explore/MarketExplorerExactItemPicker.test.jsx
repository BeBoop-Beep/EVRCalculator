import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketExplorerExactItemPicker, { exactItemLabel } from "./MarketExplorerExactItemPicker.jsx";

test("physical labels distinguish card and product variants", () => {
  assert.match(exactItemLabel({ asset: "cards", name: "Charizard", setName: "Base Set", cardNumber: "4", rarity: "Rare Holo", edition: "1st Edition", printingType: "Holo" }), /Base Set · #4 · Rare Holo · 1st Edition · Holo/);
  assert.equal(exactItemLabel({ asset: "sealed", name: "Elite Trainer Box", setName: "151", productFamily: "ETB", variantLabel: "Pokémon Center" }), "Elite Trainer Box · 151 · ETB · Pokémon Center");
});

test("selection rejects duplicates and explains the 25-item ceiling", async () => {
  const selected = Array.from({ length: 25 }, (_, index) => ({ asset: "cards", instrumentId: `v${index}`, name: `Card ${index}` }));
  let changed = false;
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerExactItemPicker selectedItems={selected} onChange={() => { changed = true; }} />); });
  assert.match(renderer.root.findByProps({ role: "status" }).children.join(""), /25 \/ 25 selected/);
  assert.equal(changed, false);
});

test("top close preserves selection while Cancel Edits is distinct", async () => {
  const selected = [{ asset: "cards", instrumentId: "v1", name: "Charizard", edition: "Unlimited" }];
  const calls = [];
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerExactItemPicker selectedItems={selected} onChange={() => calls.push("change")} onClose={() => calls.push("close")} onCancelEdit={() => calls.push("cancel-edit")} />); });
  await act(async () => { renderer.root.findByProps({ "aria-label": "Close Build Your Market" }).props.onClick(); });
  assert.deepEqual(calls, ["close"]);
  assert.equal(renderer.root.findByProps({ "data-exact-selected-items": true }).children.length, 1);
  await act(async () => { renderer.root.findAllByType("button").find((node) => node.children.includes("Cancel Edits")).props.onClick(); });
  assert.deepEqual(calls, ["close", "cancel-edit"]);
});

test("execution lock leaves selection removable and locks only execution", async () => {
  const item = { asset: "sealed", instrumentId: "sealed-1", name: "Elite Trainer Box", productFamily: "ETB" };
  let selected = [];
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerExactItemPicker selectedItems={[item]} executionLocked onChange={(items) => { selected = items; }} onBuild={() => {}} />); });
  const build = renderer.root.findAllByType("button").find((node) => String(node.children.join(" ")).includes("Requires Index Premium"));
  assert.equal(build.props.disabled, false);
  await act(async () => renderer.root.findByProps({ "aria-label": `Remove ${exactItemLabel(item)}` }).props.onClick());
  assert.deepEqual(selected, []);
});

test("search is debounced and Products maps to sealed", async () => {
  const originalFetch = global.fetch;
  const calls = [];
  global.fetch = async (url) => { calls.push(url); return { ok: true, json: async () => ({ items: [] }) }; };
  try {
    let renderer;
    await act(async () => { renderer = TestRenderer.create(<MarketExplorerExactItemPicker selectedItems={[]} onChange={() => {}} />); });
    await act(async () => { renderer.root.findAllByProps({ role: "tab" }).find((node) => node.children.includes("Products")).props.onClick(); });
    const input = renderer.root.findByType("input");
    await act(async () => { input.props.onChange({ target: { value: "c" } }); });
    await new Promise((resolve) => setTimeout(resolve, 330));
    assert.equal(calls.length, 0);
    await act(async () => { input.props.onChange({ target: { value: "etb" } }); });
    await new Promise((resolve) => setTimeout(resolve, 350));
    assert.equal(calls.length, 1);
    assert.match(calls[0], /asset=sealed/);
    renderer.unmount();
  } finally { global.fetch = originalFetch; }
});
