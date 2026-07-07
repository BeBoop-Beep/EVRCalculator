import assert from "node:assert/strict";
import test from "node:test";

import { getPokemonSetPullRates } from "./pokemonSetPullRatesClient.js";

// ---------------------------------------------------------------------------
// Phase 6C: getPokemonSetPullRates had no in-flight join, so a browser
// measurement showed /pull-rates firing 3-4x per Pull Rates tab activation
// (StrictMode remounts plus dep-driven effect re-runs). Same guard pattern as
// pokemonSetMarketClient.js / pokemonSetCardsClient.js.
// ---------------------------------------------------------------------------

function makePullRatesPayload() {
  return {
    set: { id: "set-1", name: "Test Set", slug: "testSet" },
    pullRates: { groups: [], rows: [] },
    packPaths: [],
    rarityBuckets: [],
    assumptions: {},
    sources: [],
    meta: { warnings: [] },
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

test("getPokemonSetPullRates joins concurrent identical calls into a single fetch", async () => {
  const stub = stubFetchJson(() => makePullRatesPayload());
  try {
    const [first, second] = await Promise.all([
      getPokemonSetPullRates("set-dedupe-pr"),
      getPokemonSetPullRates("set-dedupe-pr"),
    ]);
    assert.equal(stub.getCallCount(), 1, "two concurrent identical calls must issue exactly one network fetch");
    assert.deepEqual(first, second);

    await getPokemonSetPullRates("set-dedupe-pr");
    assert.equal(stub.getCallCount(), 2, "a call after the first resolves must fetch again, not reuse a stale in-flight entry");
  } finally {
    stub.restore();
  }
});

test("getPokemonSetPullRates does not join calls for a different set id", async () => {
  const stub = stubFetchJson(() => makePullRatesPayload());
  try {
    await Promise.all([
      getPokemonSetPullRates("set-dedupe-pr-a"),
      getPokemonSetPullRates("set-dedupe-pr-b"),
    ]);
    assert.equal(stub.getCallCount(), 2, "distinct set ids must not be joined together");
  } finally {
    stub.restore();
  }
});
