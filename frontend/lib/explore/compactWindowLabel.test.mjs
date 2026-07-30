import test from "node:test";
import assert from "node:assert/strict";

import { getCompactWindowLabel, needsAccessibleWindowLabel } from "./compactWindowLabel.mjs";
import { DELTA_WINDOW_DEFINITIONS } from "./marketDeltaWindows.mjs";

test("Lifetime abbreviates to LT", () => {
  assert.equal(getCompactWindowLabel("lifetime", "Lifetime"), "LT");
  assert.equal(getCompactWindowLabel("LIFETIME", "Lifetime"), "LT");
});

test("already-compact windows pass through untouched", () => {
  for (const [key, label] of [["1D", "1D"], ["7D", "7D"], ["30D", "30D"], ["3M", "3M"], ["6M", "6M"], ["1Y", "1Y"]]) {
    assert.equal(getCompactWindowLabel(key, label), label, `${label} must not be rewritten`);
  }
});

test("every standard window has a compact form of at most three characters", () => {
  // The brief's compact set: 1D 7D 30D 3M 6M 1Y LT.
  const compact = DELTA_WINDOW_DEFINITIONS.map((entry) => getCompactWindowLabel(entry.key, entry.label));
  assert.deepEqual(compact, ["1D", "7D", "30D", "3M", "6M", "1Y", "LT"]);
  for (const label of compact) {
    assert.ok(label.length <= 3, `${label} must stay compact`);
  }
});

test("only the abbreviated window needs an explicit accessible name", () => {
  assert.equal(needsAccessibleWindowLabel("lifetime", "Lifetime"), true, "LT must announce as Lifetime");
  assert.equal(needsAccessibleWindowLabel("7D", "7D"), false, "7D already reads correctly");
});

test("the abbreviation never changes the window key or its data", () => {
  // The helper is label-only; it has no access to, and returns nothing about,
  // the window key used for selection.
  for (const entry of DELTA_WINDOW_DEFINITIONS) {
    const before = { ...entry };
    getCompactWindowLabel(entry.key, entry.label);
    assert.deepEqual(entry, before, "definitions must not be mutated");
  }
  const lifetime = DELTA_WINDOW_DEFINITIONS.find((entry) => entry.key === "lifetime");
  assert.equal(lifetime.label, "Lifetime", "the canonical label is unchanged");
  assert.equal(lifetime.days, null, "the underlying timeframe is unchanged");
});

test("unknown or missing input degrades to the given label", () => {
  assert.equal(getCompactWindowLabel("custom", "Custom Window"), "Custom Window");
  assert.equal(getCompactWindowLabel(undefined, undefined), "");
});
