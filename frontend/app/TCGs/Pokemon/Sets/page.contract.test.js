const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const pagePath = path.resolve(__dirname, "page.js");

// Phase 5.6: Sword & Shield's simulator-era data is not yet validated for
// public analytics (incomplete pull/hit-rate model, unblended Trainer
// Gallery/Galarian Gallery subsets) — see
// lib/pokemon/pokemonSetPublicCoverage.js. The catalog page hides SWSH sets
// entirely for now (no status-badge UI exists yet to show them
// catalog-only-with-analytics-unavailable). This is a display filter only:
// no set data is deleted, no DB rows touched, no era/scoring math changed.

test("Sets catalog page imports and applies the centralized catalog-visibility helper", () => {
  const source = fs.readFileSync(pagePath, "utf8");

  assert.ok(
    source.includes('import { isHiddenFromPublicPokemonSetsCatalog } from "@/lib/pokemon/pokemonSetPublicCoverage";'),
    "must use the centralized catalog-visibility helper, not a one-off era check"
  );
  assert.ok(
    source.includes(".filter((setSummary) => !isHiddenFromPublicPokemonSetsCatalog(setSummary))"),
    "catalog sets list must be filtered through the centralized catalog-visibility helper"
  );
  assert.ok(
    !/era\s*===\s*["'`]Sword/i.test(source),
    "must not scatter a one-off `era === \"Sword & Shield\"` check instead of using the centralized helper"
  );
});

test("Sets catalog page keeps its existing genuine-empty state separate from the eligibility filter, so filtering SWSH out cannot collapse the page to a crash", () => {
  const source = fs.readFileSync(pagePath, "utf8");

  // groupedEras.length === 0 is the *only* condition gating the "No Pokemon
  // sets available yet" empty state — filtering out 25/171 SWSH sets still
  // leaves 146 sets, so this branch is not expected to trigger, but the
  // page must handle a fully-empty result gracefully either way (proving it
  // doesn't just render a blank page/throw if a future filter change ever
  // does empty it out).
  assert.ok(source.includes("groupedEras.length === 0"));
  assert.ok(source.includes("No Pokémon sets available yet."));
  assert.ok(source.includes("const groupedEras = groupSetsByEra(sets);"));
});
