import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizePokemonSetCardsPagePayload,
  normalizePokemonSetCardsPayload,
  normalizePokemonSetCardsValidationPayload,
} from "./pokemonSetCardsClient.js";

function makeCamelCard(overrides = {}) {
  return {
    id: "card-1",
    name: "Chase Card",
    setId: "set-1",
    setName: "Test Set",
    cardNumber: "5",
    printedNumber: "5",
    rarity: "Rare",
    supertype: "Pokémon",
    subtypes: [],
    nationalPokedexNumbers: [],
    imageSmallUrl: "https://images.example.com/small.png",
    imageLargeUrl: "https://images.example.com/large.png",
    marketPrice: 42.5,
    currentPrice: 42.5,
    change30dAmount: 5,
    change30dPercent: 11.1,
    movementScore: 5,
    movementLabel: "heating_up",
    enoughHistory: true,
    confidence: "medium",
    cardDesirabilityScore: 55.5,
    pokemonDesirabilityScore: 55.5,
    treatmentScore: 1.2,
    scarcityScore: 0.8,
    adjustedCardAppealScore: 40.5,
    pullRate: 0.01,
    pullRateSource: "pullRate",
    setValueShare: 0.02,
    isHitEligible: true,
    linkedPokemonName: "Pikachu",
    linkedPokemon: [
      { pokemonName: "Pikachu", pokemonReferenceId: 25, desirabilityScore: 90, contributionWeight: 1 },
    ],
    movement30d: {
      currentPrice: 42.5,
      changeAmount: 5,
      changePercent: 11.1,
      score: 5,
      label: "heating_up",
      enoughHistory: true,
      confidence: "medium",
    },
    ...overrides,
  };
}

function makeCardsPagePayload(overrides = {}) {
  return {
    set: { id: "set-1", name: "Test Set", slug: "testSet" },
    cards: [makeCamelCard()],
    pagination: {
      page: 1,
      pageSize: 60,
      totalCards: 120,
      totalPages: 2,
      hasNextPage: true,
      hasPreviousPage: false,
    },
    filters: {
      availableRarities: ["Common", "Rare"],
      availableSorts: ["set-number", "30d-gainers", "30d-decliners"],
      movementWindow: "30D",
      sort: "set-number",
      movementSort: null,
      movementFilter: "all",
      query: null,
      rarity: null,
    },
    meta: { warnings: [] },
    ...overrides,
  };
}

test("normalizePokemonSetCardsPagePayload normalizes cards using the same shape as the full payload", () => {
  const pageResult = normalizePokemonSetCardsPagePayload(makeCardsPagePayload());
  const fullResult = normalizePokemonSetCardsPayload({ set: { id: "set-1" }, cards: [makeCamelCard()] });

  assert.equal(pageResult.cards.length, 1);
  assert.deepEqual(Object.keys(pageResult.cards[0]).sort(), Object.keys(fullResult.cards[0]).sort());
  assert.equal(pageResult.cards[0].name, "Chase Card");
  assert.equal(pageResult.cards[0].marketPrice, 42.5);
  assert.equal(pageResult.cards[0].treatmentScore, 1.2);
  assert.equal(pageResult.cards[0].change30dAmount, 5);
});

test("normalizePokemonSetCardsPagePayload normalizes pagination metadata", () => {
  const result = normalizePokemonSetCardsPagePayload(makeCardsPagePayload());

  assert.equal(result.pagination.page, 1);
  assert.equal(result.pagination.pageSize, 60);
  assert.equal(result.pagination.totalCards, 120);
  assert.equal(result.pagination.totalPages, 2);
  assert.equal(result.pagination.hasNextPage, true);
  assert.equal(result.pagination.hasPreviousPage, false);
});

test("normalizePokemonSetCardsPagePayload normalizes filters metadata", () => {
  const result = normalizePokemonSetCardsPagePayload(
    makeCardsPagePayload({
      filters: {
        availableRarities: ["Common", "Rare"],
        availableSorts: ["set-number"],
        movementWindow: "30D",
        sort: "30d-gainers",
        movementSort: "30d-gainers",
        movementFilter: "heating",
        query: "char",
        rarity: "Rare",
      },
    })
  );

  assert.deepEqual(result.filters.availableRarities, ["Common", "Rare"]);
  assert.equal(result.filters.movementWindow, "30D");
  assert.equal(result.filters.sort, "30d-gainers");
  assert.equal(result.filters.movementSort, "30d-gainers");
  assert.equal(result.filters.movementFilter, "heating");
  assert.equal(result.filters.query, "char");
  assert.equal(result.filters.rarity, "Rare");
});

test("normalizePokemonSetCardsPagePayload tolerates missing fields defensively", () => {
  const result = normalizePokemonSetCardsPagePayload({});

  assert.deepEqual(result.cards, []);
  assert.equal(result.pagination.page, 1);
  assert.equal(result.pagination.pageSize, 60);
  assert.equal(result.pagination.hasNextPage, false);
  assert.deepEqual(result.filters.availableRarities, []);
});

test("normalizePokemonSetCardsPagePayload falls back set.slug to canonicalKey", () => {
  const result = normalizePokemonSetCardsPagePayload(
    makeCardsPagePayload({ set: { id: "set-1", name: "Test Set", canonicalKey: "testSetKey" } })
  );

  assert.equal(result.set.slug, "testSetKey");
});

function makeValidationPayload(overrides = {}) {
  return {
    set: { id: "set-1", name: "Test Set", canonicalKey: "testSetKey" },
    cards: [
      {
        cardId: "card-1",
        cardVariantId: "variant-1",
        name: "Chase Card",
        rarity: "Rare",
        supertype: "Pokémon",
        printedNumber: "5",
        imageUrl: "https://images.example.com/small.png",
        marketPrice: 42.5,
        linkedPokemonName: "Pikachu",
        pokemonDesirabilityScore: 55.5,
        treatmentScore: 1.2,
        scarcityScore: 0.8,
        adjustedCardAppealScore: 40.5,
        pullRate: 0.01,
        pullRateSource: "pullRate",
        setValueShare: 0.02,
        isHitEligible: true,
      },
    ],
    cardAppealMarketPriceCorrelation: {
      n: 1,
      pearson: 0.5,
      spearman: 0.5,
      interpretation: "healthy_separation",
      sampleSource: "canonical_checklist_cards",
      plotRows: [
        {
          pokemonCanonicalCardId: "card-1",
          cardName: "Chase Card",
          marketPrice: 42.5,
          subjectDesirabilityScore: 55.5,
          isHitEligible: true,
        },
      ],
    },
    diagnostics: {
      canonicalCount: 1,
      pricedCount: 1,
      linkedCount: 1,
      includedCount: 1,
      excludedUnpricedCount: 0,
      excludedUnlinkedCount: 0,
      excludedMissingScoreCount: 0,
      sampleSource: "canonical_checklist_cards",
    },
    meta: { warnings: [], source: "pokemon_set_cards_snapshot_latest", updatedAt: "2026-06-30T00:00:00+00:00" },
    ...overrides,
  };
}

test("normalizePokemonSetCardsValidationPayload returns cards, correlation, diagnostics, and meta", () => {
  const result = normalizePokemonSetCardsValidationPayload(makeValidationPayload());

  assert.equal(result.set.id, "set-1");
  assert.equal(result.set.slug, "testSetKey");
  assert.equal(result.cards.length, 1);
  assert.equal(result.cards[0].name, "Chase Card");
  assert.equal(result.cards[0].marketPrice, 42.5);
  assert.equal(result.cards[0].adjustedCardAppealScore, 40.5);
  assert.equal(result.cards[0].isHitEligible, true);
  assert.equal(result.cards[0].supertype, "Pokémon");

  assert.equal(result.cardAppealMarketPriceCorrelation.n, 1);
  assert.equal(result.cardAppealMarketPriceCorrelation.pearson, 0.5);
  assert.equal(result.cardAppealMarketPriceCorrelation.plotRows.length, 1);

  assert.equal(result.diagnostics.canonicalCount, 1);
  assert.equal(result.diagnostics.sampleSource, "canonical_checklist_cards");
  assert.deepEqual(result.meta.warnings, []);
});

test("normalizePokemonSetCardsValidationPayload does not require the full cards payload shape", () => {
  const result = normalizePokemonSetCardsValidationPayload({
    set: { id: "set-2" },
    cards: [{ cardId: "card-9", name: "Sparse Card", marketPrice: 5, adjustedCardAppealScore: 12 }],
    cardAppealMarketPriceCorrelation: null,
    diagnostics: {},
  });

  assert.equal(result.cards.length, 1);
  assert.equal(result.cards[0].name, "Sparse Card");
  assert.equal(result.cardAppealMarketPriceCorrelation, null);
  assert.equal(result.diagnostics.canonicalCount, null);
});

test("normalizePokemonSetCardsValidationPayload tolerates missing fields defensively", () => {
  const result = normalizePokemonSetCardsValidationPayload({});

  assert.deepEqual(result.cards, []);
  assert.equal(result.cardAppealMarketPriceCorrelation, null);
  assert.equal(result.diagnostics.canonicalCount, null);
  assert.deepEqual(result.meta, { warnings: [] });
});
