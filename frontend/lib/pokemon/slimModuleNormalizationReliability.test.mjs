import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeMarketMoversPayload,
  normalizeOverviewPayload,
  normalizeTopChasePayload,
} from "./pokemonSetMarketClient.js";

// ---------------------------------------------------------------------------
// Even when a slim module returns HTTP 200, normalization must not throw the
// payload away. These tests pin the three failure shapes the Overview redesign
// surfaced: priced Top Chase rows rendering blank prices, the Movers Top 10
// losing members, and Opening Profit vs Cost losing its series.
// ---------------------------------------------------------------------------

function topChaseCard(index, overrides = {}) {
  return {
    cardId: `card-${index}`,
    name: `Chase Card ${index}`,
    rank: index,
    marketPrice: 100 + index,
    priceHistory: [
      { date: "2026-07-01", marketPrice: 90 + index },
      { date: "2026-07-02", marketPrice: 100 + index },
    ],
    ...overrides,
  };
}

// --- Top Chase -------------------------------------------------------------

test("top chase accepts both topChaseCards and top_chase_cards", () => {
  const camel = normalizeTopChasePayload({ topChaseCards: [topChaseCard(1)] });
  const snake = normalizeTopChasePayload({ top_chase_cards: [topChaseCard(1)] });
  assert.equal(camel.cards.length, 1);
  assert.equal(snake.cards.length, 1);
  assert.equal(snake.cards[0].name, "Chase Card 1");
});

test("ten returned top chase cards do not become zero priced cards", () => {
  const payload = normalizeTopChasePayload({
    topChaseCards: Array.from({ length: 10 }, (_, index) => topChaseCard(index + 1)),
  });
  assert.equal(payload.cards.length, 10, "all ten rows must survive normalization");
  const priced = payload.cards.filter((card) => typeof card.marketPrice === "number" && card.marketPrice > 0);
  assert.equal(priced.length, 10, "every returned price must survive normalization");
});

test("top chase price aliases all normalize onto marketPrice", () => {
  const cases = [
    { marketPrice: 42 },
    { market_price: 42 },
    { currentPrice: 42 },
    { current_price: 42 },
    { estimatedMarketPrice: 42 },
    { estimated_market_price: 42 },
  ];
  cases.forEach((priceFields) => {
    const payload = normalizeTopChasePayload({
      topChaseCards: [{ cardId: "c", name: "Card", ...priceFields }],
    });
    assert.equal(
      payload.cards[0].marketPrice,
      42,
      `price alias ${Object.keys(priceFields)[0]} must normalize onto marketPrice`
    );
  });
});

test("a top chase card is not discarded because one optional field is missing", () => {
  const payload = normalizeTopChasePayload({
    topChaseCards: [
      { cardId: "c1", name: "No image or rarity", marketPrice: 12 },
      { cardId: "c2", name: "No price at all" },
    ],
  });
  assert.equal(payload.cards.length, 2, "a missing optional field must not drop the row");
  assert.equal(payload.cards[0].marketPrice, 12);
  assert.equal(payload.cards[1].marketPrice, null, "a genuinely absent price stays null, never a fake 0");
});

test("top chase card history aliases stay attached", () => {
  const fromCamel = normalizeTopChasePayload({ topChaseCards: [topChaseCard(1)] });
  assert.equal(fromCamel.cards[0].priceHistory.length, 2);

  const fromSnake = normalizeTopChasePayload({
    topChaseCards: [
      {
        cardId: "c1",
        name: "Snake history",
        marketPrice: 10,
        price_history: [{ date: "2026-07-01", market_price: 9 }],
      },
    ],
  });
  assert.equal(fromSnake.cards[0].priceHistory.length, 1);
  assert.equal(fromSnake.cards[0].priceHistory[0].marketPrice, 9);
});

test("top chase histories supplied in the sibling map attach to their card", () => {
  const payload = normalizeTopChasePayload({
    topChaseCards: [{ cardId: "c1", name: "Mapped history", marketPrice: 10 }],
    top_chase_card_histories: {
      c1: [
        { date: "2026-07-01", marketPrice: 8 },
        { date: "2026-07-02", marketPrice: 9 },
      ],
    },
  });
  assert.equal(payload.cards[0].priceHistory.length, 2);
});

// --- Market Movers ---------------------------------------------------------

function moverCard(index) {
  return {
    cardId: `mover-${index}`,
    name: `Mover ${index}`,
    currentPrice: 50 + index,
    changeAmount: index,
    changePercent: index,
  };
}

test("movers accepts both marketMovers and market_movers", () => {
  const all = Array.from({ length: 10 }, (_, index) => moverCard(index + 1));
  const camel = normalizeMarketMoversPayload({ marketMovers: { all, window: "7D" } });
  const snake = normalizeMarketMoversPayload({ market_movers: { all, window: "7D" } });
  assert.equal(camel.all.length, 10);
  assert.equal(snake.all.length, 10);
});

test("the normalized movers payload stays a flat structure with the complete Top 10", () => {
  const payload = normalizeMarketMoversPayload({
    marketMovers: {
      window: "7D",
      windowDays: 7,
      all: Array.from({ length: 10 }, (_, index) => moverCard(index + 1)),
    },
  });
  // Flat: the ticker selector reads payload.all / payload.window directly.
  assert.ok(Array.isArray(payload.all), "all must be a top-level array on the normalized payload");
  assert.equal(payload.all.length, 10, "the complete Top 10 must survive normalization");
  assert.equal(payload.window, "7D", "the fixed Overview window must be preserved");
  assert.equal(payload.windowDays, 7);
});

test("movers membership comes from all, not from heating/cooling alone", () => {
  const payload = normalizeMarketMoversPayload({
    marketMovers: {
      window: "7D",
      all: Array.from({ length: 10 }, (_, index) => moverCard(index + 1)),
      heatingUp: [moverCard(1)],
      coolingOff: [moverCard(2)],
    },
  });
  assert.equal(payload.all.length, 10);
  assert.equal(payload.heatingUp.length, 1);
  assert.equal(payload.coolingOff.length, 1);
});

test("movers falls back to heating+cooling when all is absent", () => {
  const payload = normalizeMarketMoversPayload({
    marketMovers: {
      window: "7D",
      heating_up: [moverCard(1), moverCard(2)],
      cooling_off: [moverCard(3)],
    },
  });
  assert.equal(payload.all.length, 3);
});

test("7D movers carry their 7D movement fields", () => {
  const payload = normalizeMarketMoversPayload({
    marketMovers: { window: "7D", all: [moverCard(1)] },
  });
  const [card] = payload.all;
  assert.equal(card.window, "7D");
  assert.equal(card.change7dAmount, 1);
  assert.ok(card.movement7d, "the 7D movement object must be attached for the ticker");
});

// --- Opening Profit vs Cost ------------------------------------------------

function performancePoint(date, overrides = {}) {
  return {
    snapshot_date: date,
    pack_cost: 4,
    mean_value: 5,
    median_value: 3,
    mean_value_to_cost_ratio: 1.25,
    median_value_to_cost_ratio: 0.75,
    p95_value_to_cost_ratio: 3.5,
    ...overrides,
  };
}

test("overview preserves performanceVsCostHistory", () => {
  const payload = normalizeOverviewPayload({
    set: { id: "s" },
    performanceVsCostHistory: [performancePoint("2026-07-01"), performancePoint("2026-07-02")],
  });
  assert.equal(payload.performanceVsCostHistory.length, 2);
});

test("overview accepts the snake_case performance_vs_cost_history alias", () => {
  const payload = normalizeOverviewPayload({
    set: { id: "s" },
    performance_vs_cost_history: [performancePoint("2026-07-01")],
  });
  assert.equal(
    payload.performanceVsCostHistory.length,
    1,
    "a snake_cased backend response must not silently render as no data"
  );
});

test("opening profit vs cost retains all three series on every point", () => {
  const payload = normalizeOverviewPayload({
    set: { id: "s" },
    performanceVsCostHistory: [performancePoint("2026-07-01"), performancePoint("2026-07-02")],
  });
  payload.performanceVsCostHistory.forEach((point) => {
    assert.equal(typeof point.meanValueToCostRatio, "number", "mean series must survive");
    assert.equal(typeof point.medianValueToCostRatio, "number", "median series must survive");
    assert.equal(typeof point.p95ValueToCostRatio, "number", "p95 series must survive");
  });
});

test("overview accepts snake_case set value histories and available scopes", () => {
  const payload = normalizeOverviewPayload({
    set: { id: "s" },
    set_value_histories_by_scope: { standard: [{ date: "2026-07-01", set_value: 100 }] },
    available_scopes: [{ key: "standard", label: "Checklist", latest_date: "2026-07-01" }],
    latest_market_date: "2026-07-01",
  });
  assert.equal(payload.setValueHistoriesByScope.standard.length, 1);
  assert.equal(payload.availableScopes[0].latestDate, "2026-07-01");
  assert.equal(payload.latestMarketDate, "2026-07-01");
});

test("normalization never manufactures points for an empty history", () => {
  const payload = normalizeOverviewPayload({ set: { id: "s" }, performanceVsCostHistory: [] });
  assert.deepEqual(payload.performanceVsCostHistory, [], "an empty history must stay empty, not be padded");
});
