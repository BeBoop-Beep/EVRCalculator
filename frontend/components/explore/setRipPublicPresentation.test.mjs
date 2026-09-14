import assert from "node:assert/strict";
import test from "node:test";
import { formatPublicRipScore } from "../../constants/exploreRankingConfig.mjs";
import { readPublicSetRip } from "./setRipPublicPresentation.mjs";

test("public Set Rankings renders publicScore, rank, and tier without paid score", () => {
  const target = { setRipV1: { publicScore: 83.6, rank: 4, tier: "A", cohortSize: 21 } };
  const result = readPublicSetRip(target);
  assert.deepEqual(result, { publicScore: 83.6, rank: 4, tier: "A", cohortSize: 21 });
  assert.equal(formatPublicRipScore(result.publicScore), "8.4");
  assert.equal(`#${result.rank}`, "#4");
  assert.equal(result.tier, "A");
  assert.equal("score" in target.setRipV1, false);
});

test("missing public values remain null while legacy score is a compatibility fallback", () => {
  assert.equal(readPublicSetRip({ setRipV1: { publicScore: null, score: null, rank: null } }).publicScore, null);
  assert.equal(readPublicSetRip({ setRipV1: { publicScore: null, score: 99 } }).publicScore, null);
  assert.equal(readPublicSetRip({ setRipV1: { score: 72 } }).publicScore, 72);
});
