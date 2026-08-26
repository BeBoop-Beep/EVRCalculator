// Server/client determinism for the Market Explorer filter controls.
//
// A hydration warning is not a rendering bug you fix once; it is a property you
// keep. These tests pin the properties whose loss would reintroduce one, rather
// than asserting that some error string is absent — an assertion that would
// pass forever without testing anything.
//
// The properties:
//   1. the filter surfaces render identically twice from the same props, so a
//      second render (which is what hydration is) cannot produce other markup;
//   2. no control's initial DOM state is owned by the browser rather than by
//      React — which is exactly what `<select multiple>` was;
//   3. option order is a pure function of the payload, not of arrival order;
//   4. a series colour is a pure function of its fingerprint, so hydration
//      cannot repaint a line.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFile } from "node:fs/promises";

import MultiSelectFilter from "@/components/ui/MultiSelectFilter";
import { colorForQueryFingerprint, sortEraOptions, sortSetOptions } from "@/lib/explore/marketExplorerQuery.mjs";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

const ERAS_SHUFFLED = [
  { id: "era-sv", label: "Scarlet & Violet", sortOrder: 3 },
  { id: "era-sm", label: "Sun & Moon", sortOrder: 1 },
  { id: "era-swsh", label: "Sword & Shield", sortOrder: 2 },
];

const control = (props = {}) => (
  <MultiSelectFilter
    label="Era"
    name="era"
    options={sortEraOptions(ERAS_SHUFFLED)}
    selectedIds={["era-sv"]}
    allLabel="All Eras"
    summaryNoun="Eras"
    onChange={() => {}}
    {...props}
  />
);

test("the filter control renders identical markup on every render", () => {
  const first = renderToStaticMarkup(control());
  for (let attempt = 0; attempt < 5; attempt += 1) {
    assert.equal(renderToStaticMarkup(control()), first,
      "if two renders of the same props can differ, so can the server's and the client's");
  }
});

test("the server never renders an open popover, so there is nothing to mismatch", () => {
  const markup = renderToStaticMarkup(control());
  assert.ok(!markup.includes('role="listbox"'), "the listbox exists only after a user opens it");
  assert.ok(markup.includes('aria-expanded="false"'));
});

test("no control's initial state is owned by the browser instead of React", async () => {
  for (const file of ["./MarketExplorerQueryBuilder.jsx", "../ui/MultiSelectFilter.jsx"]) {
    // Comments are stripped first: this file and the builder both NAME the
    // native control they replaced, and saying so must not fail the test.
    const source = (await read(file)).replace(/^\s*\/\/.*$/gm, "");
    assert.ok(!/<select\b/.test(source),
      `${file}: a native select's initial selection is applied by the browser, not by React's markup`);
  }
});

test("the shared control uses no layout effect, which the server cannot run", async () => {
  const source = await read("../ui/MultiSelectFilter.jsx");
  assert.ok(!source.includes("useLayoutEffect"),
    "useLayoutEffect is a no-op on the server and warns about it on every render");
});

test("option order is a pure function of the payload, not of arrival order", () => {
  const forward = sortEraOptions(ERAS_SHUFFLED).map((entry) => entry.id);
  const reversed = sortEraOptions([...ERAS_SHUFFLED].reverse()).map((entry) => entry.id);
  assert.deepEqual(forward, ["era-sm", "era-swsh", "era-sv"]);
  assert.deepEqual(reversed, forward, "the same payload in a different order must render the same list");
});

test("ties are broken on the id, so no ordering falls through to database order", () => {
  const tied = [
    { id: "b", label: "Same Name", sortOrder: 1 },
    { id: "a", label: "Same Name", sortOrder: 1 },
  ];
  assert.deepEqual(sortEraOptions(tied).map((entry) => entry.id), ["a", "b"]);
  assert.deepEqual(sortEraOptions([...tied].reverse()).map((entry) => entry.id), ["a", "b"]);
  assert.deepEqual(sortSetOptions(tied).map((entry) => entry.id), ["a", "b"]);
  assert.deepEqual(sortSetOptions([...tied].reverse()).map((entry) => entry.id), ["a", "b"]);
});

test("an era with no sortOrder sorts last deterministically rather than at 0", () => {
  const mixed = [{ id: "z", label: "Unordered" }, { id: "a", label: "First", sortOrder: 1 }];
  assert.deepEqual(sortEraOptions(mixed).map((entry) => entry.id), ["a", "z"]);
  assert.deepEqual(sortEraOptions([...mixed].reverse()).map((entry) => entry.id), ["a", "z"]);
});

test("a series colour is a pure function of its fingerprint", () => {
  const fingerprint = "cards|era=all|set=all|segment=sir|mode=chase|topN=10";
  const first = colorForQueryFingerprint(fingerprint);
  for (let attempt = 0; attempt < 20; attempt += 1) {
    assert.equal(colorForQueryFingerprint(fingerprint), first);
  }
  assert.notEqual(colorForQueryFingerprint(`${fingerprint}x`), first);
});

test("no Explorer surface derives anything from randomness or the clock", async () => {
  for (const file of [
    "./MarketExplorerQueryBuilder.jsx",
    "./MarketExplorerClient.jsx",
    "./MarketExplorerChart.jsx",
    "./MarketExplorerFilters.jsx",
    "../ui/MultiSelectFilter.jsx",
    "../../lib/explore/marketExplorerQuery.mjs",
  ]) {
    const source = await read(file);
    for (const banned of ["Math.random", "Date.now(", "new Date()"]) {
      assert.ok(!source.includes(banned), `${file} must not derive render output from ${banned}`);
    }
  }
});

test("the mobile sheet is a post-mount decision, never a first-render one", async () => {
  const source = await read("../ui/MultiSelectFilter.jsx");
  assert.ok(source.includes("useState(false)"),
    "the sheet layout must start from a fixed value, not from the viewport");
  assert.ok(
    source.indexOf("window.innerWidth") > source.indexOf("useEffect("),
    "every viewport read must sit inside an effect — reading it during render is the classic mismatch",
  );
  // And the proof at the output layer: the server markup carries no layout
  // decision at all, because the surface that would carry one is not rendered.
  assert.ok(!renderToStaticMarkup(control()).includes("data-multi-select-layout"));
});
