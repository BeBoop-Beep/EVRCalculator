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

test("top chase selector reads top market cards from snake-case market dashboard", () => {
  const selected = selectTopChaseCards({
    market_dashboard: {
      top_market_cards: [{ card_id: "card-1", card_name: "Market Chase", market_price: "99.99" }],
      market_movers: { heatingUp: [{ id: "hot-1" }], coolingOff: [], all: [{ id: "hot-1" }] },
    },
  });

  assert.equal(selected.cards.length, 1);
  assert.equal(selected.cards[0].name, "Market Chase");
  assert.equal(selected.cards[0].marketPrice, 99.99);
  assert.equal(selected.marketMovers.heatingUp.length, 1);
});
