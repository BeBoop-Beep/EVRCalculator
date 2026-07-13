import test from "node:test";
import assert from "node:assert/strict";
import { getMoversTickerTrendValue, selectMoversTickerItems } from "./moversTickerSelector.mjs";

const card = (id, percent, extra = {}) => ({ id, name: id, change7dPercent: percent, ...extra });
const entry = (gainers, decliners) => ({ heatingUp: gainers, coolingOff: decliners });

test("selects five gainers and five decliners", () => {
  const result = selectMoversTickerItems(entry(
    Array.from({ length: 5 }, (_, i) => card(`g${i}`, i + 1)),
    Array.from({ length: 5 }, (_, i) => card(`d${i}`, -(i + 1)))
  ));
  assert.equal(result.length, 10);
  assert.equal(result.filter((item) => item.movement.percent > 0).length, 5);
  assert.equal(result.filter((item) => item.movement.percent < 0).length, 5);
});

test("fills a three-gainer shortfall with seven decliners", () => {
  const result = selectMoversTickerItems(entry(
    Array.from({ length: 3 }, (_, i) => card(`g${i}`, i + 1)),
    Array.from({ length: 8 }, (_, i) => card(`d${i}`, -(i + 1)))
  ));
  assert.equal(result.filter((item) => item.movement.percent > 0).length, 3);
  assert.equal(result.filter((item) => item.movement.percent < 0).length, 7);
});

test("fills a two-decliner shortfall with eight gainers", () => {
  const result = selectMoversTickerItems(entry(
    Array.from({ length: 9 }, (_, i) => card(`g${i}`, i + 1)),
    Array.from({ length: 2 }, (_, i) => card(`d${i}`, -(i + 1)))
  ));
  assert.equal(result.filter((item) => item.movement.percent > 0).length, 8);
  assert.equal(result.filter((item) => item.movement.percent < 0).length, 2);
});

test("deduplicates cards and excludes missing 7D percentages", () => {
  const result = selectMoversTickerItems(entry(
    [card("same", 12), card("missing", null)],
    [card("same", -20), card("valid", -4)]
  ));
  assert.deepEqual(result.map((item) => item.card.id).sort(), ["same", "valid"]);
});

test("uses 7D movement instead of stronger 30D movement", () => {
  const result = selectMoversTickerItems(entry(
    [card("seven-day", 8, { change30dPercent: 1 }), card("thirty-day", 2, { change30dPercent: 99 })],
    []
  ));
  assert.deepEqual(result.map((item) => item.card.id), ["seven-day", "thirty-day"]);
});

test("ticker trend direction value covers positive, negative, zero, and unavailable movement", () => {
  assert.equal(getMoversTickerTrendValue({ amount: 1.25, percent: 9 }), 1.25);
  assert.equal(getMoversTickerTrendValue({ amount: -0.5, percent: -4 }), -0.5);
  assert.equal(getMoversTickerTrendValue({ amount: 0, percent: 2 }), 0);
  assert.equal(getMoversTickerTrendValue({ amount: null, percent: null }), null);
  assert.equal(getMoversTickerTrendValue({ percent: 3.2 }), 3.2);
});
