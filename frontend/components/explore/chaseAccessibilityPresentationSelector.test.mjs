// Chase Accessibility public presentation contract — unit tests (Phase 3/10-D).

import assert from "node:assert/strict";
import test from "node:test";

import { selectChaseAccessibilityPresentation } from "./chaseAccessibilityPresentationSelector.mjs";

const READY_SOURCE = {
  publicRipContractV11: {
    chaseAccessibility: {
      value: 0.0021,
      percent: 0.21,
      status: "ready",
      statusReason: null,
      version: "chase_accessibility_v1",
      chaseDepth: 3.87,
      mappedHcMass: 0.94,
      publicQuestion: "How reachable are this set's most important collectible values from a pack?",
      technicalTooltip: "How accessible the set's most important collectible value is from one pack.",
    },
  },
};

const UNAVAILABLE_SOURCE = {
  publicRipContractV11: {
    chaseAccessibility: {
      value: null,
      percent: null,
      status: "unavailable_missing_input",
      statusReason: "no probability-mapped drawable variants for this set",
      version: "chase_accessibility_v1",
      chaseDepth: null,
      mappedHcMass: null,
    },
  },
};

test("available: reads rawAccessibility/displayAccessibility, chaseDepth and mappedHcMass verbatim", () => {
  const chase = selectChaseAccessibilityPresentation(READY_SOURCE);
  assert.equal(chase.available, true);
  assert.equal(chase.status, "ready");
  assert.equal(chase.rawAccessibility, 0.0021);
  assert.equal(chase.displayAccessibility, 0.21);
  assert.equal(chase.chaseDepth, 3.87);
  assert.equal(chase.chaseDepthAvailable, true);
  assert.equal(chase.mappedHcMass, 0.94);
  assert.equal(chase.mappedHcMassAvailable, true);
});

test("unavailable: never fabricates a value from a missing/unready block", () => {
  const chase = selectChaseAccessibilityPresentation(UNAVAILABLE_SOURCE);
  assert.equal(chase.available, false);
  assert.equal(chase.rawAccessibility, null);
  assert.equal(chase.displayAccessibility, null);
  assert.equal(chase.statusReason, "no probability-mapped drawable variants for this set");
});

test("rank/tier/cohortSize are NEVER fabricated — always null regardless of input (Phase 8)", () => {
  const chase = selectChaseAccessibilityPresentation(READY_SOURCE);
  assert.equal(chase.rank, null);
  assert.equal(chase.cohortSize, null);
  assert.equal(chase.tier, null);
  // Even if a caller's source object smuggled in rank-shaped fields, this
  // selector must not surface them as a real rank until a canonical backend
  // contract exists.
  const withFakeRank = selectChaseAccessibilityPresentation({
    publicRipContractV11: {
      chaseAccessibility: { ...READY_SOURCE.publicRipContractV11.chaseAccessibility, rank: 3, cohortSize: 40 },
    },
  });
  assert.equal(withFakeRank.rank, null);
  assert.equal(withFakeRank.cohortSize, null);
});

test("valueConcentration/topCardConcentration are not-yet-backed diagnostics: always null, never derived locally", () => {
  const chase = selectChaseAccessibilityPresentation(READY_SOURCE);
  assert.equal(chase.valueConcentration, null);
  assert.equal(chase.topCardConcentration, null);
});

test("diagnostic fields are distinguished from the scored primary metric by shape, not just docs", () => {
  const chase = selectChaseAccessibilityPresentation(READY_SOURCE);
  assert.ok("rawAccessibility" in chase && "displayAccessibility" in chase);
  assert.ok("chaseDepth" in chase && "valueConcentration" in chase && "mappedHcMass" in chase);
  // The scored fields and diagnostic fields are named distinctly enough that
  // no render surface can accidentally treat one as the other.
  assert.notEqual(Object.keys(chase).includes("chaseDepthScore"), true);
});

test("no scoring weight or transform constant is ever exposed on this contract", () => {
  const chase = selectChaseAccessibilityPresentation(READY_SOURCE);
  const serialized = JSON.stringify(chase);
  assert.equal(/0\.002\b/.test(serialized.replace("0.0021", "")), false);
  assert.equal("weight" in chase, false);
  assert.equal("weights" in chase, false);
});

test("public copy is sourced from the backend block, falling back to the locked default only when absent", () => {
  const chase = selectChaseAccessibilityPresentation(READY_SOURCE);
  assert.equal(
    chase.publicQuestion,
    "How reachable are this set's most important collectible values from a pack?"
  );
  const noQuestionSource = {
    publicRipContractV11: {
      chaseAccessibility: { value: 0.001, percent: 0.1, status: "ready" },
    },
  };
  const fallback = selectChaseAccessibilityPresentation(noQuestionSource);
  assert.equal(
    fallback.publicQuestion,
    "How reachable are this set's most important collectible values from a pack?"
  );
});
