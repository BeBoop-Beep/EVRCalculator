import test from "node:test";
import assert from "node:assert/strict";
import React, { act } from "react";
import TestRenderer from "react-test-renderer";

import PokemonSetMobileHero from "./PokemonSetMobileHero.jsx";
import { selectMobileHeroModel } from "./mobileHeroModel.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// The page passes identity only. Set Value and RIP are deliberately absent from
// the mobile header — they live in Set Value Trend and Decision Signals — so the
// model is fed the full payload here to prove the hero renders none of it.
const model = selectMobileHeroModel({
  setName: "Scarlet & Violet—Journey Together",
  era: "Scarlet & Violet",
  logoUrl: "https://images.example/logo.png",
  setValue: { current: 663.14, deltaAmount: -115.78, deltaPercent: -14.9, windowLabel: "30D" },
  rip: { label: "RIP Score", score: 100, tier: "S", rank: 1, cohortSize: 212, verdict: "Elite, some path risk" },
});

async function renderHero(overrides = {}) {
  const calls = { toggle: 0, select: 0 };
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(
      <PokemonSetMobileHero
        model={model}
        pickerOpen={false}
        onTogglePicker={() => { calls.toggle += 1; }}
        onSelectTarget={() => { calls.select += 1; }}
        onPickerKeyDown={() => {}}
        targets={[{ target_type: "set", target_id: "perfectOrder", name: "Perfect Order" }]}
        selectedTargetId="perfectOrder"
        pickerDisabled={false}
        listboxId="set-mobile-picker-list"
        {...overrides}
      />
    );
  });
  return { renderer, calls };
}

function textOf(instance) {
  const parts = [];
  const walk = (node) => {
    if (node === null || node === undefined || node === false) return;
    if (typeof node === "string" || typeof node === "number") {
      parts.push(String(node));
      return;
    }
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (node.children) node.children.forEach(walk);
  };
  walk(instance.children);
  return parts.join(" ");
}

test("the mobile header is identity only", async () => {
  const { renderer } = await renderHero();
  const section = renderer.root.findByProps({ "data-set-mobile-hero": true });
  const regions = section.findAll((node) => typeof node.props["data-hero-region"] === "string");
  assert.deepEqual(regions.map((node) => node.props["data-hero-region"]), ["identity"]);
});

test("identity still shows logo, name and era", async () => {
  const { renderer } = await renderHero();
  const identity = renderer.root.findByProps({ "data-hero-region": "identity" });
  const text = textOf(identity);
  assert.ok(text.includes("Scarlet & Violet—Journey Together"), "the long set name renders in full");
  assert.ok(text.includes("Scarlet & Violet"), "the era renders");
  assert.equal(renderer.root.findAllByType("img").length, 1, "the logo renders");
});

test("Set Value is not rendered in the mobile header", async () => {
  const { renderer } = await renderHero();
  const json = JSON.stringify(renderer.toJSON());
  assert.ok(!json.includes("$663.14"), "the set value figure must not appear");
  assert.ok(!json.includes("115.78"), "the set value movement must not appear");
  assert.ok(!/Set Value/i.test(json), "the Set Value label must not appear");
  assert.equal(renderer.root.findAllByProps({ "data-hero-region": "value" }).length, 0);
});

test("RIP is not rendered in the mobile header", async () => {
  const { renderer } = await renderHero();
  const json = JSON.stringify(renderer.toJSON());
  assert.ok(!/RIP Score/i.test(json), "the RIP label must not appear");
  assert.ok(!json.includes("S Tier"), "the RIP tier must not appear");
  assert.ok(!json.includes("Rank #1"), "the RIP rank must not appear");
  assert.ok(!json.includes("Elite, some path risk"), "the RIP verdict must not appear");
  assert.equal(renderer.root.findAllByProps({ "data-hero-region": "rip" }).length, 0);
});

test("no activation rows survive in the mobile header", async () => {
  const { renderer } = await renderHero();
  const json = JSON.stringify(renderer.toJSON());
  assert.ok(!json.includes("View trend"));
  assert.ok(!json.includes("View verdict"));
  // The only control left is the set picker.
  const buttons = renderer.root.findAllByType("button");
  assert.equal(buttons.length, 1, "the picker trigger is the only control in the header");
  assert.equal(buttons[0].props["data-set-mobile-picker"], true);
});

test("a missing logo degrades to the name alone", async () => {
  const bare = selectMobileHeroModel({ setName: "Perfect Order", era: null, logoUrl: null });
  const { renderer } = await renderHero({ model: bare });
  assert.equal(renderer.root.findAllByType("img").length, 0);
  assert.ok(textOf(renderer.root.findByProps({ "data-hero-region": "identity" })).includes("Perfect Order"));
});

test("the header renders when there is no data at all", async () => {
  const empty = selectMobileHeroModel({});
  const { renderer } = await renderHero({ model: empty });
  assert.ok(textOf(renderer.root.findByProps({ "data-hero-region": "identity" })).includes("Selected Set"));
});

test("the set picker is reachable and announces its state", async () => {
  const { renderer, calls } = await renderHero();
  const picker = renderer.root.findByProps({ "data-set-mobile-picker": true });
  assert.equal(picker.props["aria-haspopup"], "listbox");
  assert.equal(picker.props["aria-expanded"], false);
  assert.equal(picker.props["aria-controls"], "set-mobile-picker-list");
  await act(async () => picker.props.onClick());
  assert.equal(calls.toggle, 1);
});

test("clicking the full identity row opens the picker", async () => {
  const { renderer, calls } = await renderHero();
  const identityRow = renderer.root.findByProps({ "data-testid": "mobile-hero-identity-row" });
  await act(async () => identityRow.props.onClick());
  assert.equal(calls.toggle, 1);
});

test("the identity row is rendered as a single semantic button", async () => {
  const { renderer } = await renderHero();
  const identityRow = renderer.root.findByProps({ "data-testid": "mobile-hero-identity-row" });
  assert.equal(identityRow.type, "button", "the hero row should be a real button element");
  assert.equal(identityRow.props.role, undefined, "the row should not fake a button with role=button");
  assert.equal(identityRow.findAllByType("button").length, 1, "the identity row should not contain a nested chevron button");
});

// --- Correction 2: exactly one interactive picker owner --------------------

test("the owning composition mounts the listbox and is keyboard reachable", async () => {
  const { renderer } = await renderHero({ isPickerOwner: true, pickerOpen: true });
  const picker = renderer.root.findByProps({ "data-set-mobile-picker": true });
  assert.equal(picker.props.tabIndex, 0, "the owner is in the tab order");
  assert.equal(picker.props["aria-hidden"], undefined, "the owner is exposed to assistive tech");
  assert.equal(picker.props["aria-expanded"], true);
  assert.equal(renderer.root.findAllByProps({ role: "listbox" }).length, 1, "the owner mounts exactly one listbox");
  assert.equal(picker.findAllByType("button").length, 1, "the picker trigger must not contain nested buttons when the listbox is open");
});

test("the non-owning composition mounts no listbox and is not focusable", async () => {
  const { renderer } = await renderHero({ isPickerOwner: false, pickerOpen: true });
  const picker = renderer.root.findByProps({ "data-set-mobile-picker": true });
  assert.equal(picker.props.tabIndex, -1, "the hidden composition is out of the tab order");
  assert.equal(picker.props["aria-hidden"], true, "the hidden composition is hidden from assistive tech");
  assert.equal(picker.props["aria-expanded"], false, "a non-owner never claims an open menu");
  assert.equal(renderer.root.findAllByProps({ role: "listbox" }).length, 0, "no second listbox may be mounted");
});

test("selecting a set from the listbox still works", async () => {
  const { renderer, calls } = await renderHero({ isPickerOwner: true, pickerOpen: true });
  const option = renderer.root.findByProps({ role: "option" });
  await act(async () => option.props.onClick());
  assert.equal(calls.select, 1);
});

test("the mobile listbox id can never collide with the desktop one", async () => {
  const { renderer } = await renderHero({ isPickerOwner: true, pickerOpen: true });
  const listbox = renderer.root.findByProps({ role: "listbox" });
  assert.equal(listbox.props.id, "set-mobile-picker-list");
  assert.notEqual(listbox.props.id, "compact-set-picker-list", "the desktop hero owns that id");
});
