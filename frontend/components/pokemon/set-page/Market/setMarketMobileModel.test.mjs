import assert from "node:assert/strict";
import test from "node:test";

import {
  MOBILE_TOP_CHASE_MAX_ROWS,
  buildHeroMetrics,
  buildMoverCards,
  buildSealedMetrics,
  buildSealedProductChips,
  buildTopChaseModel,
  directionOf,
  formatCompactMoney,
  formatSignedPercent,
  readCardMarketPrice,
} from "./setMarketMobileModel.mjs";

test("prices come from the payload's own fields and never from a fabricated default", () => {
  assert.equal(readCardMarketPrice({ marketPrice: 12.5 }), 12.5);
  assert.equal(readCardMarketPrice({ market_price: "8.25" }), 8.25);
  assert.equal(readCardMarketPrice({ currentNearMintPrice: 3 }), 3);
  // A missing, zero or negative price is "not priced", not "$0.00".
  assert.equal(readCardMarketPrice({}), null);
  assert.equal(readCardMarketPrice({ marketPrice: 0 }), null);
  assert.equal(readCardMarketPrice({ marketPrice: -4 }), null);
});

test("headline currency drops cents only once cents are noise", () => {
  assert.equal(formatCompactMoney(842.37), "$842.37");
  assert.equal(formatCompactMoney(12480.4), "$12,480");
  assert.equal(formatCompactMoney(null), null);
});

test("signed percent uses a true minus sign and one decimal", () => {
  assert.equal(formatSignedPercent(4.26), "+4.3%");
  assert.equal(formatSignedPercent(-11.84), "−11.8%");
  assert.equal(formatSignedPercent(null), null);
});

test("direction falls back to percent when only a percent was published", () => {
  assert.equal(directionOf(2, null), "positive");
  assert.equal(directionOf(null, -3), "negative");
  assert.equal(directionOf(0, 0), "neutral");
  assert.equal(directionOf(null, null), "neutral");
});

test("movers reshape the shared ticker selection without re-ranking it", () => {
  const entry = {
    all: [
      { id: "a", name: "Big Mover", marketPrice: 100, imageSmallUrl: "a.png", change7dAmount: 10, change7dPercent: 11.1 },
      { id: "b", name: "Small Mover", marketPrice: 50, change7dAmount: -2, change7dPercent: -3.8 },
    ],
  };
  const movers = buildMoverCards(entry, { maxItems: 5 });
  assert.equal(movers.length, 2);
  assert.deepEqual(
    movers.map((mover) => [mover.name, mover.priceText, mover.amountText, mover.percentText, mover.direction]),
    [
      ["Big Mover", "$100.00", "+$10.00", "+11.1%", "positive"],
      ["Small Mover", "$50.00", "−$2.00", "−3.8%", "negative"],
    ]
  );
  assert.equal(movers[0].imageUrl, "a.png");
  assert.equal(movers[1].imageUrl, null);
  assert.equal(movers[1].initials, "SM");
});

test("movers render only what exists — an empty entry yields an empty rail", () => {
  assert.deepEqual(buildMoverCards(null), []);
  assert.deepEqual(buildMoverCards({ all: [] }), []);
});

const chaseCard = (name, price, deltas) => ({
  id: name,
  name,
  rarity: "Special Illustration Rare",
  marketPrice: price,
  deltas,
});

test("top chase splits into one featured card and a ranked remainder", () => {
  const cards = [
    chaseCard("Alpha", 400, { "30D": { amount: 20, percent: 5.3, startDate: "2026-07-20", endDate: "2026-08-19" } }),
    chaseCard("Beta", 300, { "30D": { amount: -9, percent: -2.9, startDate: "2026-07-20", endDate: "2026-08-19" } }),
    chaseCard("Gamma", 200, {}),
  ];
  const model = buildTopChaseModel(cards, { selectedWindowKey: "30D", marketAsOfDate: "2026-08-19" });

  assert.equal(model.featured.rank, 1);
  assert.equal(model.featured.name, "Alpha");
  assert.equal(model.featured.priceText, "$400.00");
  assert.deepEqual(model.ranked.map((row) => [row.rank, row.name]), [[2, "Beta"], [3, "Gamma"]]);
  assert.equal(model.total, 3);
  // A card with no published movement says so rather than reporting a zero.
  assert.equal(model.rows[2].hasMovement, false);
  assert.equal(model.rows[2].percentText, null);
});

test("top chase renders however few cards exist and never more than the cap", () => {
  assert.equal(buildTopChaseModel([], {}).featured, null);
  assert.deepEqual(buildTopChaseModel(null, {}).rows, []);
  const many = Array.from({ length: 25 }, (_, index) => chaseCard(`Card ${index}`, 100 - index, {}));
  assert.equal(buildTopChaseModel(many, {}).rows.length, MOBILE_TOP_CHASE_MAX_ROWS);
});

test("an absent rarity collapses instead of printing filler", () => {
  const model = buildTopChaseModel([{ id: "x", name: "No Rarity", marketPrice: 10, rarity: "  " }], {});
  assert.equal(model.featured.rarity, null);
});

test("sealed chips list only the products this set actually tracks", () => {
  const chips = buildSealedProductChips([
    { sealedProductId: 7, productFamily: "booster_box", currentPrice: 420.6 },
    { sealedProductId: 9, productFamily: "elite_trainer_box", variantLabel: "Pikachu", currentPrice: 80.38 },
  ]);
  assert.deepEqual(chips, [
    { id: "7", label: "Booster Box", family: "booster_box", priceText: "$420.60" },
    { id: "9", label: "ETB — Pikachu", family: "elite_trainer_box", priceText: "$80.38" },
  ]);
  assert.deepEqual(buildSealedProductChips(undefined), []);
});

test("colliding chip labels are separated by their own published price", () => {
  const chips = buildSealedProductChips([
    { sealedProductId: 1, productFamily: "elite_trainer_box", name: "ETB (Sylveon)", currentPrice: 92.4 },
    { sealedProductId: 2, productFamily: "elite_trainer_box", name: "ETB (Umbreon)", currentPrice: 74 },
    { sealedProductId: 3, productFamily: "booster_box", currentPrice: 420.6 },
  ]);
  assert.deepEqual(chips.map((chip) => chip.label), ["ETB · $92.40", "ETB · $74.00", "Booster Box"]);
});

test("an unpriced colliding product falls back to its published name, never to a made-up one", () => {
  const chips = buildSealedProductChips([
    { sealedProductId: 1, productFamily: "elite_trainer_box", name: "ETB (Sylveon)" },
    { sealedProductId: 2, productFamily: "elite_trainer_box", name: "ETB (Umbreon)" },
  ]);
  assert.deepEqual(chips.map((chip) => chip.label), ["ETB (Sylveon)", "ETB (Umbreon)"]);
});

test("sealed metrics report only readings the sealed contract publishes", () => {
  const metrics = buildSealedMetrics({
    history: [{ marketPrice: 100 }, { marketPrice: 130 }, { marketPrice: 118 }],
    windowLabel: "30D",
    productCount: 4,
  });
  assert.deepEqual(
    metrics.map((metric) => [metric.label, metric.value]),
    [
      ["30D Low", "$100.00"],
      ["30D High", "$130.00"],
      ["Observed Days", "3"],
      ["Tracked Products", "4"],
    ]
  );
  // No population, print run or market cap cell is ever emitted.
  assert.equal(metrics.some((metric) => /population|market cap|print/i.test(metric.label)), false);
});

test("sealed metrics drop cells rather than inventing them when history is empty", () => {
  const metrics = buildSealedMetrics({ history: [], windowLabel: "7D", productCount: 0 });
  assert.deepEqual(metrics.map((metric) => metric.key), []);
});

test("hero metrics omit every reading the set does not publish", () => {
  assert.deepEqual(
    buildHeroMetrics({ releaseDateText: "Aug 1, 2025", totalCards: 191, ripRank: 3, ripCohortSize: 30 }).map((m) => [
      m.label,
      m.value,
      m.suffix ?? null,
    ]),
    [
      ["Released", "Aug 1, 2025", null],
      ["Total Cards", "191", null],
      ["RIP Rank", "#3", "of 30"],
    ]
  );
  assert.deepEqual(buildHeroMetrics({}).map((metric) => metric.key), []);
  assert.deepEqual(
    buildHeroMetrics({ totalCards: 0, ripRank: 5 }).map((metric) => metric.key),
    ["rip"],
    "a zero card count is missing data, not a real reading"
  );
});
