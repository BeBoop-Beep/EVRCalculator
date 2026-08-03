import assert from "node:assert/strict";
import test from "node:test";

import {
  selectBestSetsToRip,
  selectChaseCards,
  selectExploreRankingRows,
  selectMarketContext,
  selectMarketSignals,
  selectOpeningEconomics,
  selectSealedProducts,
  selectSetValueLeaders,
  selectSetValueMovement,
} from "./landingPreviews.mjs";

function makeEntry(overrides = {}) {
  return {
    key: "set:one",
    name: "Set One",
    era: "Scarlet & Violet",
    logoUrl: "https://images.example/one.png",
    symbolUrl: null,
    rank: 1,
    score: 82.4,
    scoreLabel: "RIP Score",
    tier: "A",
    setValue: 1200,
    previousSetValue7d: 1000,
    setValueStatus7d: "available",
    packCost: 4.5,
    meanValue: 5.4,
    probProfit: 0.42,
    overviewHref: "/TCGs/Pokemon/Sets/set-one?tab=overview",
    href: "/Explore/rip-statistics",
    ...overrides,
  };
}

test("a 7-day movement is only reported when the payload says it is comparable", () => {
  assert.deepEqual(selectSetValueMovement(makeEntry()), {
    amount: 200,
    percent: 20,
    direction: "up",
  });

  assert.equal(selectSetValueMovement(makeEntry({ setValueStatus7d: "new" })), null);
  assert.equal(selectSetValueMovement(makeEntry({ setValueStatus7d: "unavailable" })), null);
  assert.equal(selectSetValueMovement(makeEntry({ previousSetValue7d: null })), null);
});

test("a set that has not moved reports flat rather than being dropped", () => {
  const movement = selectSetValueMovement(makeEntry({ previousSetValue7d: 1200 }));
  assert.equal(movement.amount, 0);
  assert.equal(movement.direction, "flat");
});

test("opening economics need both published figures and are never derived", () => {
  const economics = selectOpeningEconomics(makeEntry());
  assert.equal(economics.packCost, 4.5);
  assert.equal(economics.meanValue, 5.4);
  assert.equal(economics.probProfit, 0.42);
  assert.equal(economics.standing, "above");
  assert.equal(economics.valueShare, 1);
  assert.ok(Math.abs(economics.costShare - 4.5 / 5.4) < 1e-9);

  assert.equal(selectOpeningEconomics(makeEntry({ meanValue: null })), null);
  assert.equal(selectOpeningEconomics(makeEntry({ packCost: null })), null);
  assert.equal(selectOpeningEconomics(makeEntry({ packCost: 0 })), null);
});

test("a modeled mean below cost is reported as below, not hidden", () => {
  const economics = selectOpeningEconomics(makeEntry({ packCost: 6, meanValue: 4.5 }));
  assert.equal(economics.standing, "below");
  assert.equal(economics.costShare, 1);
  assert.equal(economics.valueShare, 0.75);
});

test("the Explore preview publishes the backend rank and never renumbers", () => {
  const rows = selectExploreRankingRows(
    [
      makeEntry({ key: "a", name: "A", rank: 2 }),
      makeEntry({ key: "b", name: "B", rank: null }),
      makeEntry({ key: "c", name: "C", rank: 5 }),
    ],
    5
  );

  assert.deepEqual(
    rows.map((row) => row.rank),
    [2, 5],
    "an unranked set is dropped rather than given a position"
  );
  assert.equal(rows[0].href, "/TCGs/Pokemon/Sets/set-one?tab=overview");
});

test("the best-sets ladder is the same order, shorter", () => {
  const entries = [1, 2, 3, 4, 5].map((rank) =>
    makeEntry({ key: `set-${rank}`, name: `Set ${rank}`, rank })
  );
  assert.deepEqual(
    selectBestSetsToRip(entries, 3).map((row) => row.rank),
    [1, 2, 3]
  );
});

test("the set value ladder orders by value and numbers itself", () => {
  const leaders = selectSetValueLeaders([
    makeEntry({ key: "low", name: "Low", setValue: 100 }),
    makeEntry({ key: "high", name: "High", setValue: 900 }),
    makeEntry({ key: "none", name: "None", setValue: null }),
  ]);

  assert.deepEqual(
    leaders.map((row) => [row.position, row.name, row.setValue]),
    [
      [1, "High", 900],
      [2, "Low", 100],
    ],
    "a set with no checklist value is omitted, never ranked at zero"
  );
});

test("market context reports only figures the payload actually carries", () => {
  const context = selectMarketContext({
    entries: [makeEntry({ rank: 1 }), makeEntry({ key: "x", rank: null })],
    meta: { comparisonSnapshots: { currentMarketDate: "2026-07-27" } },
  });

  assert.equal(context.trackedSetCount, 2);
  assert.equal(context.rankedSetCount, 1);
  assert.equal(context.marketDate, "2026-07-27");

  const empty = selectMarketContext({ entries: [], meta: null });
  assert.equal(empty.trackedSetCount, null);
  assert.equal(empty.rankedSetCount, null);
  assert.equal(empty.marketDate, null, "no snapshot date means the section omits the figure");
});

/* --------------------------------------------- pokemon product content --- */

test("chase cards need real art and a real name, and carry their 7-day move", () => {
  const cards = selectChaseCards({
    topChaseCards: [
      {
        canonicalCardId: "a",
        name: "Gastly",
        imageSmallUrl: "https://images.example/177.png",
        rarity: "illustration rare",
        setNumber: "177/162",
        marketPrice: 99.1,
        marketDeltaWindows: { "7D": { changePercent: -2.33 } },
      },
      { canonicalCardId: "b", name: "No Art", marketPrice: 12 },
      { canonicalCardId: "c", imageSmallUrl: "https://images.example/2.png", marketPrice: 12 },
    ],
  });

  assert.equal(cards.length, 1, "a card with no art, or no name, is dropped rather than framed empty");
  assert.deepEqual(cards[0], {
    key: "a",
    name: "Gastly",
    image: "https://images.example/177.png",
    rarity: "illustration rare",
    number: "177/162",
    price: 99.1,
    changePercent: -2.33,
    direction: "down",
  });
});

test("a set with no published chase cards yields nothing to render", () => {
  assert.deepEqual(selectChaseCards(null), []);
  assert.deepEqual(selectChaseCards({}), []);
  assert.deepEqual(selectChaseCards({ topChaseCards: [] }), []);
});

test("sealed products take the most recognizable family first, priced, one per family", () => {
  const products = selectSealedProducts(
    {
      products: [
        { sealedProductId: "1", productFamily: "booster_pack", currentPrice: 11.17 },
        { sealedProductId: "2", productFamily: "booster_box", currentPrice: 189.71 },
        { sealedProductId: "3", productFamily: "booster_box", currentPrice: 313.53 },
        { sealedProductId: "4", productFamily: "elite_trainer_box", currentPrice: 130.83 },
        { sealedProductId: "5", productFamily: "booster_box" },
      ],
    },
    2
  );

  assert.deepEqual(
    products.map((p) => [p.label, p.price]),
    [
      ["Booster Box", 313.53],
      ["Elite Trainer Box", 130.83],
    ],
    "box before pack, highest price within a family, and an unpriced row never appears"
  );
});

test("sealed products render nothing when the set has no priced sealed rows", () => {
  assert.deepEqual(selectSealedProducts(null), []);
  assert.deepEqual(selectSealedProducts({ products: [] }), []);
});

test("the market strip omits any signal whose data is missing", () => {
  const entry = makeEntry();

  const full = selectMarketSignals({
    entries: [entry],
    openingSpotlightSet: entry,
    moversPayload: {
      marketMovers: {
        all: [
          { name: "Small Move", change7dPercent: 2, imageSmallUrl: "https://i/1.png", currentPrice: 10 },
          { name: "Big Move", change7dPercent: -18.4, imageSmallUrl: "https://i/2.png", currentPrice: 445, setName: "Ascended Heroes" },
        ],
      },
    },
  });
  assert.deepEqual(full.map((s) => s.key), ["opening", "value", "mover"]);
  assert.equal(full[2].cardName, "Big Move", "the largest absolute move wins, in either direction");
  assert.equal(full[2].movement.direction, "down");

  assert.equal(full[0].value, "#1", "the opening signal leads with the rank, not a score that reads as a percentage");
  assert.equal(full[0].unit, "Opening rank");

  const noMovers = selectMarketSignals({ entries: [entry], openingSpotlightSet: entry, moversPayload: null });
  assert.deepEqual(noMovers.map((s) => s.key), ["opening", "value"], "a missing movers payload drops only its own signal");

  const noOpening = selectMarketSignals({ entries: [entry], openingSpotlightSet: null, moversPayload: null });
  assert.deepEqual(
    noOpening.map((s) => s.key),
    ["value"],
    "the opening signal is omitted rather than re-derived when there is no spotlight"
  );

  assert.deepEqual(selectMarketSignals({}), [], "no data at all renders no strip");
});
