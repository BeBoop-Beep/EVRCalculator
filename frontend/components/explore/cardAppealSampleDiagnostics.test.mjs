import test from "node:test";
import assert from "node:assert/strict";

import {
  getCardAppealSampleDiagnostics,
  resolvePreferredCardAppealCorrelation,
} from "./cardAppealSampleDiagnostics.mjs";

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

test("card appeal correlation resolver prefers page-level correlation over checklist state", () => {
  const pageCorrelation = { n: 12, plotRows: [{ name: "Page Row", marketPrice: 10, cardAppealScore: 80 }] };
  const checklistCorrelation = { n: 1, plotRows: [{ name: "Checklist Row", marketPrice: 2, cardAppealScore: 20 }] };

  const selected = resolvePreferredCardAppealCorrelation({
    explorePayload: { cardAppealMarketPriceCorrelation: pageCorrelation },
    checklistState: { cardAppealMarketPriceCorrelation: checklistCorrelation },
  });

  assert.equal(selected, pageCorrelation);
});

test("card appeal correlation resolver reads nested cards payload correlation", () => {
  const nestedCorrelation = { plotted_count: 9, rows: [{ name: "Nested Row", marketPrice: 4, cardAppealScore: 55 }] };

  const selected = resolvePreferredCardAppealCorrelation({
    explorePayload: { set_cards: { card_appeal_market_price_correlation: nestedCorrelation } },
  });

  assert.equal(selected, nestedCorrelation);
});
