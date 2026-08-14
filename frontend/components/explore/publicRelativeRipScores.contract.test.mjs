// The public score layer, per metric.
//
// WHAT THIS FILE USED TO ASSERT
// -----------------------------
// That `selectFinancialRipV3Breakdown(...).score` is the ABSOLUTE fixed-anchor
// value while `.publicScore` is the relative one — and the same for Collector
// Appeal, with a fixture whose two layers were 67.3 and 93.6. That is the exact
// dual-scale behaviour that let one set print Collector Appeal as 53.2 in the
// "Why It Ranks" block and 95.9 in the RIP Summary above it, and it was written
// down here as intended.
//
// It is not intended. There is now no generic `score` on either selector: the
// public value is `publicScore` (the backend cohort-relative 0-100 score) and
// the model output is `modelScore`, named so it cannot be mistaken for a public
// number. This file now asserts that separation instead of the old ambiguity.
//
// Cross-surface agreement — the property that actually prevents the defect — is
// asserted in publicMetricContract.contract.test.mjs.

import assert from "node:assert/strict";
import test from "node:test";

import { selectFinancialRipV3Breakdown } from "./financialRipV3Selector.mjs";
import { selectCollectorAppealBreakdown } from "./collectorAppealBreakdownSelector.mjs";

function financialFixture() {
  return {
    score: 48.25,
    absoluteScore: 48.25,
    relativeScore: 82.4,
    status: "ready",
    rank: 4,
    cohortSize: 22,
    tier: "A",
    components: {
      true_win_frequency: {
        score: 31.2,
        absoluteScore: 31.2,
        relativeScore: 74.5,
        rank: 5,
        cohortSize: 22,
        tier: "B",
        raw: { trueWinProbability: 0.312 },
      },
      typical_retention: {
        score: 28.1,
        absoluteScore: 28.1,
        relativeScore: 63.0,
        rank: 8,
        cohortSize: 22,
        tier: "B",
        raw: { typicalPackValue: 2.81 },
      },
      loss_resilience: {
        score: 35.0,
        absoluteScore: 35.0,
        relativeScore: 79.0,
        rank: 4,
        cohortSize: 22,
        tier: "A",
        raw: { averageRetentionGivenLoss: 0.35 },
      },
      realistic_upside: {
        score: 55.4,
        absoluteScore: 55.4,
        relativeScore: 91.2,
        rank: 2,
        cohortSize: 22,
        tier: "A",
        raw: { p95ThresholdValue: 15.54 },
      },
      jackpot_upside: {
        score: 61.0,
        absoluteScore: 61.0,
        relativeScore: 88.7,
        rank: 3,
        cohortSize: 22,
        tier: "A",
        raw: { p99ThresholdValue: 61.0 },
      },
      base_economic_efficiency: {
        score: 39.8,
        absoluteScore: 39.8,
        relativeScore: 70.1,
        rank: 6,
        cohortSize: 22,
        tier: "B",
        raw: { baseRtpExcludingTop1Pct: 0.398, totalRtpRatio: 0.52 },
      },
    },
  };
}

function canonicalFixture() {
  return {
    publicRipContractV8: {
      overallRip: {
        score: 50.0,
        absoluteScore: 50.0,
        relativeScore: 85.0,
        rank: 3,
        rankedSetCount: 22,
        tier: "A",
      },
      financialRip: financialFixture(),
      collectorAppeal: {
        score: 67.3,
        absoluteScore: 67.3,
        relativeScore: 93.6,
        rank: 2,
        rankedSetCount: 22,
        tier: "A",
        components: {
          rosterDesirability: { score: 84.0 },
          desirableOutcomeFrequency: { rawValue: 0.19 },
          dualPathDepth: { rawValue: 0.42 },
        },
        subjectScope: {
          modeled: ["Pokémon"],
          notYetModeled: ["Trainer", "Artist"],
        },
      },
    },
  };
}

test("Financial RIP exposes ONE public score, and it is the relative one", () => {
  const selected = selectFinancialRipV3Breakdown(financialFixture());
  assert.equal(selected.publicScore, 82.4);
  assert.equal(selected.publicScoreLabel, "82.4");
  assert.equal(selected.publicAvailable, true);
  // The model output is still readable, under a name no surface will mistake.
  assert.equal(selected.modelScore, 48.25);
  // And there is no ambiguous `score` for a consumer to pick by accident.
  assert.equal("score" in selected, false);
  assert.equal("scoreLabel" in selected, false);
  assert.equal("absoluteScore" in selected, false);
});

test("every Financial RIP component exposes ONE public score", () => {
  const selected = selectFinancialRipV3Breakdown(financialFixture());
  assert.deepEqual(
    selected.rows.map((row) => row.publicScore),
    [74.5, 63.0, 79.0, 91.2, 88.7, 70.1]
  );
  assert.deepEqual(
    selected.rows.map((row) => row.modelScore),
    [31.2, 28.1, 35.0, 55.4, 61.0, 39.8]
  );
  assert.ok(selected.rows.every((row) => row.publicAvailable));
  assert.ok(selected.rows.every((row) => !("score" in row)));
  assert.ok(selected.rows.every((row) => !("absoluteScore" in row)));
});

test("Collector Appeal exposes ONE public score, and it is the relative one", () => {
  const selected = selectCollectorAppealBreakdown(canonicalFixture());
  assert.equal(selected.publicScore, 93.6);
  assert.equal(selected.publicScoreLabel, "93.6");
  assert.equal(selected.publicAvailable, true);
  assert.equal(selected.modelScore, 67.3);
  assert.equal("score" in selected, false);
  assert.equal("scoreLabel" in selected, false);
  assert.equal("absoluteScore" in selected, false);
});

test("Collector Appeal factor values stay on their native units", () => {
  const selected = selectCollectorAppealBreakdown(canonicalFixture());
  const byKey = new Map(selected.rows.map((row) => [row.key, row]));
  assert.equal(byKey.get("rosterDesirability").value, "84.0");
  assert.equal(byKey.get("desirableOutcomeFrequency").value, "19.0%");
  // D is published 0-100 and H is a 0-1 share rendered as a percentage. Neither
  // is rescaled into the other. Dual-Path Depth is absent because Collector
  // Appeal V4 does not consume it.
  assert.equal(byKey.has("dualPathDepth"), false);
});

test("a missing Financial relativeScore renders unavailable, never the model score", () => {
  const stale = financialFixture();
  delete stale.relativeScore;
  for (const component of Object.values(stale.components)) {
    delete component.relativeScore;
  }

  const selected = selectFinancialRipV3Breakdown(stale);
  assert.equal(selected.publicScore, null);
  assert.equal(selected.publicScoreLabel, "—");
  assert.equal(selected.publicAvailable, false);
  // The whole section reports itself unavailable rather than letting a
  // differently-scaled number take a public slot.
  assert.equal(selected.diagnostics.status, "unavailable");
  assert.ok(selected.rows.every((row) => row.publicScore === null));
  assert.ok(selected.rows.every((row) => row.available === false));
  // The model score is still there for audit — it is simply not public.
  assert.equal(selected.modelScore, 48.25);
  assert.ok(selected.rows.every((row) => row.modelScore !== null));
});

test("a missing Collector Appeal relativeScore renders unavailable, never the model score", () => {
  const stale = canonicalFixture();
  delete stale.publicRipContractV8.collectorAppeal.relativeScore;

  const selected = selectCollectorAppealBreakdown(stale);
  assert.equal(selected.publicScore, null);
  assert.equal(selected.publicScoreLabel, "—");
  assert.equal(selected.publicAvailable, false);
  assert.equal(selected.available, false);
  assert.equal(selected.modelScore, 67.3);
});
