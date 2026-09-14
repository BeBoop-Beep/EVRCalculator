// Production stability effort (2026-09-04): the Set Value Market process
// cache must actually short-circuit, join concurrent misses, and never probe
// the paid /market/explorer/snapshot endpoint. Own file: the module-level
// process cache would otherwise leak state across other test files.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";

const {
  getExploreSetValueMarket,
  __resetExploreSetValueMarketCacheForTests,
  __seedExploreSetValueMarketCacheForTests,
} = await import("./exploreSetValueMarketServer.js");

const realFetch = globalThis.fetch;
test.after(() => { globalThis.fetch = realFetch; });

test("never probes the paid /market/explorer/snapshot endpoint", async () => {
  __resetExploreSetValueMarketCacheForTests();
  const calledUrls = [];
  globalThis.fetch = async (url) => {
    calledUrls.push(String(url));
    return { ok: true, json: async () => ({ marketOverview: null, sets: [], meta: {} }) };
  };
  await getExploreSetValueMarket();
  assert.ok(calledUrls.every((url) => !url.includes("/market/explorer/snapshot")));
  assert.ok(calledUrls.some((url) => url.includes("/explore/set-value-market")));
});

test("sequential requests always defer to fetch so Next's Data Cache — not our own process TTL — is the sole freshness authority", async () => {
  // A prior version of this module gated fetch behind its own 120s
  // process-local TTL, so once a response landed, a second call within that
  // window returned the cached value WITHOUT calling fetch again. That is a
  // bug in production: Next's `next: { revalidate: 120 }` fetch cache can
  // serve a stale response while it revalidates in the background, and our
  // own TTL would then re-pin that same stale payload in processCache for
  // another full 120s, stacking an extra delay on top of Next's own
  // revalidation window before a newly published snapshot is ever picked up.
  // The fix is for this module to always call fetch and let Next own
  // freshness; processCache is now purely a last-known-good fallback for
  // failures. So two sequential calls must both reach fetch, and each must
  // return exactly what fetch just returned (no stale pinning in between).
  __resetExploreSetValueMarketCacheForTests();
  let callCount = 0;
  globalThis.fetch = async () => {
    callCount += 1;
    return { ok: true, json: async () => ({ marketOverview: null, sets: [{ setId: `call-${callCount}` }], meta: {} }) };
  };
  const first = await getExploreSetValueMarket();
  const second = await getExploreSetValueMarket();
  assert.equal(callCount, 2);
  assert.deepEqual(first.sets, [{ setId: "call-1" }]);
  assert.deepEqual(second.sets, [{ setId: "call-2" }]);
});

test("concurrent misses join a single in-flight backend request", async () => {
  __resetExploreSetValueMarketCacheForTests();
  let callCount = 0;
  globalThis.fetch = async () => {
    callCount += 1;
    await new Promise((resolve) => setTimeout(resolve, 10));
    return { ok: true, json: async () => ({ marketOverview: null, sets: [], meta: {} }) };
  };
  const [a, b, c] = await Promise.all([
    getExploreSetValueMarket(),
    getExploreSetValueMarket(),
    getExploreSetValueMarket(),
  ]);
  assert.equal(callCount, 1);
  assert.deepEqual(a, b);
  assert.deepEqual(b, c);
});

test("A: SUCCESS -> FAILURE -> STALE: an expired warm cache survives a throwing revalidation", async () => {
  __resetExploreSetValueMarketCacheForTests();
  const snapshotA = { marketOverview: { raw: { indexValue: 1 } }, sets: [{ setId: "A" }], meta: {} };
  // Seed cache as already-warm-but-expired, simulating snapshot A having
  // succeeded previously and the freshness window having since elapsed.
  __seedExploreSetValueMarketCacheForTests(snapshotA);

  globalThis.fetch = async () => { throw new Error("ECONNRESET simulated transient failure"); };
  const served = await getExploreSetValueMarket();

  // A is still served, marked stale/requestFailed, never overwritten by the failure.
  assert.deepEqual(served.sets, snapshotA.sets);
  assert.equal(served.meta.stale, true);
  assert.equal(served.meta.requestFailed, true);
});

test("A (500 variant): a non-ok response on an expired cache also falls back to stale A", async () => {
  __resetExploreSetValueMarketCacheForTests();
  const snapshotA = { marketOverview: null, sets: [{ setId: "A" }], meta: {} };
  __seedExploreSetValueMarketCacheForTests(snapshotA);

  globalThis.fetch = async () => ({ ok: false, status: 500 });
  const served = await getExploreSetValueMarket();

  assert.deepEqual(served.sets, snapshotA.sets);
  assert.equal(served.meta.requestFailed, true);
});

test("B: SUCCESS -> FAILURE -> RECOVERY: A survives a failed refresh, then B replaces A on the next success", async () => {
  __resetExploreSetValueMarketCacheForTests();
  const snapshotA = { marketOverview: null, sets: [{ setId: "A" }], meta: {} };
  __seedExploreSetValueMarketCacheForTests(snapshotA);

  // Revalidation fails: A is still served.
  globalThis.fetch = async () => { throw new Error("network down"); };
  const duringOutage = await getExploreSetValueMarket();
  assert.deepEqual(duringOutage.sets, snapshotA.sets);
  assert.equal(duringOutage.meta.requestFailed, true);

  // Backend recovers with a genuinely new snapshot B. The failed attempt must
  // not have pinned the cache to A forever, nor left any other TTL blocking
  // the transition to B on the very next call.
  const snapshotB = { marketOverview: null, sets: [{ setId: "B" }], meta: {} };
  globalThis.fetch = async () => ({ ok: true, json: async () => snapshotB });
  const recovered = await getExploreSetValueMarket();
  assert.deepEqual(recovered.sets, snapshotB.sets);
  assert.equal(recovered.meta.requestFailed, undefined);
  assert.equal(recovered.meta.stale, undefined);
});

test("C: true cold failure (never-successful cache + backend failure) returns the unavailable contract without throwing", async () => {
  __resetExploreSetValueMarketCacheForTests();
  globalThis.fetch = async () => { throw new Error("network down"); };
  const result = await getExploreSetValueMarket();
  assert.equal(result.meta.requestFailed, true);
  assert.deepEqual(result.sets, []);
  assert.equal(result.marketOverview, null);
});

test("H: the public Market fetch no longer disables the persistent Next.js Data Cache with cache:no-store", async () => {
  __resetExploreSetValueMarketCacheForTests();
  let observedOptions;
  globalThis.fetch = async (_url, options) => {
    observedOptions = options;
    return { ok: true, json: async () => ({ marketOverview: null, sets: [], meta: {} }) };
  };
  await getExploreSetValueMarket();
  assert.notEqual(observedOptions?.cache, "no-store");
  assert.equal(observedOptions?.next?.revalidate, 120);
});
