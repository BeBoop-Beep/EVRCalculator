// Era & Sets — the scope model.
//
// The thing this file exists to pin is that a scope is a NARROWING and never a
// market: it names eras and sets, reconciles impossible combinations, and
// carries no series, no index and no line.

import test from "node:test";
import assert from "node:assert/strict";

import {
  buildEraSetTree,
  clearScope,
  describeScope,
  filterEraSetTree,
  isScopeEmpty,
  reconcileScope,
  toggleScopeEra,
  toggleScopeSet,
} from "./marketExplorerScope.mjs";

// Deliberately out of order, so a passing test can only pass because the tree
// sorts rather than because the fixture was already sorted.
const OPTIONS = {
  eras: [
    { id: "era-sv", label: "Scarlet & Violet", sortOrder: 3 },
    { id: "era-sm", label: "Sun & Moon", sortOrder: 1 },
    { id: "era-swsh", label: "Sword & Shield", sortOrder: 2 },
  ],
  sets: [
    { id: "set-twm", label: "Twilight Masquerade", eraId: "era-sv", assets: ["cards"] },
    { id: "set-ah", label: "Ascended Heroes", eraId: "era-sv", assets: ["cards", "sealed"] },
    { id: "set-evo", label: "Evolving Skies", eraId: "era-swsh", assets: ["cards"] },
    { id: "set-bur", label: "Burning Shadows", eraId: "era-sm", assets: ["cards"] },
  ],
};

const tree = () => buildEraSetTree(OPTIONS);

test("the tree is eras in publication order, each holding its own sets", () => {
  const eras = tree();
  assert.deepEqual(eras.map((era) => era.label), ["Sun & Moon", "Sword & Shield", "Scarlet & Violet"]);
  assert.deepEqual(eras.at(-1).sets.map((entry) => entry.label), ["Ascended Heroes", "Twilight Masquerade"]);
});

test("era names are the payload's, and no Legacy bucket is ever invented", () => {
  const labels = tree().map((era) => era.label);
  // The canonical spelling, exactly as the eras table stores it.
  assert.ok(labels.includes("Sword & Shield"));
  for (const label of labels) {
    assert.ok(!label.includes("Legacy"), `${label} must not be relabelled`);
    assert.ok(!label.includes("/"), `${label} must not be a composite bucket`);
  }
  // An era the payload does not carry simply is not in the tree.
  assert.deepEqual(buildEraSetTree({ eras: [], sets: [] }), []);
  assert.deepEqual(buildEraSetTree(null), []);
});

test("the tree narrows to the sets the chosen asset can actually offer", () => {
  const sealed = buildEraSetTree(OPTIONS, { asset: "sealed" });
  assert.deepEqual(sealed.map((era) => era.label), ["Scarlet & Violet"]);
  assert.deepEqual(sealed[0].sets.map((entry) => entry.id), ["set-ah"]);
});

test("selecting an era and expanding it are different actions", () => {
  // Selection is all this module owns. Expansion is component state and does
  // not appear here at all — which is the point: opening Sword & Shield to look
  // inside must never select it.
  const selected = toggleScopeEra(clearScope(), "era-swsh", tree());
  assert.deepEqual(selected, { eraIds: ["era-swsh"], setIds: [] });
  assert.ok(!("expanded" in selected));
  assert.deepEqual(toggleScopeEra(selected, "era-swsh", tree()), { eraIds: [], setIds: [] });
});

test("sets can be selected singly and in multiples", () => {
  let scope = toggleScopeSet(clearScope(), "set-evo", tree());
  assert.deepEqual(scope.setIds, ["set-evo"]);
  scope = toggleScopeSet(scope, "set-bur", tree());
  assert.deepEqual(scope.setIds.sort(), ["set-bur", "set-evo"]);
});

test("an impossible era+set combination is reconciled rather than sent to the backend", () => {
  // The engine ANDs era and set, so "Scarlet & Violet" plus "Evolving Skies"
  // (a Sword & Shield set) resolves to nothing at all. The set is dropped
  // rather than composing a market that is empty by construction.
  const scope = reconcileScope({ eraIds: ["era-sv"], setIds: ["set-evo", "set-ah"] }, tree());
  assert.deepEqual(scope, { eraIds: ["era-sv"], setIds: ["set-ah"] });
});

test("selecting an era strands no previously chosen set silently", () => {
  const withSet = toggleScopeSet(clearScope(), "set-evo", tree());
  const narrowed = toggleScopeEra(withSet, "era-sv", tree());
  assert.deepEqual(narrowed, { eraIds: ["era-sv"], setIds: [] });
});

test("unknown ids are dropped rather than carried into a query", () => {
  assert.deepEqual(reconcileScope({ eraIds: ["era-nope"], setIds: ["set-nope"] }, tree()),
    { eraIds: [], setIds: [] });
});

test("the scope summarises itself, most specific statement first", () => {
  assert.equal(describeScope(clearScope(), tree()), "");
  assert.equal(describeScope({ eraIds: ["era-swsh"], setIds: [] }, tree()), "Sword & Shield");
  assert.equal(describeScope({ eraIds: ["era-swsh", "era-sv"], setIds: [] }, tree()), "2 Eras");
  // An explicit set is the most specific thing the user said, so it wins.
  assert.equal(describeScope({ eraIds: ["era-sv"], setIds: ["set-ah"] }, tree()), "Ascended Heroes");
  assert.ok(isScopeEmpty(clearScope()));
});

test("search matches era names and set names, and an era match keeps its sets", () => {
  assert.deepEqual(filterEraSetTree(tree(), "sword").map((era) => era.label), ["Sword & Shield"]);
  assert.equal(filterEraSetTree(tree(), "sword")[0].sets.length, 1);

  const bySet = filterEraSetTree(tree(), "ascended");
  assert.deepEqual(bySet.map((era) => era.label), ["Scarlet & Violet"]);
  assert.deepEqual(bySet[0].sets.map((entry) => entry.label), ["Ascended Heroes"]);

  assert.deepEqual(filterEraSetTree(tree(), "nothing at all"), []);
  assert.equal(filterEraSetTree(tree(), "").length, 3);
});
