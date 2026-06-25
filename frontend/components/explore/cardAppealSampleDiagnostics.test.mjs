import test from "node:test";
import assert from "node:assert/strict";

import { getCardAppealSampleDiagnostics } from "./cardAppealSampleDiagnostics.mjs";

test("card appeal sample diagnostics separate priced cards from appeal-scored cards", () => {
  const diagnostics = getCardAppealSampleDiagnostics([
    {
      name: "Pokemon with camel fields",
      supertype: "Pokémon",
      marketPrice: 12,
      adjustedCardAppealScore: 88,
    },
    {
      name: "Trainer with price only",
      supertype: "Trainer",
      market_price: 4,
    },
    {
      name: "Pokemon with snake price only",
      supertype: "Pokemon",
      current_price: 2,
    },
    {
      name: "Item with score and current price",
      supertype: "Item",
      currentPrice: 3,
      adjusted_card_appeal_score: 40,
    },
    {
      name: "Energy with zero price",
      supertype: "Energy",
      current_price: 0,
    },
  ]);

  assert.deepEqual(diagnostics, {
    totalCards: 5,
    pricedCards: 4,
    appealScoredCards: 2,
    pricedAppealCards: 2,
    excludedPricedNoAppeal: 2,
    excludedNonPokemonPriced: 1,
  });
});

test("card appeal sample diagnostics handle missing or non-array inputs", () => {
  assert.deepEqual(getCardAppealSampleDiagnostics(null), {
    totalCards: 0,
    pricedCards: 0,
    appealScoredCards: 0,
    pricedAppealCards: 0,
    excludedPricedNoAppeal: 0,
    excludedNonPokemonPriced: 0,
  });
});
