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
  const calls = [];
  globalThis.fetch = async (...args) => {
    callCount += 1;
    calls.push(args);
    const body = responseFactory(callCount, ...args);
    return {
      ok: true,
      status: 200,
      json: async () => body,
    };
  };
  return {
    getCallCount: () => callCount,
    getCalls: () => calls,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

test("getPokemonSetCardsPage bypasses browser caches and requests pricing-v3", async () => {
  const stub = stubFetchJson(() => makeCardsPagePayload());
  try {
    await getPokemonSetCardsPage("set-cache-contract", { page: 1, sort: "set-number" });
    const [[url, options]] = stub.getCalls();
    assert.match(url, /snapshot_contract=pricing-v3/);
    assert.deepEqual(options, {
      method: "GET",
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
  } finally {
    stub.restore();
  }
});

test("a completed fresh response replaces an older response for the same set", async () => {
  const stub = stubFetchJson((callCount) =>
    makeCardsPagePayload({
      cards: [
        {
          id: "caterpie",
          name: "Caterpie",
          marketPrice: callCount === 1 ? 0.16 : 0.19,
          change30dAmount: callCount === 1 ? null : 0.09,
          change30dPercent: callCount === 1 ? null : 90,
        },
      ],
      meta: { snapshot: { updatedAt: callCount === 1 ? "old" : "fresh" } },
    })
  );
  try {
    const oldPayload = await getPokemonSetCardsPage("journey-together-freshness", { page: 1 });
    const freshPayload = await getPokemonSetCardsPage("journey-together-freshness", { page: 1 });
    assert.equal(stub.getCallCount(), 2, "only concurrent calls may be joined; completed data must not be cached");
    assert.equal(oldPayload.cards[0].marketPrice, 0.16);
    assert.equal(freshPayload.cards[0].marketPrice, 0.19);
    assert.equal(freshPayload.cards[0].change30dAmount, 0.09);
    assert.equal(freshPayload.meta.snapshot.updatedAt, "fresh");
  } finally {
    stub.restore();
  }
});

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
      getPokemonSetCardsPage("set-dedupe-cards-a", { page: 1, sort: "set-number", movementSort: "7d-movers" }),
    ]);
    assert.equal(stub.getCallCount(), 6, "distinct set ids, pages, sorts, movement filters, or movement sorts must not be joined together");
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
