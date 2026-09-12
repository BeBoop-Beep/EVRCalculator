import assert from "node:assert/strict";
import test from "node:test";
import { projectSetRankingsLensTargets } from "./setRankingsLensProjection.mjs";

const source = {
  target_type: "set",
  target_id: "ascended",
  name: "Ascended Heroes",
  setRipV1: { score: 12.34, publicScore: 38.73, tier: "B", rank: 4, cohortSize: 22, rankable: true, methodologyVersion: "overall_rip_v12" },
  overallRipV12: { score: 36.8998, leaderNormalizedScore: 36.89, rank: 17, cohortSize: 22, status: "ready", components: { privateWeightingInput: 999 } },
  financialRipV4: { leaderNormalizedScore: 30.066, rank: 19, cohortSize: 22, status: "ready" },
  chaseAccessibility: { value: 0.0037, modelScore: 71.25, publicScore: 38.37, setRank: 21, setCohortSize: 22, cohortId: "run-22", status: "ready" },
  publicRipContractV11: {
    overallRip: { score: 36.8998, rank: 17, cohortSize: 22, tier: "C" },
    financialRip: { score: 30.066, rank: 19, cohortSize: 22, tier: "D" },
    collectorAppeal: { score: 99.0942, rank: 1, cohortSize: 22, tier: "S" },
    audit: { weights: { forbidden: true } },
  },
  publicCollectorAppealContractV1: {
    collectorAppeal: { leaderNormalizedScore: 99.0942, absoluteScore: 88.1, rank: 1, cohortSize: 22, tier: "S" },
    components: {
      rosterDesirability: { score: 82.1, rank: 2, modeledPokemon: ["secret"] },
      desirableOutcomeFrequency: { rawValue: 0.14, displayPercent: 14, status: "available", statusReason: null, impliedOddsOneInN: 7.1 },
      treatment: { score: 999 }, scarcity: { score: 998 }, artist: { score: 997 },
    },
  },
  overallRipV12Composition: { weights: { financial: 0.86 }, effectiveWeights: { financial: 1 } },
};

test("Basic receives public Set RIP identity but no Plus peer-pillar intelligence", () => {
  const row = projectSetRankingsLensTargets([source], { rankingsIntelligence: false })[0];
  // PUBLIC_BLOCK_LEAVES.setRipV1 intentionally excludes `score` — this is the
  // entitlement-leak fix (a prior contract leaked the raw score to Basic/
  // anonymous viewers). Only the public leaderboard leaves survive.
  assert.deepEqual(row.setRipV1, {
    publicScore: 38.73,
    tier: "B",
    rank: 4,
    cohortSize: 22,
    rankable: true,
    methodologyVersion: "overall_rip_v12",
  });
  assert.equal(row.setRipV1.score, undefined, "raw score must not leak to a Basic/anonymous viewer");
  assert.equal(row.overallRipV12, undefined);
  assert.equal(row.financialRipV4, undefined);
  assert.equal(row.publicRipContractV11, undefined);
  assert.equal(row.publicCollectorAppealContractV1, undefined);
  assert.equal(row.chaseAccessibility, undefined);
});

test("Plus preserves distinct V12 peers and normalizes authoritative Chase for ExploreTableClient", () => {
  const row = projectSetRankingsLensTargets([source], { rankingsIntelligence: true })[0];
  assert.equal(row.setRipV1.score, 12.34);
  assert.equal(row.overallRipV12.score, 36.8998);
  assert.equal(row.financialRipV4.leaderNormalizedScore, 30.066);
  assert.equal(row.publicCollectorAppealContractV1.collectorAppeal.leaderNormalizedScore, 99.0942);
  assert.deepEqual(row.setRipV1.chaseAccessibility, {
    value: 0.0037, modelScore: 71.25, publicScore: 38.37,
    setRank: 21, setCohortSize: 22, cohortId: "run-22", status: "ready",
  });
  assert.equal(row.chaseAccessibility, undefined);
  assert.equal(row.publicRipContractV11.audit, undefined);
  assert.deepEqual(row.publicCollectorAppealContractV1.components, {
    rosterDesirability: { score: 82.1 },
    desirableOutcomeFrequency: { rawValue: 0.14, displayPercent: 14, status: "available", statusReason: null },
  });
  assert.equal(row.overallRipV12Composition, undefined);
});

test("missing publicScore stays missing and never falls back to raw or model score", () => {
  const missing = { ...source, chaseAccessibility: { value: 0.9, modelScore: 88, status: "ready" } };
  const row = projectSetRankingsLensTargets([missing], { rankingsIntelligence: true })[0];
  assert.equal(row.setRipV1.chaseAccessibility.publicScore, undefined);
});
