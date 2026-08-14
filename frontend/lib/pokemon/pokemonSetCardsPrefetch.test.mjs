// Cache-identity lifecycle for the Cards intent prefetch.
//
// The whole optimization rests on ONE property: the URL a prefetch requests and
// the URL the subsequent render requests must be the same, and the render must
// reuse the prefetched result rather than issue a second request. These tests
// pin that against the real module, counting actual fetches.
import assert from "node:assert/strict";
import test, { beforeEach } from "node:test";

// pokemonSetCardsClient.js is CJS-resolved under the test runner (the package
// has no "type": "module"), so it is required rather than ESM-imported.
import { createRequire } from "node:module";

const {
  getPokemonSetCardsPage,
  prefetchPokemonSetCardsPage,
  __resetCardsPageResultCache,
} = createRequire(import.meta.url)("./pokemonSetCardsClient.js");

const SET = "5d3d5c23-7098-4393-ad63-6ad9372aee30";

/** The exact option object the cards-page effect passes on first render. */
const RENDER_OPTIONS = Object.freeze({
  page: 1,
  pageSize: 60,
  sort: "set-number",
  sortDirection: "asc",
  query: null,
  rarity: null,
  movementFilter: "all",
  movementSort: "desc",
  movementMetric: null,
  section: "all-cards",
});

let requested = [];

function installFetch({ fail = false } = {}) {
  requested = [];
  globalThis.fetch = async (url) => {
    requested.push(String(url));
    if (fail) {
      return { ok: false, status: 503, json: async () => ({ message: "backend unavailable" }) };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        cards: [{ id: "c1", name: "Card One", setNumber: "1" }],
        pagination: { page: 1, pageSize: 60, totalCards: 266, totalPages: 5 },
        filters: {},
        meta: { snapshot: { updatedAt: "2026-08-13T00:00:00Z" } },
      }),
    };
  };
}

beforeEach(() => {
  __resetCardsPageResultCache();
  installFetch();
  globalThis.performance = globalThis.performance || { now: () => Date.now() };
});

test("prefetch and render request the identical URL", async () => {
  await prefetchPokemonSetCardsPage(SET, RENDER_OPTIONS);
  const prefetchUrl = requested[0];
  __resetCardsPageResultCache();
  installFetch();
  await getPokemonSetCardsPage(SET, RENDER_OPTIONS);
  assert.equal(requested[0], prefetchUrl, "prefetch and render URLs diverged");
});

test("a completed prefetch removes the render's network request entirely", async () => {
  await prefetchPokemonSetCardsPage(SET, RENDER_OPTIONS);
  assert.equal(requested.length, 1, "prefetch should issue exactly one request");
  const payload = await getPokemonSetCardsPage(SET, RENDER_OPTIONS);
  assert.equal(requested.length, 1, "render must reuse the prefetched result, not refetch");
  assert.equal(payload.cards.length, 1);
  assert.equal(payload.pagination.totalCards, 266);
});

test("the reused payload is the same data the render would have fetched", async () => {
  const direct = await getPokemonSetCardsPage(SET, RENDER_OPTIONS);
  __resetCardsPageResultCache();
  installFetch();
  await prefetchPokemonSetCardsPage(SET, RENDER_OPTIONS);
  const viaPrefetch = await getPokemonSetCardsPage(SET, RENDER_OPTIONS);
  assert.deepEqual(viaPrefetch, direct);
});

test("a scope change is a different identity and still fetches", async () => {
  await prefetchPokemonSetCardsPage(SET, RENDER_OPTIONS);
  assert.equal(requested.length, 1);
  for (const [label, override] of [
    ["page", { page: 2 }],
    ["sort", { sort: "market-price" }],
    ["direction", { sortDirection: "desc" }],
    ["query", { query: "pikachu" }],
    ["rarity", { rarity: "Illustration Rare" }],
    ["movementFilter", { movementFilter: "gainers" }],
    ["movementMetric", { movementMetric: "percent" }],
    ["section", { section: "market-movers" }],
  ]) {
    const before = requested.length;
    await getPokemonSetCardsPage(SET, { ...RENDER_OPTIONS, ...override });
    assert.equal(requested.length, before + 1, `${label} must not reuse the page-1 entry`);
  }
});

test("a different set is a different identity", async () => {
  await prefetchPokemonSetCardsPage(SET, RENDER_OPTIONS);
  const before = requested.length;
  await getPokemonSetCardsPage("5e99f658-39f0-4845-9228-db8db3965f32", RENDER_OPTIONS);
  assert.equal(requested.length, before + 1);
});

test("a failed prefetch is not cached and never surfaces its error", async () => {
  installFetch({ fail: true });
  const result = await prefetchPokemonSetCardsPage(SET, RENDER_OPTIONS);
  assert.equal(result, null, "prefetch must swallow failures");
  assert.equal(requested.length, 1);

  // The render path owns the error, and must be free to retry.
  installFetch();
  const payload = await getPokemonSetCardsPage(SET, RENDER_OPTIONS);
  assert.equal(requested.length, 1, "retry should issue its own request");
  assert.equal(payload.cards.length, 1);
});

test("prefetch never rejects even when the set id is missing", async () => {
  assert.equal(await prefetchPokemonSetCardsPage("", RENDER_OPTIONS), null);
  assert.equal(await prefetchPokemonSetCardsPage(null, RENDER_OPTIONS), null);
});

test("concurrent prefetch and render still issue only one request", async () => {
  const [a, b] = await Promise.all([
    prefetchPokemonSetCardsPage(SET, RENDER_OPTIONS),
    getPokemonSetCardsPage(SET, RENDER_OPTIONS),
  ]);
  assert.equal(requested.length, 1, "in-flight join should merge them");
  assert.deepEqual(a, b);
});
