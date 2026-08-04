import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";

// See slimModuleRequestLifecycle.test.mjs — createRequire is the import form
// that resolves this CJS-transpiled ESM module under the suite's tsx runner.
const require = createRequire(import.meta.url);
const {
  __hasSlimModuleInflightForTests,
  __resetTopChaseLastKnownGoodForTests,
  getCachedPokemonSetTopChase,
  getPokemonSetTopChase,
} = require("./pokemonSetMarketClient.js");

const {
  TOP_CHASE_STATUS,
  validateTopChasePayload,
} = await import("./topChasePayloadContract.mjs");

// ---------------------------------------------------------------------------
// Top Chase Cards state machine.
//
// The section used to infer success from `cards.length > 0`. A checklist or
// dashboard fallback row carries images and prices but no dedicated Top Chase
// history, so a FAILED dedicated module rendered a full grid of cards whose
// every chart read "Awaiting trend" — and was recorded as a success, so nothing
// retried. These tests pin the distinction between a payload that is settled
// (a genuinely new set) and one that is broken (retry-worthy).
// ---------------------------------------------------------------------------

const SET_ID = "11111111-1111-1111-1111-111111111111";
const OTHER_SET_ID = "22222222-2222-2222-2222-222222222222";
const DATE = "2026-08-03";
const PRIOR = "2026-08-02";

function history(dates, price = 10) {
  return dates.map((date) => ({ date, marketPrice: price }));
}

function topChaseBody({ setId = SET_ID, cards = null, histories = null } = {}) {
  return {
    set: { id: setId, name: "Phantasmal Flames", slug: "phantasmalFlames" },
    latestMarketDate: DATE,
    topChaseCards:
      cards ||
      [
        { cardVariantId: "v1", cardId: "c1", name: "Chase A", marketPrice: 120.5, setId },
        { cardVariantId: "v2", cardId: "c2", name: "Chase B", marketPrice: 80.25, setId },
      ],
    topChaseCardHistories:
      histories || { v1: history([PRIOR, DATE]), v2: history([PRIOR, DATE], 20) },
    meta: { sources: {}, warnings: [] },
  };
}

function jsonResponse(body, { status = 200 } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function installFetch(handlers) {
  const calls = [];
  let index = 0;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    const handler = handlers[Math.min(index, handlers.length - 1)];
    index += 1;
    if (typeof handler === "function") {
      return handler();
    }
    return handler;
  };
  return calls;
}

test.beforeEach(() => {
  __resetTopChaseLastKnownGoodForTests();
});

test.afterEach(() => {
  delete globalThis.fetch;
});

// --- 1. Direct load, dedicated payload succeeds -----------------------------
test("direct load with a valid dedicated payload renders cards and graphs", async () => {
  installFetch([jsonResponse(topChaseBody())]);

  const result = await getPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 });

  assert.equal(result.cards.length, 2);
  assert.equal(result.topChaseVerdict.status, TOP_CHASE_STATUS.COMPLETE);
  assert.equal(result.topChaseVerdict.renderableCardCount, 2);
  assert.equal(result.isStale, false);
  // Every rendered card can actually draw a line.
  result.cards.forEach((card) => assert.ok(card.priceHistory.length >= 2));
});

test("a successful Top Chase request is issued with no-store", async () => {
  const calls = installFetch([jsonResponse(topChaseBody())]);
  await getPokemonSetTopChase(SET_ID);

  assert.equal(calls[0].init.cache, "no-store");
  // No random cache-busting parameter is appended.
  assert.ok(!/[?&](_|cb|ts|nonce)=/.test(calls[0].url));
});

// --- 2. First request fails, second succeeds --------------------------------
test("one transient failure is retried once and then renders without a reload", async () => {
  const calls = installFetch([
    () => {
      const error = new Error("The operation was aborted.");
      error.name = "AbortError";
      throw error;
    },
    () => jsonResponse(topChaseBody()),
  ]);

  const result = await getPokemonSetTopChase(SET_ID);

  assert.equal(calls.length, 2, "expected exactly two attempts");
  assert.equal(result.topChaseVerdict.status, TOP_CHASE_STATUS.COMPLETE);
});

test("a retryable 503 snapshot-incomplete error triggers exactly one retry", async () => {
  const calls = installFetch([
    jsonResponse(
      { message: "incomplete", code: "POKEMON_SET_TOP_CHASE_SNAPSHOT_INCOMPLETE", retryable: true },
      { status: 503 }
    ),
    jsonResponse(topChaseBody()),
  ]);

  const result = await getPokemonSetTopChase(SET_ID);

  assert.equal(calls.length, 2);
  assert.equal(result.topChaseVerdict.complete, true);
});

// --- 3. Both requests fail, no cache ----------------------------------------
test("both attempts failing raises a retryable error and never invents rows", async () => {
  const calls = installFetch([jsonResponse({ message: "boom" }, { status: 502 })]);

  await assert.rejects(
    () => getPokemonSetTopChase(SET_ID),
    (error) => {
      assert.equal(error.status, 502);
      return true;
    }
  );

  assert.equal(calls.length, 2, "bounded at two attempts — no polling loop");
  assert.equal(__hasSlimModuleInflightForTests(`top-chase:${SET_ID}:365d:10`), false);
});

// --- 4. Checklist rows must never masquerade as Top Chase -------------------
test("checklist-shaped rows with prices but no history are not a Top Chase success", async () => {
  // Exactly the misleading payload: images and prices present, histories absent.
  const checklistish = topChaseBody({
    cards: [
      { cardVariantId: "v1", name: "A", marketPrice: 10, imageUrl: "http://img/a", setId: SET_ID },
      { cardVariantId: "v2", name: "B", marketPrice: 20, imageUrl: "http://img/b", setId: SET_ID },
    ],
    histories: {},
  });
  installFetch([jsonResponse(checklistish)]);

  await assert.rejects(() => getPokemonSetTopChase(SET_ID));
});

test("validator classifies priced-but-historyless rows as structurally incomplete", () => {
  const verdict = validateTopChasePayload(
    {
      set: { id: SET_ID },
      latestMarketDate: DATE,
      cards: [{ cardVariantId: "v1", marketPrice: 10, priceHistory: [] }],
    },
    { setId: SET_ID }
  );

  assert.equal(verdict.status, TOP_CHASE_STATUS.STRUCTURALLY_INCOMPLETE);
  assert.equal(verdict.renderable, false);
  assert.ok(verdict.reasons.includes("no_usable_top_chase_history"));
});

// --- 5. Validated last-known-good survives a transient refresh failure -------
test("a validated same-set payload is reused, marked stale, on a later failure", async () => {
  installFetch([jsonResponse(topChaseBody())]);
  const fresh = await getPokemonSetTopChase(SET_ID);
  assert.equal(fresh.topChaseVerdict.complete, true);
  assert.ok(getCachedPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 }));

  installFetch([jsonResponse({ message: "down" }, { status: 503 })]);
  const stale = await getPokemonSetTopChase(SET_ID);

  assert.equal(stale.isStale, true);
  assert.equal(stale.isLastKnownGood, true);
  assert.equal(stale.cards.length, 2);
});

test("an incomplete payload is never stored as last-known-good", async () => {
  installFetch([jsonResponse(topChaseBody({ histories: {} }))]);
  await assert.rejects(() => getPokemonSetTopChase(SET_ID));

  assert.equal(getCachedPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 }), null);
});

test("last-known-good is keyed by set, window and limit", async () => {
  installFetch([jsonResponse(topChaseBody())]);
  await getPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 });

  // A different window/limit must not inherit the cached payload.
  assert.ok(getCachedPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 }));
  assert.equal(getCachedPokemonSetTopChase(SET_ID, { window: "30d", limit: 10 }), null);
  assert.equal(getCachedPokemonSetTopChase(SET_ID, { window: "365d", limit: 5 }), null);
  assert.equal(getCachedPokemonSetTopChase(OTHER_SET_ID, { window: "365d", limit: 10 }), null);
});

// --- 6. Set switch during a request -----------------------------------------
test("another set's payload is rejected rather than rendered under this set", async () => {
  installFetch([jsonResponse(topChaseBody({ setId: OTHER_SET_ID }))]);

  await assert.rejects(
    () => getPokemonSetTopChase(SET_ID),
    (error) => {
      assert.equal(error.code, "POKEMON_SET_TOP_CHASE_SNAPSHOT_INCOMPLETE");
      assert.equal(error.topChaseVerdict.status, TOP_CHASE_STATUS.IDENTITY_MISMATCH);
      return true;
    }
  );
});

test("a previous set's last-known-good is never served for a different set", async () => {
  installFetch([jsonResponse(topChaseBody())]);
  await getPokemonSetTopChase(SET_ID);

  installFetch([jsonResponse({ message: "down" }, { status: 503 })]);
  await assert.rejects(() => getPokemonSetTopChase(OTHER_SET_ID));
});

test("validator rejects a card carrying a foreign set id", () => {
  const verdict = validateTopChasePayload(
    {
      set: { id: SET_ID },
      latestMarketDate: DATE,
      cards: [{ cardVariantId: "v1", marketPrice: 10, setId: OTHER_SET_ID, priceHistory: history([PRIOR, DATE]) }],
    },
    { setId: SET_ID }
  );

  assert.equal(verdict.status, TOP_CHASE_STATUS.IDENTITY_MISMATCH);
  assert.ok(verdict.reasons.includes("cross_set_card_history"));
});

// --- 7. Phantasmal Flames shape ---------------------------------------------
test("variant-keyed topChaseCardHistories map onto cards and produce chart series", async () => {
  // The real Phantasmal Flames shape: 10 cards, 10 variant-keyed histories, no
  // embedded per-card priceHistory at all.
  const cards = Array.from({ length: 10 }, (_, index) => ({
    cardVariantId: `variant-${index}`,
    cardId: `card-${index}`,
    name: `Chase ${index}`,
    marketPrice: 50 + index,
    setId: SET_ID,
  }));
  const histories = Object.fromEntries(
    cards.map((card, index) => [card.cardVariantId, history(["2026-08-01", PRIOR, DATE], 40 + index)])
  );
  installFetch([jsonResponse(topChaseBody({ cards, histories }))]);

  const result = await getPokemonSetTopChase(SET_ID);

  assert.equal(result.cards.length, 10);
  assert.equal(result.topChaseVerdict.status, TOP_CHASE_STATUS.COMPLETE);
  assert.equal(result.topChaseVerdict.renderableCardCount, 10);
  result.cards.forEach((card) => {
    assert.equal(card.priceHistory.length, 3, "each card resolves its variant-keyed series");
    assert.equal(card.selectedHistorySource, "top_chase_card_histories");
  });
});

// --- 8. Genuinely new set ----------------------------------------------------
test("a new set with one historical point settles as insufficient history", async () => {
  const cards = [{ cardVariantId: "v1", name: "New", marketPrice: 15, setId: SET_ID }];
  installFetch([jsonResponse(topChaseBody({ cards, histories: { v1: history([DATE]) } }))]);

  const result = await getPokemonSetTopChase(SET_ID);

  assert.equal(result.topChaseVerdict.status, TOP_CHASE_STATUS.INSUFFICIENT_HISTORY);
  assert.equal(result.topChaseVerdict.retryable, false);
});

test("insufficient history is not retried", async () => {
  const cards = [{ cardVariantId: "v1", marketPrice: 15, setId: SET_ID }];
  const calls = installFetch([
    jsonResponse(topChaseBody({ cards, histories: { v1: history([DATE]) } })),
  ]);

  await getPokemonSetTopChase(SET_ID);

  assert.equal(calls.length, 1, "a truthful terminal state must not retry");
});

// --- Validator edge cases ----------------------------------------------------
test("an empty snapshot is settled, not retryable", () => {
  const verdict = validateTopChasePayload(
    { set: { id: SET_ID }, cards: [], latestMarketDate: DATE },
    { setId: SET_ID }
  );
  assert.equal(verdict.status, TOP_CHASE_STATUS.EMPTY);
  assert.equal(verdict.retryable, false);
});

test("history dated after latestMarketDate is structurally incomplete", () => {
  const verdict = validateTopChasePayload(
    {
      set: { id: SET_ID },
      latestMarketDate: DATE,
      cards: [{ cardVariantId: "v1", marketPrice: 10, priceHistory: history([DATE, "2026-08-04"]) }],
    },
    { setId: SET_ID }
  );
  assert.equal(verdict.status, TOP_CHASE_STATUS.STRUCTURALLY_INCOMPLETE);
  assert.ok(verdict.reasons.includes("history_date_after_latest_market_date"));
});

test("the in-flight key is released after a contract-validation failure", async () => {
  installFetch([jsonResponse(topChaseBody({ histories: {} }))]);
  await assert.rejects(() => getPokemonSetTopChase(SET_ID));

  assert.equal(__hasSlimModuleInflightForTests(`top-chase:${SET_ID}:365d:10`), false);
});

// --- Partially complete payloads must retry, not settle ----------------------
//
// The defect this pins: the client settled on
//   `verdict.renderable || !isRetryableTopChaseStatus(verdict.status)`.
// A partially complete payload is BOTH renderable and structurally incomplete,
// so it returned on attempt one and the cards without history kept showing
// "Awaiting trend" with no automatic retry ever firing.

function partialTopChaseBody({ withHistory = 8, total = 10 } = {}) {
  const cards = [];
  const histories = {};
  for (let index = 0; index < total; index += 1) {
    const key = `v${index}`;
    cards.push({ cardVariantId: key, cardId: `c${index}`, name: `Chase ${index}`, marketPrice: 50 + index, setId: SET_ID });
    histories[key] = index < withHistory ? history([PRIOR, DATE], 50 + index) : [];
  }
  return topChaseBody({ cards, histories });
}

test("a partially complete payload (8/10 cards) is retried instead of settling", async () => {
  const calls = installFetch([
    jsonResponse(partialTopChaseBody({ withHistory: 8, total: 10 })),
    jsonResponse(partialTopChaseBody({ withHistory: 10, total: 10 })),
  ]);

  const result = await getPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 });

  assert.equal(calls.length, 2, "a partially complete payload must spend the retry");
  assert.equal(result.topChaseVerdict.status, TOP_CHASE_STATUS.COMPLETE);
  assert.equal(result.topChaseVerdict.renderableCardCount, 10);
  assert.equal(result.isStale, false);
});

test("a partial payload is never stored as last-known-good", async () => {
  installFetch([
    jsonResponse(partialTopChaseBody({ withHistory: 8, total: 10 })),
    jsonResponse(partialTopChaseBody({ withHistory: 8, total: 10 })),
  ]);

  // Both attempts return the same partial payload, so the call fails.
  await assert.rejects(() => getPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 }));

  // Nothing incomplete may enter the last-known-good cache.
  assert.equal(getCachedPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 }), null);
});

test("after both attempts return partials, the section errors rather than rendering half a grid", async () => {
  // ATOMIC: a partially renderable payload is not an acceptable final answer.
  // Returning it would leave 2 of 10 cards on "Awaiting trend" while the section
  // recorded a success, which is the outcome this contract exists to prevent.
  const calls = installFetch([
    jsonResponse(partialTopChaseBody({ withHistory: 8, total: 10 })),
    jsonResponse(partialTopChaseBody({ withHistory: 8, total: 10 })),
  ]);

  await assert.rejects(
    () => getPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 }),
    (error) => {
      assert.equal(error.code, "POKEMON_SET_TOP_CHASE_SNAPSHOT_INCOMPLETE");
      assert.equal(error.retryable, true);
      assert.equal(error.topChaseVerdict.status, TOP_CHASE_STATUS.STRUCTURALLY_INCOMPLETE);
      return true;
    }
  );

  assert.equal(calls.length, 2, "exactly two attempts, never a polling loop");
});

test("a complete last-known-good beats a later partial for the same set+window+limit", async () => {
  installFetch([jsonResponse(topChaseBody())]);
  const fresh = await getPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 });
  assert.equal(fresh.topChaseVerdict.complete, true);

  // Both later attempts come back partial; the validated complete payload stands
  // in, clearly marked stale.
  installFetch([
    jsonResponse(partialTopChaseBody({ withHistory: 8, total: 10 })),
    jsonResponse(partialTopChaseBody({ withHistory: 8, total: 10 })),
  ]);
  const stale = await getPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 });

  assert.equal(stale.isLastKnownGood, true);
  assert.equal(stale.isStale, true);
  assert.equal(stale.topChaseVerdict.status, TOP_CHASE_STATUS.COMPLETE);
});

test("insufficient history still settles on attempt one without retrying", async () => {
  const calls = installFetch([
    jsonResponse(
      topChaseBody({
        cards: [{ cardVariantId: "v1", cardId: "c1", name: "Chase A", marketPrice: 120.5, setId: SET_ID }],
        histories: { v1: history([DATE]) },
      })
    ),
  ]);

  const result = await getPokemonSetTopChase(SET_ID, { window: "365d", limit: 10 });

  assert.equal(calls.length, 1, "a settled truth must not spend the retry");
  assert.equal(result.topChaseVerdict.status, TOP_CHASE_STATUS.INSUFFICIENT_HISTORY);
});
