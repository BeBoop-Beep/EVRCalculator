import test from "node:test";
import assert from "node:assert/strict";
import { familyEvidenceScores, familyTier, participatingFamilyCount, participatingFamilyScores, selectPreferredSetRipContract, setRipTier, whySetRanks } from "./SetRipFamilyBreakdown.jsx";

const sets = [
  { name: "Alpha", setRipV1: { score: 92, rank: 1, cohortSize: 20, familyScores: [{ family: "booster_box", score: 95, rank: 1, cohortSize: 20, skuCount: 2 }] } },
  { name: "Beta", setRipV1: { score: 84, rank: 4, cohortSize: 20, familyScores: [{ family: "booster_bundle", score: 82, rank: 4, cohortSize: 20, skuCount: 1 }] } },
  { name: "Gamma", setRipV1: { score: 76, rank: 9, cohortSize: 20, familyScores: [{ family: "elite_trainer_box", score: 75, rank: 9, cohortSize: 18, skuCount: 1 }] } },
];

test("three representative sets retain identical canonical values for every consumer", () => {
  assert.deepEqual(sets.map(({ setRipV1 }) => ({ score: setRipV1.score, rank: setRipV1.rank, tier: setRipTier(setRipV1) })), [
    { score: 92, rank: 1, tier: "S" },
    { score: 84, rank: 4, tier: "A" },
    { score: 76, rank: 9, tier: "B" },
  ]);
  for (const { setRipV1 } of sets) {
    const family = participatingFamilyScores(setRipV1)[0];
    assert.equal(familyTier(family), setRipV1 === sets[2].setRipV1 ? "B" : setRipTier(setRipV1));
    assert.ok(whySetRanks(setRipV1));
  }
});

test("invalid and empty family entries never produce placeholder modules", () => {
  assert.deepEqual(participatingFamilyScores({ familyScores: [{ family: "x" }, null] }), []);
  assert.deepEqual(participatingFamilyScores({ familyScores: {} }), []);
});

test("legacy family evidence is counted without fabricating ranking context", () => {
  const legacy = {
    participatingFamilyCount: 6,
    familyScores: [{ family: "booster_box", skuCount: 1, meanStanding: 1 }],
  };
  assert.equal(participatingFamilyCount(legacy), 6);
  assert.equal(familyEvidenceScores(legacy).length, 1);
  assert.deepEqual(participatingFamilyScores(legacy), []);
});

test("family count falls back to evidence only when the canonical count is absent", () => {
  assert.equal(participatingFamilyCount({ familyScores: [{ family: "booster_box" }] }), 1);
  assert.equal(participatingFamilyCount({ participatingFamilyCount: 0, familyScores: [{ family: "booster_box" }] }), 0);
});

test("the set page prefers an enriched selected target over a legacy explore payload", () => {
  const legacy = { score: 96, rank: 1, participatingFamilyCount: 6, familyScores: [{ family: "booster_box" }] };
  const enriched = { score: 96, rank: 1, cohortSize: 22, participatingFamilyCount: 1,
    familyScores: [{ family: "booster_box", skuCount: 1, score: 100, rank: 1, cohortSize: 15 }] };
  assert.equal(selectPreferredSetRipContract(legacy, enriched), enriched);
  assert.deepEqual(participatingFamilyScores(selectPreferredSetRipContract(legacy, enriched)), enriched.familyScores);
});
