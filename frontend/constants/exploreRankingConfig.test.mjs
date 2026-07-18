import test from "node:test";
import assert from "node:assert/strict";

import {
  EXPLORE_RANKING_MODES,
  getAbsoluteScoreField,
  getAbsoluteScoreForMode,
  getRelativeScoreField,
  getRelativeScoreForMode,
  getRankForMode,
  getScoreForMode,
} from "./exploreRankingConfig.js";

const TARGET = {
  rip: { score: 29.07, relativeScore: 82.4, rank: 4, tier: "A" },
  ripCore: { score: 22.32, relativeScore: 61.8, rank: 12, tier: "B" },
  universalSetDesirability: { score: 95.5, rank: 1 },
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
