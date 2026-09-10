// Companion to exploreSetValueMarketServerCacheBehavior.test.mjs, own file for
// the same reason: the module-level process cache is global and would leak
// state across other test files.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";

const {
  getExploreMarketMovers,
  __resetExploreMarketMoversCacheForTests,
  __seedExploreMarketMoversCacheForTests,
} = await import("./exploreMarketMoversServer.js");

const realFetch = globalThis.fetch;
test.after(() => { globalThis.fetch = realFetch; });

test("A: SUCCESS -> FAILURE -> STALE: an expired warm movers cache survives a throwing revalidation", async () => {
  __resetExploreMarketMoversCacheForTests();
  const snapshotA = { marketMovers: { window: "7D", all: [{ canonicalCardId: "A" }] }, meta: {} };
  __seedExploreMarketMoversCacheForTests(snapshotA);

  globalThis.fetch = async () => { throw new Error("ECONNRESET simulated transient failure"); };
  const served = await getExploreMarketMovers();

  assert.deepEqual(served.marketMovers.all, snapshotA.marketMovers.all);
  assert.equal(served.meta.stale, true);
  assert.equal(served.meta.requestFailed, true);
});

test("B: SUCCESS -> FAILURE -> RECOVERY: A survives a failed refresh, then B replaces A on the next success", async () => {
  __resetExploreMarketMoversCacheForTests();
  const snapshotA = { marketMovers: { window: "7D", all: [{ canonicalCardId: "A" }] }, meta: {} };
  __seedExploreMarketMoversCacheForTests(snapshotA);

  globalThis.fetch = async () => { throw new Error("network down"); };
  const duringOutage = await getExploreMarketMovers();
  assert.deepEqual(duringOutage.marketMovers.all, snapshotA.marketMovers.all);
  assert.equal(duringOutage.meta.requestFailed, true);

  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({ marketMovers: { window: "7D", all: [{ canonicalCardId: "B" }] }, meta: {} }),
  });
  const recovered = await getExploreMarketMovers();
  assert.equal(recovered.marketMovers.all[0].canonicalCardId, "B");
  assert.equal(recovered.meta.requestFailed, undefined);
});

test("C: true cold failure returns the unavailable contract without throwing", async () => {
  __resetExploreMarketMoversCacheForTests();
  globalThis.fetch = async () => { throw new Error("network down"); };
  const result = await getExploreMarketMovers();
  assert.equal(result.meta.requestFailed, true);
  assert.deepEqual(result.marketMovers.all, []);
});

test("H: the public movers fetch no longer disables the persistent Next.js Data Cache with cache:no-store", async () => {
  __resetExploreMarketMoversCacheForTests();
  let observedOptions;
  globalThis.fetch = async (_url, options) => {
    observedOptions = options;
    return { ok: true, json: async () => ({ marketMovers: { window: "7D", all: [] }, meta: {} }) };
  };
  await getExploreMarketMovers();
  assert.notEqual(observedOptions?.cache, "no-store");
  assert.equal(observedOptions?.next?.revalidate, 120);
});

test("G: movers being unavailable does not throw or corrupt an otherwise independent read", async () => {
  __resetExploreMarketMoversCacheForTests();
  globalThis.fetch = async () => ({ ok: false, status: 500 });
  const result = await getExploreMarketMovers();
  // Market Overview / Set Market live in a completely separate module
  // (exploreSetValueMarketServer.js) with its own fetch call and cache key,
  // so a movers failure has no path to affect it — this asserts the movers
  // surface degrades to its own well-formed empty contract rather than
  // throwing and taking the page down.
  assert.equal(result.meta.requestFailed, true);
  assert.deepEqual(result.marketMovers, { window: "7D", all: [] });
});
