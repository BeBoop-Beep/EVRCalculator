import test from "node:test";
import assert from "node:assert/strict";

import {
  EXPLORE_RANKING_MODES,
  getAbsoluteScoreField,
  getAbsoluteScoreForMode,
  getRelativeScoreField,
  getRelativeScoreForMode,
  getRankForMode,
  getRankedSetCountField,
  getRankedSetCountForMode,
  getScoreForMode,
} from "./exploreRankingConfig.js";

const TARGET = {
  rip: {
    score: 29.07,
    relativeScore: 82.4,
    rank: 4,
    tier: "A",
    cohortSize: 21,
    financialRip: {
      components: {
        profit: { score: 40.1, rank: 6, tier: "B", cohortSize: 21 },
      },
    },
  },
  ripCore: { score: 22.32, relativeScore: 61.8, rank: 12, tier: "B", cohortSize: 21 },
  universalSetDesirability: { score: 95.5, rank: 1, rankedSetCount: 135 },
  mean_value_to_cost_ratio: 1.23,
  mean_value_to_cost_rank: 3,
};

test("overall mode exposes distinct absolute and relative fields", () => {
  assert.equal(getAbsoluteScoreField("overall"), "rip.score");
  assert.equal(getRelativeScoreField("overall"), "rip.relativeScore");
  assert.equal(getAbsoluteScoreForMode(TARGET, "overall"), 29.07);
  assert.equal(getRelativeScoreForMode(TARGET, "overall"), 82.4);
  assert.equal(getRankForMode(TARGET, "overall"), 4);
});

test("financial mode reads ripCore absolute and relative", () => {
  assert.equal(getAbsoluteScoreForMode(TARGET, "financial"), 22.32);
  assert.equal(getRelativeScoreForMode(TARGET, "financial"), 61.8);
  assert.equal(getRankForMode(TARGET, "financial"), 12);
});

test("absolute and relative are never the same field", () => {
  for (const mode of ["overall", "financial"]) {
    assert.notEqual(getAbsoluteScoreField(mode), getRelativeScoreField(mode));
  }
});

test("a mode without a relative field returns null for relative, keeps absolute", () => {
  // Pillars carry an absolute component score and a rank, but no relativeScore.
  assert.equal(getRelativeScoreForMode(TARGET, "profit"), null);
  assert.equal(getAbsoluteScoreField("profit"), "rip.financialRip.components.profit.score");
});

test("ratio-only modes expose no relative score", () => {
  // EV-to-cost and God Pull Upside are raw ratios; they must not fabricate one.
  for (const mode of ["averageReturn", "godPullUpside"]) {
    assert.equal(getRelativeScoreField(mode), null);
    assert.equal(getRelativeScoreForMode(TARGET, mode), null);
    assert.equal(EXPLORE_RANKING_MODES[mode].scoreFormat, "ratio");
  }
});

test("absolute score falls back to scoreField when no explicit absolute field", () => {
  // desirability mode defines only scoreField; absolute resolves to it.
  assert.equal(getAbsoluteScoreField("desirability"), "universalSetDesirability.score");
  assert.equal(getAbsoluteScoreForMode(TARGET, "desirability"), 95.5);
  assert.equal(getScoreForMode(TARGET, "desirability"), 95.5);
});

test("ranked-set count reads each mode's own cohort denominator", () => {
  // Overall/Financial denominators live on the RIP objects as cohortSize; the
  // desirability denominator is the ALL-SET rankedSetCount. They differ on
  // purpose, so a rank and its denominator always describe one population.
  assert.equal(getRankedSetCountField("overall"), "rip.cohortSize");
  assert.equal(getRankedSetCountForMode(TARGET, "overall"), 21);
  assert.equal(getRankedSetCountForMode(TARGET, "financial"), 21);
  assert.equal(getRankedSetCountForMode(TARGET, "profit"), 21);
  assert.equal(getRankedSetCountForMode(TARGET, "desirability"), 135);
});

test("ratio-only modes expose no ranked-set count field", () => {
  for (const mode of ["averageReturn", "godPullUpside"]) {
    assert.equal(getRankedSetCountField(mode), null);
    assert.equal(getRankedSetCountForMode(TARGET, mode), null);
  }
});

test("null-safe getters: missing objects never throw and return null", () => {
  const empty = {};
  for (const mode of ["overall", "financial", "profit", "desirability"]) {
    assert.equal(getAbsoluteScoreForMode(empty, mode), null);
    assert.equal(getRelativeScoreForMode(empty, mode), null);
    assert.equal(getRankForMode(empty, mode), null);
    assert.equal(getRankedSetCountForMode(empty, mode), null);
  }
});

test("missing relative but present absolute: relative null, absolute intact", () => {
  const partial = { rip: { score: 30.0, rank: 2, cohortSize: 21 } };
  assert.equal(getAbsoluteScoreForMode(partial, "overall"), 30.0);
  assert.equal(getRelativeScoreForMode(partial, "overall"), null);
  assert.equal(getRankForMode(partial, "overall"), 2);
});

test("missing absolute but present rank: absolute null, rank intact", () => {
  const partial = { rip: { relativeScore: 55.0, rank: 3, cohortSize: 21 } };
  assert.equal(getAbsoluteScoreForMode(partial, "overall"), null);
  assert.equal(getRelativeScoreForMode(partial, "overall"), 55.0);
  assert.equal(getRankForMode(partial, "overall"), 3);
});
