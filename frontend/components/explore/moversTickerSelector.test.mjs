import test from "node:test";
import assert from "node:assert/strict";
import {
  MOVERS_TICKER_MAX_ITEMS,
  getMoversTickerTrendValue,
  selectMoversTickerItems,
} from "./moversTickerSelector.mjs";

const card = (id, percent, amount = null, extra = {}) => ({
  id,
  name: id,
  change7dPercent: percent,
  change7dAmount: amount,
  ...extra,
});

test("prefers the complete eligible all list over capped direction arrays", () => {
  const positive = card("positive", 100, 10);
  const negatives = Array.from({ length: 22 }, (_, index) => card(`negative-${index + 1}`, -(index + 1), -(index + 1)));
  const entry = {
    heatingUp: [positive],
    coolingOff: negatives.slice(0, 5),
    all: [positive, ...negatives],
  };

  const result = selectMoversTickerItems(entry);

  assert.equal(result.length, MOVERS_TICKER_MAX_ITEMS);
  assert.ok(result.some((item) => item.card.id === "negative-22"));
  assert.ok(!result.some((item) => item.card.id === "negative-1"));
});

test("ranks one positive with the nine largest of twenty-two negatives", () => {
  const positive = card("positive", 100, 20);
  const negatives = Array.from({ length: 22 }, (_, index) => card(`negative-${index + 1}`, -(index + 1), -(index + 1)));

  const result = selectMoversTickerItems({ all: [positive, ...negatives] });

  assert.equal(result.length, 10);
  assert.equal(result.filter((item) => item.movement.percent > 0).length, 1);
  assert.deepEqual(
    result.filter((item) => item.movement.percent < 0).map((item) => item.card.id),
    Array.from({ length: 9 }, (_, index) => `negative-${22 - index}`)
  );
});

test("returns ten positives when no negative candidates exist", () => {
  const result = selectMoversTickerItems({
    all: Array.from({ length: 12 }, (_, index) => card(`positive-${index + 1}`, index + 1, index + 1)),
  });

  assert.equal(result.length, 10);
  assert.ok(result.every((item) => item.movement.percent > 0));
});

test("deduplicates canonical card identities after ranking", () => {
  const result = selectMoversTickerItems({
    all: [
      card("variant-a", 5, 1, { canonicalCardId: "canonical-card" }),
      card("variant-b", -20, -4, { canonicalCardId: "canonical-card" }),
      card("other", 3, 2, { canonicalCardId: "other-card" }),
    ],
  });

  assert.deepEqual(result.map((item) => item.card.id), ["variant-b", "other"]);
});

test("excludes zero, null, and non-finite movement percentages", () => {
  const result = selectMoversTickerItems({
    all: [card("zero", 0), card("null", null), card("nan", "not-a-number"), card("valid", -4, -1)],
  });

  assert.deepEqual(result.map((item) => item.card.id), ["valid"]);
});

test("uses stable percentage, amount, then identity tie ordering", () => {
  const result = selectMoversTickerItems({
    all: [
      card("percent-first", -11, -1),
      card("amount-last", 10, 1),
      card("identity-c", -10, -2),
      card("identity-a", 10, 2),
    ],
  });

  assert.deepEqual(result.map((item) => item.card.id), ["percent-first", "identity-a", "identity-c", "amount-last"]);
});

test("uses movements before legacy direction arrays when all is unavailable", () => {
  const result = selectMoversTickerItems({
    movements: [card("movement-contract", 20, 2)],
    heatingUp: [card("legacy", 99, 9)],
    coolingOff: [],
  });

  assert.deepEqual(result.map((item) => item.card.id), ["movement-contract"]);
});

test("falls back to merged heating and cooling arrays for legacy payloads", () => {
  const result = selectMoversTickerItems({
    heatingUp: [card("gainer", 5, 1)],
    coolingOff: [card("decliner", -8, -2)],
  });

  assert.deepEqual(result.map((item) => item.card.id), ["decliner", "gainer"]);
});

test("Chaos Rising-shaped fixture fills ten positions from 23 eligible rows", () => {
  const cardsWith7dDeltas = Array.from({ length: 122 }, (_, index) =>
    card(`chaos-card-${index + 1}`, index === 0 ? 100 : -(index + 1), index === 0 ? 10 : -(index + 1))
  );
  const eligibleMovements = cardsWith7dDeltas.slice(0, 23);
  const chaosRisingMovers = {
    heatingUp: eligibleMovements.slice(0, 1),
    coolingOff: eligibleMovements.slice(1, 6),
    all: eligibleMovements,
  };

  assert.equal(cardsWith7dDeltas.length, 122);
  assert.equal(chaosRisingMovers.all.length, 23);
  assert.equal(chaosRisingMovers.heatingUp.length, 1);
  assert.equal(chaosRisingMovers.coolingOff.length, 5);
  assert.equal(selectMoversTickerItems(chaosRisingMovers).length, 10);
});

test("ticker trend direction value covers positive, negative, zero, and unavailable movement", () => {
  assert.equal(getMoversTickerTrendValue({ amount: 1.25, percent: 9 }), 1.25);
  assert.equal(getMoversTickerTrendValue({ amount: -0.5, percent: -4 }), -0.5);
  assert.equal(getMoversTickerTrendValue({ amount: 0, percent: 2 }), 0);
  assert.equal(getMoversTickerTrendValue({ amount: null, percent: null }), null);
  assert.equal(getMoversTickerTrendValue({ percent: 3.2 }), 3.2);
});
