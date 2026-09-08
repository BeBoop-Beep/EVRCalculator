import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const rip = read("./RipDecisionPage.jsx");
const css = read("./RipDecisionPage.module.css");
const selector = read("./chaseAccessibilityPresentationSelector.mjs");
const analysis = read("../pokemon/set-page/Analysis/PokemonSetAnalysisClient.jsx");

test("Opening Snapshot is Overall above three equal peer cards", () => {
  assert.ok(rip.indexOf("metrics.overall") < rip.indexOf("data-three-pillar-summary"));
  assert.match(rip, /styles\.pillarCardRow/);
  assert.match(css, /\.pillarCardRow[^}]*repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(css, /\.pillarCardRow \{ grid-template-columns:minmax\(0,1fr\)/);
});
test("Financial, Chase, and Collector have separate destinations", () => {
  for (const id of ["set-detail-financial-rip", "set-detail-chase-accessibility", "set-detail-collector-appeal"]) assert.ok(rip.includes(id));
  assert.match(rip, /<FinancialRipV3Breakdown/);
  assert.match(rip, /<CollectorAppealBreakdown/);
  assert.match(rip, /Raw Accessibility:/);
  assert.doesNotMatch(rip, /data-market-based-summary-group/);
});
test("Chase uses backend public score and standing without frontend scoring", () => {
  for (const field of ["publicScore", "rank", "cohortSize", "cohortId"]) assert.ok(selector.includes(field));
  assert.match(rip, /chase\.publicScore/);
  assert.doesNotMatch(selector, /computePublic|normalizePublic|Math\.min.*modelScore/i);
});
test("missing public score is not replaced by raw or model score", async () => {
  const { selectChaseAccessibilityPresentation } = await import("./chaseAccessibilityPresentationSelector.mjs");
  const value = selectChaseAccessibilityPresentation({ chaseAccessibility: { value: 0.004, percent: 0.4, modelScore: 66, publicScore: null, status: "ready" } });
  assert.equal(value.publicScore, null);
  assert.equal(value.rawAccessibility, 0.004);
  assert.equal(value.modelScore, 66);
});
test("Set Analysis exposes peers and preserves the old deep-link alias", () => {
  for (const id of ["financial-rip", "chase-accessibility", "collector-appeal"]) assert.ok(analysis.includes(`"${id}"`));
  assert.match(analysis, /requestedSectionRaw === "market-based" \? "financial-rip"/);
  assert.doesNotMatch(analysis, /activeSection === "market-based"/);
});
test("ordinary presentation contains no weighting recipe", () => {
  for (const source of [rip, analysis]) assert.doesNotMatch(source, /86\s*\/\s*4\s*\/\s*10|0\.86\s*\*|0\.04\s*\*|90\/10 explanation/);
});
