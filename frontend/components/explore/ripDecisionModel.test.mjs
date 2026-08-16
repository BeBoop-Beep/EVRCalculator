import assert from "node:assert/strict";
import test from "node:test";
import { buildRipDecisionModel, selectRipDecisionFields } from "./ripDecisionModel.mjs";

test("opening economics map only authoritative summary fields", () => {
  const model = buildRipDecisionModel({
    summary: {
      pack_cost: 5.49,
      mean_value: 3.12,
      median_value: 1.08,
      prob_profit: 0.187,
      expected_loss_per_pack: 3.41,
    },
  });
  assert.equal(model.packCost, 5.49);
  assert.equal(model.expectedValue, 3.12);
  assert.equal(model.typicalOpening, 1.08);
  assert.equal(model.recoverCostProbability, 0.187);
  assert.equal(model.expectedLoss, 3.41);
});

test("missing optional chase fields degrade to a null presentation model", () => {
  const decision = selectRipDecisionFields({ summary: { pack_cost: 4.99 } });
  assert.equal(decision.topChase, null);
  assert.equal(decision.breakEvenValue, null);
  assert.deepEqual(decision.marketChaseCards, []);
});

test("published chase probability thresholds pass through without client calculations", () => {
  const decision = selectRipDecisionFields({
    canonical: {
      top_chase: {
        card_name: "Example ex",
        market_value: 250,
        probability_per_opening: 0.002,
        odds_denominator: 500,
        openings_for_50_percent: 347,
        openings_for_90_percent: 1151,
        spend_for_50_percent: 1731.53,
        spend_for_90_percent: 5743.49,
      },
    },
  });
  assert.deepEqual(decision.topChase, {
    name: "Example ex",
    imageUrl: null,
    marketValue: 250,
    probability: 0.002,
    oddsDenominator: 500,
    openings50: 347,
    openings90: 1151,
    spend50: 1731.53,
    spend90: 5743.49,
  });
});

test("market chase cards are capped for a compact responsive section", () => {
  const chaseCards = Array.from({ length: 7 }, (_, index) => ({ id: index, name: `Card ${index}` }));
  assert.equal(selectRipDecisionFields({ chaseCards }).marketChaseCards.length, 4);
});
