import assert from "node:assert/strict";
import test from "node:test";

import { getPokemonSetCardsPage, getPokemonSetCardsValidation } from "./pokemonSetCardsClient.js";

// ---------------------------------------------------------------------------
// Phase 6B: getPokemonSetCardsPage had no in-flight join at all (unlike every
// other slim endpoint in pokemonSetMarketClient.js), so a browser measurement
// showed it firing 3x for one initial Cards-tab load (StrictMode's
// mount/cleanup/mount plus a further duplicate). These tests guard the fix:
// concurrent identical calls join a single in-flight request, while distinct
// params (page/sort/filter/etc.) still fetch independently.
// ---------------------------------------------------------------------------

function makeCardsPagePayload(overrides = {}) {
  return {
    set: { id: "set-1", name: "Test Set", slug: "testSet" },
    cards: [],
    pagination: { page: 1, pageSize: 60, totalCards: 0, totalPages: 1, hasNextPage: false, hasPreviousPage: false },
    filters: { availableRarities: [], availableSorts: [], sort: "set-number" },
    meta: { warnings: [] },
    ...overrides,
  };
}

function stubFetchJson(responseFactory) {
  const originalFetch = globalThis.fetch;
  let callCount = 0;
  globalThis.fetch = async (...args) => {
    callCount += 1;
    const body = responseFactory(callCount, ...args);
    return {
      ok: true,
      status: 200,
      json: async () => body,
    };
  };
  return {
    getCallCount: () => callCount,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

test("getPokemonSetCardsPage joins concurrent identical calls into a single fetch", async () => {
  const stub = stubFetchJson(() => makeCardsPagePayload());
  try {
    const [first, second] = await Promise.all([
      getPokemonSetCardsPage("set-dedupe-cards-page", { page: 1, pageSize: 60, sort: "set-number" }),
      getPokemonSetCardsPage("set-dedupe-cards-page", { page: 1, pageSize: 60, sort: "set-number" }),
    ]);
    assert.equal(stub.getCallCount(), 1, "two concurrent identical calls must issue exactly one network fetch");
    assert.deepEqual(first, second);

    await getPokemonSetCardsPage("set-dedupe-cards-page", { page: 1, pageSize: 60, sort: "set-number" });
    assert.equal(stub.getCallCount(), 2, "a call after the first resolves must fetch again, not reuse a stale in-flight entry");
  } finally {
    stub.restore();
  }
});

test("getPokemonSetCardsPage does not join calls for a different set id, page, sort, or filter", async () => {
  const stub = stubFetchJson(() => makeCardsPagePayload());
  try {
    await Promise.all([
      getPokemonSetCardsPage("set-dedupe-cards-a", { page: 1, sort: "set-number" }),
      getPokemonSetCardsPage("set-dedupe-cards-b", { page: 1, sort: "set-number" }),
      getPokemonSetCardsPage("set-dedupe-cards-a", { page: 2, sort: "set-number" }),
      getPokemonSetCardsPage("set-dedupe-cards-a", { page: 1, sort: "market-value" }),
      getPokemonSetCardsPage("set-dedupe-cards-a", { page: 1, sort: "set-number", movementFilter: "risers" }),
    ]);
    assert.equal(stub.getCallCount(), 5, "distinct set ids, pages, sorts, or movement filters must not be joined together");
  } finally {
    stub.restore();
  }
});

// ---------------------------------------------------------------------------
// Phase 6C: the same join, extended to getPokemonSetCardsValidation (was
// firing 3-4x per Insights activation with no join at all).
// ---------------------------------------------------------------------------

function makeCardsValidationPayload() {
  return {
    set: { id: "set-1", name: "Test Set", slug: "testSet" },
    cards: [],
    cardAppealMarketPriceCorrelation: null,
    diagnostics: {},
    meta: { warnings: [] },
  };
}

test("getPokemonSetCardsValidation joins concurrent identical calls into a single fetch", async () => {
  const stub = stubFetchJson(() => makeCardsValidationPayload());
  try {
    const [first, second] = await Promise.all([
      getPokemonSetCardsValidation("set-dedupe-validation"),
      getPokemonSetCardsValidation("set-dedupe-validation"),
    ]);
    assert.equal(stub.getCallCount(), 1, "two concurrent identical calls must issue exactly one network fetch");
    assert.deepEqual(first, second);

    await getPokemonSetCardsValidation("set-dedupe-validation");
    assert.equal(stub.getCallCount(), 2, "a call after the first resolves must fetch again, not reuse a stale in-flight entry");
  } finally {
    stub.restore();
  }
});

test("getPokemonSetCardsValidation does not join calls for a different set id, and never collides with cards-page keys", async () => {
  const stub = stubFetchJson(() => makeCardsValidationPayload());
  try {
    await Promise.all([
      getPokemonSetCardsValidation("set-dedupe-validation-a"),
      getPokemonSetCardsValidation("set-dedupe-validation-b"),
      // Same set id as a validation call, but the cards-page endpoint — the
      // namespaced keys must keep these fully independent.
      getPokemonSetCardsPage("set-dedupe-validation-a", { page: 1, sort: "set-number" }),
    ]);
    assert.equal(stub.getCallCount(), 3, "distinct set ids or endpoints must not be joined together");
  } finally {
    stub.restore();
  }
});
