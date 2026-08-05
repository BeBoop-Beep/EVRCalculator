// The RIP hero selector, after the V7 cutover.
//
// This file previously asserted the OPPOSITE of what it asserts now: that the
// hero resolves the backend `rip` object and offers a "RIP Core" mode. `rip` is
// Overall RIP **v4** (90% RIP Core + 10% legacy CA7) and RIP Core is Financial
// RIP **V2**, so those assertions pinned a superseded model under the public
// name. They are replaced, not relaxed.
//
// The end-to-end canonical guarantees (v4-vs-V7 precedence, the unavailable
// state, the Collector Appeal and Financial RIP halves) live in
// canonicalRipV7.contract.test.mjs. This file covers the hero selector itself.

import assert from "node:assert/strict";
import test from "node:test";

import {
  RIP_SCORE_HELPER,
  RIP_SCORE_LABEL,
  hasCanonicalRipContract,
  selectRipHeroScoreMode,
} from "./ripHeroScoreMode.mjs";

const CANONICAL_TARGET = {
  publicRipContractV7: {
    overallRip: {
      score: 41.8,
      absoluteScore: 41.8,
      relativeScore: 73.4,
      rank: 4,
      rankedSetCount: 21,
      tier: "A",
      version: "overall_rip_v7",
    },
  },
};

// Overall RIP v4, Financial RIP V2 and the legacy min-max presentation fields,
// with values that could not be mistaken for the canonical ones above.
const LEGACY_ONLY_TARGET = {
  rip: { score: 88.8, relativeScore: 12.3, rank: 19, cohortSize: 21, tier: "F" },
  ripCore: { score: 77.7, relativeScore: 15.5, rank: 18, cohortSize: 21, tier: "F" },
  pack_score: 64.2,
  relative_pack_score: 51.0,
  pack_rank: 9,
};

test("the hero resolves the canonical V7 score, rank, tier and cohort", () => {
  const selected = selectRipHeroScoreMode({ target: CANONICAL_TARGET });

  assert.equal(selected.label, RIP_SCORE_LABEL);
  assert.equal(selected.label, "RIP Score");
  assert.equal(selected.available, true);
  assert.equal(selected.score, 73.4);
  assert.equal(selected.rank, 4);
  assert.equal(selected.tier, "A");
  assert.equal(selected.cohortSize, 21);
  assert.equal(selected.sourceShape, "publicRipContractV7");
});

test("the public score is the relative score; the absolute stays a diagnostic", () => {
  const selected = selectRipHeroScoreMode({ target: CANONICAL_TARGET });
  assert.equal(selected.score, selected.relativeScore);
  assert.equal(selected.absoluteScore, 41.8);
  assert.notEqual(selected.score, selected.absoluteScore);
});

test("there is one mode: no RIP Core, no mode argument, no coreAvailable", () => {
  const selected = selectRipHeroScoreMode({ target: CANONICAL_TARGET });
  assert.equal("mode" in selected, false, "the selector no longer resolves a mode");
  assert.equal("coreAvailable" in selected, false);
  // Passing a legacy mode argument cannot change anything.
  const withIgnoredMode = selectRipHeroScoreMode({ mode: "rip-core", target: CANONICAL_TARGET });
  assert.deepEqual(withIgnoredMode, selected);
});

test("the hero returns no interpretation label, summary or severity", () => {
  const selected = selectRipHeroScoreMode({
    target: {
      ...CANONICAL_TARGET,
      rip_score_interpretation_label: "Elite but swingy",
      rip_score_interpretation_summary: "High ceiling, rough floor.",
      rip_score_interpretation_severity: "warning",
      ripScoreInterpretationLabel: "Elite but swingy",
    },
  });
  assert.equal("interpretation" in selected, false);
  assert.equal(JSON.stringify(selected).includes("Elite but swingy"), false);
});

test("the helper is neutral and states no weight or verdict", () => {
  assert.equal(RIP_SCORE_HELPER, "Financial performance + collector appeal");
  assert.equal(/\d/.test(RIP_SCORE_HELPER), false, "no percentage or weight in public copy");
  assert.equal(/RIP Core|Profit|Safety|Stability/.test(RIP_SCORE_HELPER), false);
});

test("a legacy-only payload renders unavailable, never a legacy score", () => {
  const selected = selectRipHeroScoreMode({ summary: LEGACY_ONLY_TARGET });

  assert.equal(selected.available, false);
  assert.equal(selected.score, null);
  assert.equal(selected.relativeScore, null);
  assert.equal(selected.absoluteScore, null);
  assert.equal(selected.rank, null);
  assert.equal(selected.tier, null);
  assert.equal(selected.cohortSize, null);
  assert.equal(hasCanonicalRipContract(LEGACY_ONLY_TARGET), false);
});

test("source precedence is payload -> target -> summary within the one model", () => {
  const payload = {
    publicRipContractV7: { overallRip: { relativeScore: 90.0, rank: 1, tier: "S", rankedSetCount: 21 } },
  };
  const target = { publicRipContractV7: { overallRip: { relativeScore: 50.0, rank: 10, tier: "C" } } };
  const summary = { publicRipContractV7: { overallRip: { relativeScore: 10.0, rank: 20, tier: "F" } } };

  assert.equal(selectRipHeroScoreMode({ payload, target, summary }).score, 90.0);
  assert.equal(selectRipHeroScoreMode({ target, summary }).score, 50.0);
  assert.equal(selectRipHeroScoreMode({ summary }).score, 10.0);
});

test("the backend's unavailable reason is carried, not replaced by a number", () => {
  const selected = selectRipHeroScoreMode({
    target: {
      overallRipV7: {
        score: null,
        status: "unavailable_missing_input",
        statusReason: "collector_appeal_v3_unavailable",
      },
      rip: LEGACY_ONLY_TARGET.rip,
    },
  });
  assert.equal(selected.available, false);
  assert.equal(selected.score, null);
  assert.equal(selected.status, "unavailable_missing_input");
  assert.equal(selected.statusReason, "collector_appeal_v3_unavailable");
});

test("no arguments at all is safe and unavailable", () => {
  const selected = selectRipHeroScoreMode();
  assert.equal(selected.available, false);
  assert.equal(selected.score, null);
  assert.equal(selected.label, "RIP Score");
});
