import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./PokemonSetAnalysisClient.jsx", import.meta.url), "utf8");

test("Set Analysis exposes approved peer overview and independent breakdown sections", () => {
  for (const label of ["Overall RIP", "Financial RIP", "Chase Accessibility", "Collector Appeal"])
    assert.match(source, new RegExp(label));
  for (const section of ["financial-rip", "chase-accessibility", "collector-appeal"])
    assert.match(source, new RegExp(`\\["${section}"`));
});

test("Set Analysis preserves the old deep link only as a Financial alias", () => {
  assert.match(source, /requestedSectionRaw === "market-based" \? "financial-rip"/);
  assert.doesNotMatch(source, /value: "market-based"/);
});

test("Set Analysis renders Chase public score, rank, and cohort without fallback", () => {
  assert.match(source, /chaseAccessibility\.publicScore/);
  assert.match(source, /chaseAccessibility\.rank/);
  assert.match(source, /chaseAccessibility\.cohortSize/);
  assert.doesNotMatch(source, /publicScore\s*\?\?\s*(?:modelScore|rawAccessibility|displayAccessibility)/);
});

test("Analysis route remains an actual component-backed consumer", () => {
  assert.match(source, /getPokemonSetInsightsCritical\(setId\)/);
  assert.match(source, /selectChaseAccessibilityPresentation/);
  assert.match(source, /activeSection === "overview"/);
});
