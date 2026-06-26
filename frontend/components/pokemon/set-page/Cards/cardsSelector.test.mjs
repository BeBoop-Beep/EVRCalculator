import test from "node:test";
import assert from "node:assert/strict";

import { selectCards } from "./cardsSelector.mjs";

test("cards selector normalizes prices and demand fields", () => {
  const selected = selectCards({
    cards: [
      { id: "a", name: "A", current_price: "3.5", pokemon_desirability_score: "88" },
      { name: "" },
    ],
  });

  assert.equal(selected.cards.length, 1);
  assert.equal(selected.cards[0].currentPrice, 3.5);
  assert.equal(selected.cards[0].subjectDemandScore, 88);
  assert.equal(selected.diagnostics.pricedRows, 1);
  assert.equal(selected.diagnostics.demandRows, 1);
});
