// Era & Sets, rendered — and the reusable disclosure it sits inside.
//
// Two behaviours matter here and are easy to get wrong:
//   1. selecting an era and expanding it are SEPARATE controls, so neither
//      click does the other's job;
//   2. the group is a real, accessible disclosure that starts collapsed.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerEraSets from "./MarketExplorerEraSets.jsx";
import ExplorerDisclosure from "./ExplorerDisclosure.jsx";
import { buildEraSetTree } from "@/lib/explore/marketExplorerScope.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const OPTIONS = {
  eras: [
    { id: "era-sv", label: "Scarlet & Violet", sortOrder: 3 },
    { id: "era-swsh", label: "Sword & Shield", sortOrder: 2 },
  ],
  sets: [
    { id: "set-ah", label: "Ascended Heroes", eraId: "era-sv", assets: ["cards"] },
    { id: "set-evo", label: "Evolving Skies", eraId: "era-swsh", assets: ["cards"] },
    { id: "set-lor", label: "Lost Origin", eraId: "era-swsh", assets: ["cards"] },
  ],
};

function mount({ scope = { eraIds: [], setIds: [] }, status = "ready", onToggleEra, onToggleSet } = {}) {
  const tree = buildEraSetTree(OPTIONS, { eraIds: scope.eraIds, setIds: scope.setIds });
  let renderer;
  act(() => {
    renderer = TestRenderer.create(
      <MarketExplorerEraSets
        tree={tree}
        scope={scope}
        status={status}
        onToggleEra={onToggleEra}
        onToggleSet={onToggleSet}
      />
    );
  });
  return renderer;
}

const findAll = (renderer, prop) =>
  renderer.root.findAll((node) => node.props?.[prop] !== undefined, { deep: true });
const find = (renderer, prop, value) =>
  renderer.root.findAll((node) => node.props?.[prop] === value, { deep: true })[0] || null;

function textOf(node) {
  if (node === null || node === undefined || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  return (node.children || []).map(textOf).filter(Boolean).join(" ");
}
const pageText = (renderer) => textOf(renderer.toJSON());

test("eras render by their canonical names, with no Legacy bucket", () => {
  const text = pageText(mount());
  assert.ok(text.includes("Sword & Shield"));
  assert.ok(text.includes("Scarlet & Violet"));
  assert.ok(!text.includes("Legacy"));
});

test("sets stay collapsed until their era is expanded", () => {
  const renderer = mount();
  // Nothing but the era rows on first render — not every tracked set at once,
  // which is what keeps this usable at 390px.
  assert.equal(findAll(renderer, "data-explorer-set-option").length, 0);
  assert.equal(findAll(renderer, "data-explorer-era-row").length, 2);

  act(() => { find(renderer, "data-explorer-era-expand", "era-swsh").props.onClick(); });
  assert.deepEqual(
    findAll(renderer, "data-explorer-set-option").map((node) => node.props["data-explorer-set-option"]),
    ["set-evo", "set-lor"]
  );
});

test("expanding an era does NOT select it", () => {
  const selected = [];
  const renderer = mount({ onToggleEra: (id) => selected.push(id) });
  act(() => { find(renderer, "data-explorer-era-expand", "era-swsh").props.onClick(); });
  assert.deepEqual(selected, [], "the chevron is not a checkbox");
  assert.equal(find(renderer, "data-explorer-era-row", "era-swsh").props["data-explorer-era-selected"], "false");
});

test("selecting an era does NOT force its set list open", () => {
  const selected = [];
  const renderer = mount({ onToggleEra: (id) => selected.push(id) });
  const option = find(renderer, "data-explorer-era-option", "era-swsh");
  act(() => { option.findAll((node) => node.type === "input", { deep: true })[0].props.onChange(); });
  assert.deepEqual(selected, ["era-swsh"]);
  assert.equal(findAll(renderer, "data-explorer-set-option").length, 0);
});

test("a child set is selectable on its own", () => {
  const chosen = [];
  const renderer = mount({ scope: { eraIds: ["era-swsh"], setIds: [] }, onToggleSet: (id) => chosen.push(id) });
  act(() => { find(renderer, "data-explorer-era-expand", "era-swsh").props.onClick(); });
  const row = find(renderer, "data-explorer-set-option", "set-lor");
  act(() => { row.findAll((node) => node.type === "input", { deep: true })[0].props.onChange(); });
  assert.deepEqual(chosen, ["set-lor"]);
});

test("the expand control is an accessible button, not a bare span", () => {
  const renderer = mount();
  const expand = find(renderer, "data-explorer-era-expand", "era-sv");
  assert.equal(expand.type, "button");
  assert.equal(expand.props["aria-expanded"], false);
  assert.ok(String(expand.props["aria-controls"]).length > 0);
});

test("a scope is stated as a scope, never as a line on the chart", () => {
  const text = pageText(mount());
  assert.ok(text.includes("scope"));
  assert.ok(text.includes("No standalone"));
  // The hand-off to the builder appears only once something is scoped.
  assert.equal(pageText(mount()).includes("Use in Build a Market"), false);
  const scoped = mount({ scope: { eraIds: ["era-swsh"], setIds: [] } });
  assert.ok(pageText(scoped).includes("Use in Build a Market"));
});

test("a signed-out or failed options load says so instead of showing an empty tree", () => {
  assert.ok(pageText(mount({ status: "signedOut" })).includes("Sign in to browse eras and sets"));
  assert.ok(pageText(mount({ status: "loading" })).includes("Loading canonical eras and sets"));
  assert.ok(pageText(mount({ status: "unavailable" })).includes("temporarily unavailable"));
});

// --- the reusable disclosure ----------------------------------------------

function mountDisclosure(props = {}) {
  let renderer;
  act(() => {
    renderer = TestRenderer.create(
      <ExplorerDisclosure id="demo" title="Demo Group" {...props}>
        <p data-demo-body>body</p>
      </ExplorerDisclosure>
    );
  });
  return renderer;
}

test("a disclosure starts collapsed and renders nothing underneath it", () => {
  const renderer = mountDisclosure();
  assert.equal(find(renderer, "data-explorer-disclosure", "demo").props["data-explorer-disclosure-open"], "false");
  assert.equal(findAll(renderer, "data-demo-body").length, 0);
});

test("a disclosure header is a keyboard-operable button that announces its state", () => {
  const renderer = mountDisclosure();
  const toggle = find(renderer, "data-explorer-disclosure-toggle", "demo");
  assert.equal(toggle.type, "button");
  assert.equal(toggle.props["aria-expanded"], false);

  act(() => { toggle.props.onClick(); });
  assert.equal(find(renderer, "data-explorer-disclosure-toggle", "demo").props["aria-expanded"], true);
  assert.equal(findAll(renderer, "data-demo-body").length, 1);
});

test("openSignal opens a group but can never close one the user opened", () => {
  let renderer;
  act(() => {
    renderer = TestRenderer.create(
      <ExplorerDisclosure id="demo" title="Demo Group" openSignal={null}>
        <p data-demo-body>body</p>
      </ExplorerDisclosure>
    );
  });
  assert.equal(findAll(renderer, "data-demo-body").length, 0);

  act(() => {
    renderer.update(
      <ExplorerDisclosure id="demo" title="Demo Group" openSignal={1}>
        <p data-demo-body>body</p>
      </ExplorerDisclosure>
    );
  });
  assert.equal(findAll(renderer, "data-demo-body").length, 1);

  // Reverting the signal must not slam the panel shut under the user.
  act(() => {
    renderer.update(
      <ExplorerDisclosure id="demo" title="Demo Group" openSignal={null}>
        <p data-demo-body>body</p>
      </ExplorerDisclosure>
    );
  });
  assert.equal(findAll(renderer, "data-demo-body").length, 1);
});
