import test from "node:test";
import assert from "node:assert/strict";
import { readOptionalRankingsChase } from "./rankingsPresentation.mjs";

const row = (overrides = {}) => ({ overallRipV8: { rank: 1, cohortSize: 8, relativeScore: 92, tier: "S" }, financialRipV3: { rank: 1, cohortSize: 8, relativeScore: 90, tier: "S" }, publicRipContractV8: { collectorAppeal: { rank: 2, cohortSize: 8, relativeScore: 88, tier: "S" } }, prob_profit: 0.2, expected_loss_when_losing: 3, mean_value: 5, ...overrides });

test("optional chase adapter renders nothing when canonical fields are absent", () => assert.equal(readOptionalRankingsChase(row()), null));
test("optional chase adapter passes through the canonical decision contract without calculating odds", () => assert.deepEqual(readOptionalRankingsChase({ ripDecision: { topChase: { cardName: "Moonbreon", currentMarketPrice: "999", impliedOddsOneInN: "1200", packsFor50PercentChance: 832 } } }), { name: "Moonbreon", marketValue: 999, oneInPacks: 1200, packsTo50: 832 }));
test("rankings chase is independent from chance to beat cost", () => assert.deepEqual(readOptionalRankingsChase({ prob_profit: 0.095, rankingsChase: { cardName: "Magikarp", currentMarketPrice: 387.56, impliedOddsOneInN: 473 } }), { name: "Magikarp", marketValue: 387.56, oneInPacks: 473, packsTo50: null }));
