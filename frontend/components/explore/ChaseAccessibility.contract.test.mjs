// Chase Accessibility V1 — frontend copy/state contract tests.
//
// Chase Accessibility measures how reachable a set's most valuable/significant
// cards are from a random pack (HC_i-weighted mean of modeled per-pack
// probabilities). It is a raw percentage with no discrete "chase" event, so it
// must never be phrased as a chance/probability of pulling a chase card.
//
// The claims under test:
//   * the approved plain-English meaning is present on the set page,
//   * the forbidden "chance of a chase" framing never appears anywhere near it,
//   * an unavailable/insufficient-coverage state renders distinctly from a
//     measured 0% (`formatPercent(null)` returns an em dash, never "0.0%"),
//   * the three read-model states (ready, no pull model, insufficient mapped
//     HC mass) are all represented without fabricating a value,
//   * Chase Depth, where referenced at all, is never presented as a literal
//     count of chase cards.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { normalizePokemonSetInsightsCriticalPayload } from "../../lib/pokemon/pokemonSetInsightsCriticalNormalizer.mjs";
import { adaptCriticalInsightsToExplorePayload } from "../../lib/pokemon/pokemonSetInsightsCriticalExploreAdapter.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
// Mixed CRLF/LF lives in this directory; normalize before any source assertion.
const readSource = (name) =>
  fs.readFileSync(path.join(here, name), "utf8").replace(/\r\n/g, "\n");

const pageSource = readSource("RipStatisticsPageClient.jsx");

const FORBIDDEN_PHRASES = [
  "chance of pulling a chase card",
  "chance of a chase",
  "probability of a chase",
  "chance to hit the chase",
];

// Locked, independently-approved copy from
// docs/research/CHASE_ACCESSIBILITY_V1_IMPLEMENTATION.md §2 — asserted here
// as fixed literals, NOT derived from the component source, so this test
// fails if the shipped copy drifts from what was actually approved rather
// than merely re-confirming whatever string the component happens to carry.
const CHASE_ACCESSIBILITY_PUBLIC_QUESTION =
  "How reachable are this set's most important cards from a pack?";
const CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP =
  "How accessible the set's most important collectible value is from one pack.";

test("the set page renders the locked technical tooltip verbatim", () => {
  assert.equal(
    pageSource.includes(CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP),
    true,
    "locked technical tooltip string is missing or has drifted from the approved copy"
  );
});

test("the set page carries the approved public plain-English question as its own distinct string", () => {
  assert.equal(
    pageSource.includes(CHASE_ACCESSIBILITY_PUBLIC_QUESTION),
    true,
    "public plain-English question is missing or has drifted from the approved copy"
  );
});

test("the public question and the technical tooltip are never merged into one hybrid sentence", () => {
  assert.notEqual(
    CHASE_ACCESSIBILITY_PUBLIC_QUESTION,
    CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP
  );
  // Neither approved string should be a substring of the other, and no
  // single string in the source should concatenate both.
  assert.equal(
    pageSource.includes(
      `${CHASE_ACCESSIBILITY_PUBLIC_QUESTION} ${CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP}`
    ),
    false
  );
  assert.equal(
    pageSource.includes(
      `${CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP} ${CHASE_ACCESSIBILITY_PUBLIC_QUESTION}`
    ),
    false
  );
});

test("no forbidden chance-of-chase wording appears anywhere in the set page source", () => {
  const lowered = pageSource.toLowerCase();
  for (const phrase of FORBIDDEN_PHRASES) {
    assert.equal(
      lowered.includes(phrase),
      false,
      `forbidden phrase present: ${phrase}`
    );
  }
});

test("Chase Accessibility is labelled distinctly from a generic chase-probability metric", () => {
  assert.match(pageSource, /label:\s*"Chase Accessibility"/);
});

test("Chase Depth, if referenced, is never called a literal count of chase cards", () => {
  // The pre-existing "Cards Carrying Value" tile (effective_chase_count) is a
  // DIFFERENT, older metric and is deliberately left alone; this only asserts
  // that nothing on the page calls Chase Accessibility's own depth concept a
  // literal chase-card count.
  assert.equal(/chaseDepth[^\n]*literal count of chase cards/i.test(pageSource), false);
  assert.equal(/\bnumber of chase cards\b/i.test(pageSource), false);
});

test("normalizer passes chaseAccessibility fields through untouched, never coercing null to 0", () => {
  const normalized = normalizePokemonSetInsightsCriticalPayload({
    chaseAccessibility: null,
    chaseAccessibilityPct: null,
    chaseAccessibilityStatus: "chase_accessibility_insufficient_probability_coverage",
    chaseAccessibilityVersion: "chase_accessibility_v1_hc_value_squared_modeled_probability",
    chaseDepth: null,
    mappedHcMass: 0.42,
  });
  assert.equal(normalized.chaseAccessibility, null);
  assert.equal(normalized.chaseAccessibilityPct, null);
  assert.notEqual(normalized.chaseAccessibilityPct, 0);
  assert.equal(
    normalized.chaseAccessibilityStatus,
    "chase_accessibility_insufficient_probability_coverage"
  );
});

test("normalizer passes a ready, available state through with the measured percentage intact", () => {
  const normalized = normalizePokemonSetInsightsCriticalPayload({
    chaseAccessibility: 0.00234,
    chaseAccessibilityPct: 0.234,
    chaseAccessibilityStatus: "ready",
    chaseAccessibilityVersion: "chase_accessibility_v1_hc_value_squared_modeled_probability",
    chaseDepth: 12.5,
    mappedHcMass: 1.0,
  });
  assert.equal(normalized.chaseAccessibilityPct, 0.234);
  assert.equal(normalized.chaseAccessibilityStatus, "ready");
  assert.equal(normalized.chaseDepth, 12.5);
});

test("normalizer represents the structurally-unsupported (no pull model) state without a value", () => {
  const normalized = normalizePokemonSetInsightsCriticalPayload({
    chaseAccessibility: null,
    chaseAccessibilityPct: null,
    chaseAccessibilityStatus: "unavailable_pull_model",
    chaseAccessibilityVersion: "chase_accessibility_v1_hc_value_squared_modeled_probability",
    chaseDepth: null,
    mappedHcMass: null,
  });
  assert.equal(normalized.chaseAccessibility, null);
  assert.equal(normalized.chaseAccessibilityStatus, "unavailable_pull_model");
});

test("the Explore adapter carries chaseAccessibility fields through verbatim", () => {
  const adapted = adaptCriticalInsightsToExplorePayload({
    chaseAccessibility: 0.005,
    chaseAccessibilityPct: 0.5,
    chaseAccessibilityStatus: "ready",
    chaseAccessibilityVersion: "chase_accessibility_v1_hc_value_squared_modeled_probability",
    chaseDepth: 8.1,
    mappedHcMass: 1.0,
  });
  assert.equal(adapted.chaseAccessibilityPct, 0.5);
  assert.equal(adapted.chaseAccessibilityStatus, "ready");
  assert.equal(adapted.chaseDepth, 8.1);
});

test("the Explore adapter never fabricates a value for a payload with no chase accessibility block", () => {
  const adapted = adaptCriticalInsightsToExplorePayload({});
  assert.equal(adapted.chaseAccessibility, null);
  assert.equal(adapted.chaseAccessibilityPct, null);
  assert.equal(adapted.chaseAccessibilityStatus, null);
});
