import test from "node:test";
import assert from "node:assert/strict";

import { selectTopChaseCards } from "./topChaseCardsSelector.mjs";

test("top chase selector removes non-renderable skeleton rows", () => {
  const selected = selectTopChaseCards({
    topChaseCards: [
      {},
      { cardId: "card-1", name: "Mega Chase", marketPrice: "42.50" },
    ],
  });

  assert.equal(selected.cards.length, 1);
  assert.equal(selected.cards[0].name, "Mega Chase");
  assert.equal(selected.cards[0].marketPrice, 42.5);
  assert.equal(selected.diagnostics.emptyRenderableRows, 1);
});
