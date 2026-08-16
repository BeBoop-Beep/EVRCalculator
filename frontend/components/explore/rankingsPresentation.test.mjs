import test from "node:test";
import assert from "node:assert/strict";
import { explainRankingsLeader, readOptionalRankingsChase } from "./rankingsPresentation.mjs";

const row = (overrides = {}) => ({ overallRipV8: { rank: 1, cohortSize: 8, relativeScore: 92, tier: "S" }, financialRipV3: { rank: 1, cohortSize: 8, relativeScore: 90, tier: "S" }, publicRipContractV8: { collectorAppeal: { rank: 2, cohortSize: 8, relativeScore: 88, tier: "S" } }, prob_profit: 0.2, expected_loss_when_losing: 3, mean_value: 5, ...overrides });

test("#1 explanation uses authoritative ranks and cohort comparisons without a composite score", () => {
  assert.equal(explainRankingsLeader([row(), row({ financialRipV3: { rank: 4, cohortSize: 8 }, prob_profit: 0.1 }), row({ financialRipV3: { rank: 6, cohortSize: 8 }, prob_profit: 0.05 })]), "Top-tier financial outcomes + elite collector appeal.");
});
test("#1 explanation is null for an empty ranking", () => assert.equal(explainRankingsLeader([]), null));
test("optional chase adapter renders nothing when canonical fields are absent", () => assert.equal(readOptionalRankingsChase(row()), null));
test("optional chase adapter passes through fields without calculating odds", () => assert.deepEqual(readOptionalRankingsChase({ topChase: { name: "Moonbreon", marketValue: "999", oneInPacks: "1200" } }), { name: "Moonbreon", marketValue: 999, oneInPacks: 1200, packsTo50: null, spendTo50: null }));
