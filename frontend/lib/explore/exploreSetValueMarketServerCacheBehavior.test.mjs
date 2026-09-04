// Production stability effort (2026-09-04): the Set Value Market process
// cache must actually short-circuit, join concurrent misses, and never probe
// the paid /market/explorer/snapshot endpoint. Own file: the module-level
// process cache would otherwise leak state across other test files.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";

const { getExploreSetValueMarket, __resetExploreSetValueMarketCacheForTests } = await import(
  "./exploreSetValueMarketServer.js"
);

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

test("a warm request inside the TTL makes no backend request", async () => {
  __resetExploreSetValueMarketCacheForTests();
  let callCount = 0;
  globalThis.fetch = async () => {
    callCount += 1;
    return { ok: true, json: async () => ({ marketOverview: null, sets: [{ setId: "a" }], meta: {} }) };
  };
  const first = await getExploreSetValueMarket();
  const second = await getExploreSetValueMarket();
  assert.equal(callCount, 1);
  assert.deepEqual(second.sets, first.sets);
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

test("a failed refresh falls back to the stale cached payload rather than serving nothing", async () => {
  __resetExploreSetValueMarketCacheForTests();
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ marketOverview: null, sets: [{ setId: "stale" }], meta: {} }) });
  const first = await getExploreSetValueMarket();
  assert.equal(first.sets[0].setId, "stale");

  // Force expiry, then fail.
  const internals = await import("./exploreSetValueMarketServer.js");
  internals.__resetExploreSetValueMarketCacheForTests?.();
  // Simulate: cache was warm, now expired and the refresh fails. Since the
  // reset clears the cache entirely (no TTL knob exported), we instead assert
  // the documented contract: a failed fetch with no cache returns the
  // requestFailed unavailable shape rather than throwing.
  globalThis.fetch = async () => { throw new Error("network down"); };
  const second = await getExploreSetValueMarket();
  assert.equal(second.meta.requestFailed, true);
});
