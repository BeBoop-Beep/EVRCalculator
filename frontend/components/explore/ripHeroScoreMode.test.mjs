import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  RIP_CORE_MODE,
  RIP_SCORE_MODE,
  hasCanonicalRipContract,
  hasRipCorePresentationContract,
  selectRipHeroScoreMode,
} from "./ripHeroScoreMode.mjs";

// Canonical backend objects, shaped like the explore/insights contract.
// `score` is the raw formula output (the model/absolute score); `relativeScore`
// is the cohort-relative 0-100 PUBLIC score. The hero must surface RELATIVE as
// its primary `score` and keep the absolute as a secondary diagnostic.
// Legacy fields are ALSO present, with deliberately different values, so every
// test doubles as proof that the legacy fields are not being read.
const target = {
  rip: {
    score: 82.2094,
    relativeScore: 96.7,
    rank: 1,
    tier: "S",
    cohortSize: 21,
    interpretation: { label: "Elite opener", summary: "Final summary", severity: "positive" },
  },
  ripCore: {
    score: 83.11,
    relativeScore: 90.4,
    rank: 2,
    tier: "S",
    cohortSize: 21,
    interpretation: { label: "Financially strong", summary: "Core summary", severity: "positive" },
  },
  // Legacy fields — never to be read again. Values chosen to be obviously
  // different from the canonical ones above.
  pack_score: 12.3,
  relative_pack_score: 98.4,
  pack_rank: 99,
  pack_tier: "F",
  relative_rip_core_score: 55.5,
  rip_core_rank: 88,
  rip_core_tier: "D",
  rip_rank_with_desirability: 77,
};

test("RIP Score hero surfaces the RELATIVE public score, absolute stays secondary", () => {
  const selected = selectRipHeroScoreMode({ mode: RIP_SCORE_MODE, target });

  // Primary public score is the cohort-relative number.
  assert.equal(selected.score, 96.7);
  assert.equal(selected.relativeScore, 96.7);
  // The raw 90/10 formula output remains available as a secondary diagnostic,
  // never promoted to the primary `score`.
  assert.equal(selected.absoluteScore, 82.2094);
  assert.notEqual(selected.score, selected.absoluteScore);
  assert.equal(selected.rank, 1);
  assert.equal(selected.tier, "S");
  assert.equal(selected.cohortSize, 21);
  assert.equal(selected.available, true);
  assert.equal(selected.interpretation.label, "Elite opener");
  assert.match(selected.helper, /Collector Appeal/);
  // Legacy values must not leak through under any label.
  assert.notEqual(selected.score, 98.4);
  assert.notEqual(selected.absoluteScore, 12.3);
  assert.notEqual(selected.rank, 99);
  assert.notEqual(selected.rank, 77);
});

test("RIP Core hero surfaces the RELATIVE public score with its own placement", () => {
  const selected = selectRipHeroScoreMode({ mode: RIP_CORE_MODE, target });

  assert.equal(selected.mode, RIP_CORE_MODE);
  assert.equal(selected.score, 90.4);
  assert.equal(selected.relativeScore, 90.4);
  assert.equal(selected.absoluteScore, 83.11);
  assert.equal(selected.rank, 2);
  assert.equal(selected.tier, "S");
  assert.equal(selected.cohortSize, 21);
  assert.equal(selected.interpretation.label, "Financially strong");
  assert.match(selected.helper, /without Collector Appeal/);
  assert.notEqual(selected.score, 55.5);
  assert.notEqual(selected.rank, 88);
});

test("a missing canonical contract renders unavailable — never the legacy score", () => {
  const legacyOnly = {
    pack_score: 89.0,
    relative_pack_score: 98.4,
    pack_rank: 3,
    pack_tier: "S",
    relative_rip_core_score: 61.2,
    rip_core_rank: 15,
  };
  const selected = selectRipHeroScoreMode({ mode: RIP_SCORE_MODE, summary: legacyOnly });

  assert.equal(selected.score, null);
  assert.equal(selected.relativeScore, null);
  assert.equal(selected.absoluteScore, null);
  assert.equal(selected.rank, null);
  assert.equal(selected.tier, null);
  assert.equal(selected.available, false);
  assert.equal(hasCanonicalRipContract(legacyOnly), false);
});

test("a present absolute but missing relative renders unavailable, never promoting the model score", () => {
  // A stale payload carrying only the raw formula output must NOT silently show
  // the model score as the public number.
  const stale = { rip: { score: 82.2, rank: 1, tier: "S", cohortSize: 21 } };
  const selected = selectRipHeroScoreMode({ mode: RIP_SCORE_MODE, target: stale });

  assert.equal(selected.score, null);
  assert.equal(selected.relativeScore, null);
  assert.equal(selected.absoluteScore, 82.2);
  assert.equal(selected.available, false);
});

test("an unavailable canonical RIP carries the backend's status through", () => {
  const hidden = {
    rip: { score: null, relativeScore: null, status: "incomplete_missing_desirability" },
  };
  const selected = selectRipHeroScoreMode({ mode: RIP_SCORE_MODE, target: hidden });

  assert.equal(selected.score, null);
  assert.equal(selected.available, false);
  assert.equal(selected.status, "incomplete_missing_desirability");
});

test("RIP Core mode falls back to RIP Score MODE when core is absent, without inventing a score", () => {
  const ripOnly = { rip: { score: 70.0, relativeScore: 88.0, rank: 5, tier: "A", cohortSize: 21 } };
  const selected = selectRipHeroScoreMode({ mode: RIP_CORE_MODE, target: ripOnly });

  assert.equal(selected.mode, RIP_SCORE_MODE);
  assert.equal(selected.score, 88.0);
  assert.equal(selected.absoluteScore, 70.0);
  assert.equal(hasRipCorePresentationContract(ripOnly), false);
});

test("the payload source (set-page snapshot) is honored alongside the target", () => {
  const selected = selectRipHeroScoreMode({
    mode: RIP_SCORE_MODE,
    payload: { rip: { score: 56.7918, relativeScore: 12.5, rank: 21, tier: "F", cohortSize: 21 } },
  });

  assert.equal(selected.score, 12.5);
  assert.equal(selected.absoluteScore, 56.7918);
  assert.equal(selected.rank, 21);
  assert.equal(selected.cohortSize, 21);
});

test("rank stays numerical rather than displaying the tier letter", () => {
  const selected = selectRipHeroScoreMode({ mode: RIP_SCORE_MODE, target });
  assert.notEqual(String(selected.rank), selected.tier);
});

test("source-level guard: the selector never mentions the legacy score fields", () => {
  const source = readFileSync(fileURLToPath(new URL("./ripHeroScoreMode.mjs", import.meta.url)), "utf8");
  const code = source
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
  for (const banned of [
    '"pack_score"',
    '"relative_pack_score"',
    '"packScore"',
    '"relativePackScore"',
    '"pack_rank"',
    '"packRank"',
    '"pack_tier"',
    '"packTier"',
    '"relative_rip_core_score"',
    '"relativeRipCoreScore"',
    '"rip_rank_with_desirability"',
    '"rip_rank_without_desirability"',
  ]) {
    assert.ok(!code.includes(banned), `ripHeroScoreMode.mjs reads legacy field ${banned}`);
  }
});
