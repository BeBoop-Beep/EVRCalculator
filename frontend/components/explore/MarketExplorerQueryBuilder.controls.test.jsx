// The query builder's three filter axes, rendered.
//
// The source-text contract test next to this one pins WHAT the builder is
// allowed to offer. This one pins how the replaced native controls BEHAVE:
// canonical ordering that does not depend on payload arrival order, sets that
// narrow to the selected eras and reconcile when they no longer can, backend
// rarity options kept distinct between the modern and the legacy market, and a
// query preview that follows the controls.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerQueryBuilder from "./MarketExplorerQueryBuilder.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Deliberately shuffled: eras arrive out of sortOrder and sets out of name
// order, so a test that passes could only pass because the builder sorts.
const OPTIONS_PAYLOAD = {
  asset: { id: "cards", label: "Cards" },
  eras: [
    { id: "era-swsh", label: "Sword & Shield", sortOrder: 2 },
    { id: "era-sv", label: "Scarlet & Violet", sortOrder: 3 },
    { id: "era-sm", label: "Sun & Moon", sortOrder: 1 },
  ],
  sets: [
    { id: "set-twm", label: "Twilight Masquerade", eraId: "era-sv", releaseDate: "2024-05-24" },
    { id: "set-ah", label: "Ascended Heroes", eraId: "era-sv", releaseDate: "2025-08-01" },
    { id: "set-evo", label: "Evolving Skies", eraId: "era-swsh", releaseDate: "2021-08-27" },
    { id: "set-bur", label: "Burning Shadows", eraId: "era-sm", releaseDate: "2017-08-04" },
  ],
  segments: {
    segments: [
      { key: "special_illustration_rare", label: "Special Illustration Rare", definition: "Modern SIR." },
      { key: "illustration_rare", label: "Illustration Rare", definition: "Modern IR." },
      { key: "ultra_rare", label: "Ultra Rare", definition: "Modern UR." },
      { key: "hyper_rare", label: "Hyper Rare", definition: "Modern HR." },
      { key: "double_rare", label: "Double Rare", definition: "Modern DR." },
      { key: "rare_ultra", label: "Rare Ultra", definition: "Legacy Rare Ultra." },
      { key: "rare_secret", label: "Rare Secret", definition: "Legacy Rare Secret." },
      { key: "rare_rainbow", label: "Rare Rainbow", definition: "Legacy Rare Rainbow." },
      { key: "rare_holo", label: "Rare Holo", definition: "Legacy Rare Holo." },
    ],
  },
};

async function mountBuilder({ onAddQuery = async () => "added", payload = OPTIONS_PAYLOAD } = {}) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => payload });
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(<MarketExplorerQueryBuilder onAddQuery={onAddQuery} />);
  });
  globalThis.fetch = originalFetch;
  return renderer;
}

const control = (renderer, name) =>
  renderer.root.find((node) => node.props?.["data-multi-select-trigger"] === name);
const summaryOf = (renderer, name) =>
  renderer.root.find((node) => node.props?.["data-multi-select-summary"] === name).props.children;
const optionIds = (renderer) =>
  renderer.root.findAll((node) => node.props?.["data-multi-select-option"] !== undefined)
    .map((node) => node.props["data-multi-select-option"]);
const optionLabels = (renderer) =>
  renderer.root.findAll((node) => node.props?.["data-multi-select-option"] !== undefined)
    .map((node) => node.props.children.find((child) => child?.props?.className?.includes?.("flex-1"))?.props?.children?.[0]?.props?.children);
const open = (renderer, name) => act(() => { control(renderer, name).props.onClick(); });
const close = (renderer, name) => act(() => { control(renderer, name).props.onClick(); });
const pick = (renderer, id) => act(() => {
  renderer.root.find((node) => node.props?.["data-multi-select-option"] === id).props.onClick();
});
const preview = (renderer) =>
  renderer.root.find((node) => node.props?.["data-market-query-preview"] !== undefined).props.children;

// -- Era ---------------------------------------------------------------------

test("Era: no native select survives anywhere in the builder", async () => {
  const renderer = await mountBuilder();
  assert.equal(renderer.root.findAll((node) => node.type === "select").length, 0,
    "an OS-painted control on a dark research workspace is the defect this phase removed");
});

test("Era: unset reads All Eras, one reads its name, many read a count", async () => {
  const renderer = await mountBuilder();
  assert.equal(summaryOf(renderer, "era"), "All Eras");
  open(renderer, "era");
  pick(renderer, "era-sv");
  assert.equal(summaryOf(renderer, "era"), "Scarlet & Violet");
  pick(renderer, "era-swsh");
  assert.equal(summaryOf(renderer, "era"), "2 Eras selected");
});

test("Era: options are ordered canonically, not by payload arrival order", async () => {
  const renderer = await mountBuilder();
  open(renderer, "era");
  assert.deepEqual(optionIds(renderer), ["era-sm", "era-swsh", "era-sv"],
    "sortOrder is the canonical order; the payload deliberately arrives shuffled");
});

// -- Set ---------------------------------------------------------------------

test("Set: unset reads All Sets and the list is alphabetical", async () => {
  const renderer = await mountBuilder();
  assert.equal(summaryOf(renderer, "set"), "All Sets");
  open(renderer, "set");
  assert.deepEqual(optionIds(renderer), ["set-ah", "set-bur", "set-evo", "set-twm"]);
});

test("Set: the list narrows to the selected eras", async () => {
  const renderer = await mountBuilder();
  open(renderer, "era");
  pick(renderer, "era-sv");
  close(renderer, "era");
  open(renderer, "set");
  assert.deepEqual(optionIds(renderer), ["set-ah", "set-twm"]);
});

test("Set: an era change reconciles away a set that is no longer possible", async () => {
  const renderer = await mountBuilder();
  open(renderer, "set");
  pick(renderer, "set-evo");
  assert.equal(summaryOf(renderer, "set"), "Evolving Skies");
  close(renderer, "set");

  await act(async () => { control(renderer, "era").props.onClick(); });
  pick(renderer, "era-sv");
  assert.equal(summaryOf(renderer, "set"), "All Sets",
    "a Sword & Shield set cannot stay selected under a Scarlet & Violet filter");
  assert.ok(!String(preview(renderer)).includes("Evolving Skies"),
    "and it must not survive in the query spec either");
});

test("Set: search filters the loaded list without a request per keystroke", async () => {
  const renderer = await mountBuilder();
  open(renderer, "set");
  const originalFetch = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = async () => { requests += 1; return { ok: true, json: async () => OPTIONS_PAYLOAD }; };
  act(() => {
    renderer.root.find((node) => node.props?.["data-multi-select-search"] === "set")
      .props.onChange({ target: { value: "asc" } });
  });
  globalThis.fetch = originalFetch;
  assert.deepEqual(optionIds(renderer), ["set-ah"]);
  assert.equal(requests, 0, "search is client-side over the canonical list already loaded");
});

test("Set: multi-select accumulates", async () => {
  const renderer = await mountBuilder();
  open(renderer, "set");
  pick(renderer, "set-ah");
  pick(renderer, "set-twm");
  assert.equal(summaryOf(renderer, "set"), "2 Sets selected");
});

// -- Card Segment / Rarity ---------------------------------------------------

test("Rarity: every published segment is offered, modern and legacy kept distinct", async () => {
  const renderer = await mountBuilder();
  open(renderer, "segment");
  assert.deepEqual(optionLabels(renderer), [
    "Special Illustration Rare", "Illustration Rare", "Ultra Rare", "Hyper Rare", "Double Rare",
    "Rare Ultra", "Rare Secret", "Rare Rainbow", "Rare Holo",
  ], "legacy rarity names are their own markets and must never be folded into the modern ones");
});

test("Rarity: options come only from the payload", async () => {
  const renderer = await mountBuilder({ payload: { ...OPTIONS_PAYLOAD, segments: { segments: [] } } });
  assert.equal(summaryOf(renderer, "segment"), "All Rarities");
  open(renderer, "segment");
  assert.equal(renderer.root.findAll((node) => node.props?.["data-multi-select-empty"] === "segment").length, 1,
    "an unpublished taxonomy yields no options, never a client-invented list");
});

test("Rarity: the published definition stays visible on the option", async () => {
  const renderer = await mountBuilder();
  open(renderer, "segment");
  const described = renderer.root.findAll(
    (node) => node.props?.["data-multi-select-option-description"] !== undefined
  );
  assert.equal(described.length, 9);
  assert.equal(described[0].props.children, "Modern SIR.");
});

test("Rarity: single and multi selection both summarize compactly", async () => {
  const renderer = await mountBuilder();
  open(renderer, "segment");
  pick(renderer, "special_illustration_rare");
  assert.equal(summaryOf(renderer, "segment"), "Special Illustration Rare");
  pick(renderer, "illustration_rare");
  pick(renderer, "rare_ultra");
  assert.equal(summaryOf(renderer, "segment"), "3 segments selected");
});

// -- Preview and add ---------------------------------------------------------

test("the query preview follows the custom controls", async () => {
  const renderer = await mountBuilder();
  assert.equal(preview(renderer), "Global · All rarities · All");
  open(renderer, "segment");
  pick(renderer, "special_illustration_rare");
  close(renderer, "segment");
  assert.equal(preview(renderer), "Global · Special Illustration Rare · All");
  open(renderer, "era");
  pick(renderer, "era-sv");
  close(renderer, "era");
  assert.equal(preview(renderer), "Scarlet & Violet · Special Illustration Rare · All");
});

test("Add to Comparison still travels as the normalized spec", async () => {
  const specs = [];
  const renderer = await mountBuilder({ onAddQuery: async (spec) => { specs.push(spec); return "added"; } });
  open(renderer, "segment");
  pick(renderer, "illustration_rare");
  close(renderer, "segment");
  await act(async () => {
    await renderer.root.find((node) => node.props?.["data-market-query-add"] !== undefined).props.onClick();
  });
  assert.equal(specs.length, 1);
  assert.deepEqual(specs[0].segmentIds, ["illustration_rare"]);
  assert.equal(specs[0].mode, "all");
  assert.equal(specs[0].topN, null);
});
