// MultiSelectFilter — the one inDex multi-select control.
//
// These tests pin the behaviour that separates this control from the native
// `<select multiple>` it replaced: a compact closed summary rather than a wall
// of names, an EMPTY selection that reads as ALL, disabled options that cannot
// be selected, client-side search over the list already loaded, keyboard
// operation, and accessible semantics that state the selection in text rather
// than in colour.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MultiSelectFilter, { CHIP_LIMIT, filterOptions, summarizeSelection } from "./MultiSelectFilter.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const OPTIONS = [
  { id: "sv", label: "Scarlet & Violet" },
  { id: "swsh", label: "Sword & Shield" },
  { id: "sm", label: "Sun & Moon" },
  { id: "legacy", label: "Legacy Era", disabled: true },
];

/** Render the control and return the tree plus the selection it last emitted. */
function mount(overrides = {}) {
  const emitted = [];
  let renderer;
  act(() => {
    renderer = TestRenderer.create(
      <MultiSelectFilter
        label="Era"
        name="era"
        options={OPTIONS}
        selectedIds={[]}
        allLabel="All Eras"
        summaryNoun="Eras"
        searchable={false}
        onChange={(next) => emitted.push(next)}
        {...overrides}
      />
    );
  });
  return { renderer, emitted };
}

const byProp = (renderer, prop) => renderer.root.findAll((node) => node.props?.[prop] !== undefined);
const trigger = (renderer) => renderer.root.find((node) => node.props?.["data-multi-select-trigger"] !== undefined);
const openControl = (renderer) => act(() => { trigger(renderer).props.onClick(); });
const optionNodes = (renderer) => byProp(renderer, "data-multi-select-option");
const summaryText = (renderer) =>
  renderer.root.find((node) => node.props?.["data-multi-select-summary"] !== undefined).props.children;

test("the closed control summarizes rather than listing every name", () => {
  assert.equal(summarizeSelection({ selectedIds: [], options: OPTIONS, allLabel: "All Eras", summaryNoun: "Eras" }), "All Eras");
  assert.equal(summarizeSelection({ selectedIds: ["sv"], options: OPTIONS, allLabel: "All Eras", summaryNoun: "Eras" }), "Scarlet & Violet");
  assert.equal(
    summarizeSelection({ selectedIds: ["sv", "swsh", "sm"], options: OPTIONS, allLabel: "All Eras", summaryNoun: "Eras" }),
    "3 Eras selected",
  );
});

test("an empty selection reads as ALL, never as nothing", () => {
  const { renderer } = mount();
  assert.equal(summaryText(renderer), "All Eras");
  assert.equal(trigger(renderer).props["data-multi-select-count"], 0);
});

test("the popover is closed on the first render, so SSR and hydration agree", () => {
  const { renderer } = mount();
  assert.equal(trigger(renderer).props["aria-expanded"], false);
  assert.equal(trigger(renderer).props["aria-controls"], undefined);
  assert.equal(optionNodes(renderer).length, 0, "no listbox exists until the user opens one");
});

test("opening exposes a multi-selectable listbox with accessible semantics", () => {
  const { renderer } = mount();
  openControl(renderer);
  assert.equal(trigger(renderer).props["aria-expanded"], true);
  assert.equal(trigger(renderer).props["aria-haspopup"], "listbox");
  const listbox = renderer.root.find((node) => node.props?.role === "listbox");
  assert.equal(listbox.props["aria-multiselectable"], "true");
  assert.equal(listbox.props.id, trigger(renderer).props["aria-controls"]);
  assert.equal(optionNodes(renderer).length, OPTIONS.length);
});

test("the selected state is stated in text, not carried by colour alone", () => {
  const { renderer } = mount({ selectedIds: ["sv", "swsh"] });
  const spoken = renderer.root.findAll((node) => node.props?.className === "sr-only")
    .map((node) => node.props.children).flat().join(" ");
  assert.match(String(spoken), /2 of 4 selected/);
  openControl(renderer);
  const option = optionNodes(renderer).find((node) => node.props["data-multi-select-option"] === "sv");
  assert.equal(option.props["aria-selected"], true);
  assert.equal(option.props["data-multi-select-option-selected"], "true");
});

test("selecting adds, selecting again removes, and the emitted list is canonical", () => {
  const { renderer, emitted } = mount({ selectedIds: ["swsh"] });
  openControl(renderer);
  const pick = (id) => act(() => {
    optionNodes(renderer).find((node) => node.props["data-multi-select-option"] === id).props.onClick();
  });
  pick("sv");
  assert.deepEqual(emitted.at(-1), ["sv", "swsh"], "the emitted selection is sorted, so one selection is one spec");
  pick("swsh");
  assert.deepEqual(emitted.at(-1), [], "selecting a selected option removes it");
});

test("a disabled option cannot be selected", () => {
  const { renderer, emitted } = mount();
  openControl(renderer);
  const legacy = optionNodes(renderer).find((node) => node.props["data-multi-select-option"] === "legacy");
  assert.equal(legacy.props["aria-disabled"], "true");
  act(() => { legacy.props.onClick(); });
  assert.equal(emitted.length, 0, "a disabled option emits no change");
});

test("the All action clears back to the empty-means-all state", () => {
  const { renderer, emitted } = mount({ selectedIds: ["sv", "swsh"] });
  openControl(renderer);
  act(() => {
    renderer.root.find((node) => node.props?.["data-multi-select-clear"] !== undefined).props.onClick();
  });
  assert.deepEqual(emitted.at(-1), []);
});

test("search filters the loaded list client-side and issues no request", () => {
  assert.deepEqual(filterOptions(OPTIONS, "sword").map((entry) => entry.id), ["swsh"]);
  assert.deepEqual(filterOptions(OPTIONS, "  SCARLET ").map((entry) => entry.id), ["sv"]);
  assert.equal(filterOptions(OPTIONS, "").length, OPTIONS.length, "an empty term is not a filter");

  const { renderer } = mount({ searchable: true });
  openControl(renderer);
  const search = renderer.root.find((node) => node.props?.["data-multi-select-search"] !== undefined);
  act(() => { search.props.onChange({ target: { value: "sun" } }); });
  assert.deepEqual(optionNodes(renderer).map((node) => node.props["data-multi-select-option"]), ["sm"]);
  assert.equal(renderer.root.findAll((node) => node.props?.["data-multi-select-empty"] !== undefined).length, 0);
});

test("a search with no matches says so instead of rendering an empty box", () => {
  const { renderer } = mount({ searchable: true });
  openControl(renderer);
  act(() => {
    renderer.root.find((node) => node.props?.["data-multi-select-search"] !== undefined)
      .props.onChange({ target: { value: "zzzz" } });
  });
  assert.equal(renderer.root.findAll((node) => node.props?.["data-multi-select-empty"] !== undefined).length, 1);
});

test("Enter and Space toggle an option from the keyboard", () => {
  for (const key of ["Enter", " "]) {
    const { renderer, emitted } = mount();
    openControl(renderer);
    const option = optionNodes(renderer).find((node) => node.props["data-multi-select-option"] === "sm");
    act(() => { option.props.onKeyDown({ key, preventDefault() {} }); });
    assert.deepEqual(emitted.at(-1), ["sm"], `${key} must toggle the focused option`);
  }
});

test("Escape closes the popover", () => {
  const { renderer } = mount();
  openControl(renderer);
  const popover = renderer.root.find((node) => node.props?.["data-multi-select-popover"] !== undefined);
  act(() => { popover.props.onKeyDown({ key: "Escape", preventDefault() {}, stopPropagation() {} }); });
  assert.equal(trigger(renderer).props["aria-expanded"], false);
  assert.equal(optionNodes(renderer).length, 0);
});

test("closing does not discard the selection", () => {
  const { renderer } = mount({ selectedIds: ["sv", "swsh"], onChange: () => {} });
  openControl(renderer);
  const popover = renderer.root.find((node) => node.props?.["data-multi-select-popover"] !== undefined);
  act(() => { popover.props.onKeyDown({ key: "Escape", preventDefault() {}, stopPropagation() {} }); });
  assert.equal(summaryText(renderer), "2 Eras selected");
});

test("chips stay a clarity aid and never become a cloud", () => {
  const many = Array.from({ length: CHIP_LIMIT + 1 }, (_, index) => ({ id: `s${index}`, label: `Set ${index}` }));
  const few = mount({ options: many, selectedIds: ["s0", "s1"] });
  assert.equal(few.renderer.root.findAll((node) => node.props?.["data-multi-select-chip"] !== undefined).length, 2);

  const flood = mount({ options: many, selectedIds: many.map((entry) => entry.id) });
  assert.equal(
    flood.renderer.root.findAll((node) => node.props?.["data-multi-select-chips"] !== undefined).length,
    0,
    "past the chip limit the closed summary is the readable statement",
  );
});

test("removing a chip deselects exactly that option", () => {
  const { renderer, emitted } = mount({ selectedIds: ["sv", "swsh"] });
  act(() => {
    renderer.root.find((node) => node.props?.["data-multi-select-chip"] === "sv").props.onClick();
  });
  assert.deepEqual(emitted.at(-1), ["swsh"]);
});

test("mobile density: every interactive row clears a 44px tap target", () => {
  const { renderer } = mount();
  assert.match(trigger(renderer).props.className, /min-h-11/);
  openControl(renderer);
  for (const option of optionNodes(renderer)) {
    assert.match(option.props.className, /min-h-11/);
  }
});

test("the popover is a fixed-position surface, so glass panels cannot trap it", () => {
  const { renderer } = mount();
  openControl(renderer);
  const popover = renderer.root.find((node) => node.props?.["data-multi-select-popover"] !== undefined);
  assert.match(popover.props.className, /fixed/);
});
