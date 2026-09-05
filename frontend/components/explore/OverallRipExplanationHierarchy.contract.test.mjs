// Overall RIP explanation hierarchy — semantic contract tests (Phase 14).
//
// Covers: version-aware Overall explanation (A), Market-Based explanatory-only
// (B), Accessibility raw-vs-score separation touch points relevant to this
// selector (D, partial — the fuller Accessibility contract lives in
// ChaseAccessibility.contract.test.mjs), no-frontend-scoring (I), and shadow
// safety (J): a generic/current fixture carrying BOTH V10 and V12 data must
// still render V10 until a caller explicitly supplies the V12 contract shape.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { selectOverallRipExplanationHierarchy } from "./overallRipExplanationHierarchySelector.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const selectorSource = fs.readFileSync(
  path.join(here, "overallRipExplanationHierarchySelector.mjs"),
  "utf8"
);
const componentSource = fs.readFileSync(
  path.join(here, "OverallRipExplanationHierarchy.jsx"),
  "utf8"
);

const V10_ONLY_SOURCE = {
  publicRipContractV10: {
    overallRip: {
      relativeScore: 82.4,
      rank: 3,
      rankedSetCount: 40,
      tier: "Great",
      status: "ready",
    },
    financialRip: { relativeScore: 80.1 },
    collectorAppeal: { relativeScore: 70.5 },
  },
};

const V12_CONTRACT_SOURCE = {
  publicRipContractV11: {
    overallRipV12: {
      score: 78.3,
      status: "ready",
      statusReason: null,
      rankable: true,
      version: "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5",
      components: {
        financialRipV4: { score: 80.0, weight: 0.86, contribution: 68.8 },
        chaseAccessibility: { raw: 0.002, score: 50.0, weight: 0.04, contribution: 2.0 },
        collectorAppeal: { score: 75.0, weight: 0.1, contribution: 7.5 },
      },
      missingInputs: [],
    },
    overallRipV12Composition: {
      version: "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5",
      inputs: {
        financialRip: "financial_rip_v4",
        chaseAccessibility: "chase_accessibility_v1",
        collectorAppeal: "collector_appeal_v5",
      },
      weights: { financial_rip: 0.86, chase_accessibility: 0.04, collector_appeal: 0.1 },
      effectiveWeights: { chase_accessibility: 0.04 },
    },
  },
};

// A generic/current resolver fixture where BOTH V10 and V12 data are present
// (the real backend shape once the shadow lineage is enriched onto a target
// row) but the caller only ever supplies the plain target object — never the
// explicit `publicRipContractV11` opt-in key.
const AMBIENT_BOTH_VERSIONS_SOURCE = {
  ...V10_ONLY_SOURCE,
  overallRipV12: V12_CONTRACT_SOURCE.publicRipContractV11.overallRipV12,
  overallRipV12Composition: V12_CONTRACT_SOURCE.publicRipContractV11.overallRipV12Composition,
};

test("A: V10-only data renders a presentation-safe explanation and never claims Accessibility", () => {
  const explanation = selectOverallRipExplanationHierarchy(V10_ONLY_SOURCE);
  assert.equal(explanation.version, "v10");
  assert.equal(explanation.canonical, true);
  assert.equal(explanation.headline, "Overall RIP combines Financial RIP with Collector Appeal.");
  assert.equal(explanation.marketBased, null);
  assert.equal(/accessibility/i.test(explanation.headline), false);
});

test("A: explicit V12 contract data renders a presentation-safe headline with an optional Market-Based grouping", () => {
  const explanation = selectOverallRipExplanationHierarchy(V12_CONTRACT_SOURCE);
  assert.equal(explanation.version, "v12");
  assert.equal(explanation.canonical, false);
  assert.equal(
    explanation.headline,
    "Overall RIP combines Market-Based Opening Quality with Collector Appeal."
  );
  assert.ok(explanation.marketBased);
  assert.equal(explanation.marketBased.explanatoryOnly, true);
  assert.equal(
    explanation.marketBased.headline,
    "Market-Based Opening Quality combines Financial RIP with Chase Accessibility."
  );
});

test("B: Market-Based grouping is mathematically consistent and explanatory-only, never its own persisted score", () => {
  const explanation = selectOverallRipExplanationHierarchy(V12_CONTRACT_SOURCE);
  const marketBased = explanation.marketBased;
  assert.ok(marketBased);
  assert.equal(Math.round(marketBased.marketBasedWeight * 100), 90);
  assert.equal(Math.round(marketBased.collectorWeight * 100), 10);
  assert.equal(Math.round(marketBased.internalFinancialShare * 10000) / 100, 95.56);
  assert.equal(Math.round(marketBased.internalAccessibilityShare * 10000) / 100, 4.44);
  // No field anywhere in the view model claims Market-Based itself is scored
  // or persisted.
  assert.equal("persistedScore" in marketBased, false);
  assert.equal("score" in marketBased, false);
});

test("J: shadow safety — a generic fixture carrying BOTH versions still resolves V10 until the caller explicitly opts into the V11 contract", () => {
  const explanation = selectOverallRipExplanationHierarchy(AMBIENT_BOTH_VERSIONS_SOURCE);
  assert.equal(explanation.version, "v10");
  assert.equal(explanation.headline, "Overall RIP combines Financial RIP with Collector Appeal.");
});

test("J: an explicit V11-contract fixture renders the V12 explanation", () => {
  const explanation = selectOverallRipExplanationHierarchy(V12_CONTRACT_SOURCE);
  assert.equal(explanation.version, "v12");
});

test("never explains V10 data with V12 weights: V10-only headline never contains 86% or 4%", () => {
  const explanation = selectOverallRipExplanationHierarchy(V10_ONLY_SOURCE);
  assert.equal(/86%/.test(explanation.headline), false);
  assert.equal(/\b4%\b/.test(explanation.headline), false);
});

// PERMANENT CONTRACT (Phase 7/10-B): the current V12 presentation must never
// emit any locked scoring-weight percentage, in either the Overall headline
// or the Market-Based grouping, for any available explanation.
test("PERMANENT: no locked scoring-weight percentages anywhere in V12 or V10 presentation output", () => {
  const forbidden = ["86%", "4%", "10%", "90%", "95.56", "4.44"];
  const v12 = selectOverallRipExplanationHierarchy(V12_CONTRACT_SOURCE);
  const v10 = selectOverallRipExplanationHierarchy(V10_ONLY_SOURCE);
  const rendered = [
    v12.headline,
    v12.marketBased && v12.marketBased.headline,
    v12.marketBased && v12.marketBased.note,
    v10.headline,
  ]
    .filter(Boolean)
    .join(" | ");
  for (const token of forbidden) {
    assert.equal(rendered.includes(token), false, `forbidden weight token "${token}" found in: ${rendered}`);
  }
});

test("I: no frontend scoring — selector source never implements the V12 blend or the Accessibility transform", () => {
  assert.equal(/0\.86\s*\*/.test(selectorSource), false);
  assert.equal(/\.86\s*\*\s*F/i.test(selectorSource), false);
  assert.equal(/100\s*\*\s*A(_raw)?\s*\/\s*\(A(_raw)?\s*\+\s*0?\.002\)/.test(selectorSource), false);
  assert.equal(/A_raw\s*\/\s*\(A_raw\s*\+/.test(selectorSource), false);
});

test("I: component never implements Overall RIP scoring math, only renders the selector's view model", () => {
  assert.equal(/0\.86/.test(componentSource), false);
  assert.equal(/0\.04/.test(componentSource), false);
  assert.equal(/0\.002/.test(componentSource), false);
});

test("approved public question is present verbatim", () => {
  assert.equal(
    selectorSource.includes("How good is this to open overall?"),
    true
  );
});

test("Market-Based public question is present verbatim and distinct from the Overall question", () => {
  assert.equal(
    selectorSource.includes(
      "What do the market and modeled opening outcomes say about this opening?"
    ),
    true
  );
});

test("no forbidden chase-probability phrasing in the selector or component", () => {
  const forbidden = ["chance of a chase", "probability of a chase"];
  for (const phrase of forbidden) {
    assert.equal(selectorSource.toLowerCase().includes(phrase), false);
    assert.equal(componentSource.toLowerCase().includes(phrase), false);
  }
});

test("unavailable V12 never fabricates a headline or a Market-Based grouping from missing weights", () => {
  const explanation = selectOverallRipExplanationHierarchy({
    publicRipContractV11: {
      overallRipV12: { score: null, status: "unavailable_missing_input", statusReason: "x" },
      overallRipV12Composition: { weights: {}, effectiveWeights: {} },
    },
  });
  assert.equal(explanation.available, false);
  assert.equal(explanation.headline, null);
  assert.equal(explanation.marketBased, null);
});
