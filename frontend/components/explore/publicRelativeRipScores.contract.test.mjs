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
        raw: {},
      },
      typical_retention: {
        score: 28.1,
        absoluteScore: 28.1,
        relativeScore: 63.0,
        rank: 8,
        cohortSize: 22,
        tier: "B",
        raw: {},
      },
      loss_resilience: {
        score: 35.0,
        absoluteScore: 35.0,
        relativeScore: 79.0,
        rank: 4,
        cohortSize: 22,
        tier: "A",
        raw: {},
      },
      realistic_upside: {
        score: 55.4,
        absoluteScore: 55.4,
        relativeScore: 91.2,
        rank: 2,
        cohortSize: 22,
        tier: "A",
        raw: {},
      },
      jackpot_upside: {
        score: 61.0,
        absoluteScore: 61.0,
        relativeScore: 88.7,
        rank: 3,
        cohortSize: 22,
        tier: "A",
        raw: {},
      },
      base_economic_efficiency: {
        score: 39.8,
        absoluteScore: 39.8,
        relativeScore: 70.1,
        rank: 6,
        cohortSize: 22,
        tier: "B",
        raw: {},
      },
    },
  };
}

function canonicalFixture() {
  return {
    publicRipContractV7: {
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

test("Financial RIP separates absolute model score from public relative score", () => {
  const selected = selectFinancialRipV3Breakdown(financialFixture());
  assert.equal(selected.score, 48.25);
  assert.equal(selected.scoreLabel, "48.3");
  assert.equal(selected.absoluteScore, 48.25);
  assert.equal(selected.relativeScore, 82.4);
  assert.equal(selected.publicScore, 82.4);
  assert.equal(selected.publicScoreLabel, "82.4");
  assert.equal(selected.publicAvailable, true);
});

test("every Financial RIP component exposes its own public relative score", () => {
  const selected = selectFinancialRipV3Breakdown(financialFixture());
  assert.deepEqual(
    selected.rows.map((row) => row.publicScore),
    [74.5, 63.0, 79.0, 91.2, 88.7, 70.1]
  );
  assert.deepEqual(
    selected.rows.map((row) => row.absoluteScore),
    [31.2, 28.1, 35.0, 55.4, 61.0, 39.8]
  );
  assert.ok(selected.rows.every((row) => row.publicAvailable));
});

test("Collector Appeal separates absolute model score from public relative score", () => {
  const selected = selectCollectorAppealBreakdown(canonicalFixture());
  assert.equal(selected.score, 67.3);
  assert.equal(selected.scoreLabel, "67.3");
  assert.equal(selected.absoluteScore, 67.3);
  assert.equal(selected.relativeScore, 93.6);
  assert.equal(selected.publicScore, 93.6);
  assert.equal(selected.publicScoreLabel, "93.6");
  assert.equal(selected.publicAvailable, true);
});

test("Collector Appeal factor values stay on their native units", () => {
  const selected = selectCollectorAppealBreakdown(canonicalFixture());
  const byKey = new Map(selected.rows.map((row) => [row.key, row]));
  assert.equal(byKey.get("rosterDesirability").value, "84.0");
  assert.equal(byKey.get("desirableOutcomeFrequency").value, "19.0%");
  assert.equal(byKey.get("dualPathDepth").value, "42.0%");
});

test("missing Financial relativeScore never falls back into publicScore", () => {
  const stale = financialFixture();
  delete stale.relativeScore;
  for (const component of Object.values(stale.components)) {
    delete component.relativeScore;
  }

  const selected = selectFinancialRipV3Breakdown(stale);
  assert.equal(selected.score, 48.25, "absolute model score remains available for audit");
  assert.equal(selected.publicScore, null);
  assert.equal(selected.publicScoreLabel, "—");
  assert.equal(selected.publicAvailable, false);
  assert.ok(selected.rows.every((row) => row.publicScore === null));
  assert.ok(selected.rows.every((row) => row.absoluteScore !== null));
});

test("missing Collector Appeal relativeScore never falls back into publicScore", () => {
  const stale = canonicalFixture();
  delete stale.publicRipContractV7.collectorAppeal.relativeScore;

  const selected = selectCollectorAppealBreakdown(stale);
  assert.equal(selected.score, 67.3, "absolute model score remains available for audit");
  assert.equal(selected.publicScore, null);
  assert.equal(selected.publicScoreLabel, "—");
  assert.equal(selected.publicAvailable, false);
});
