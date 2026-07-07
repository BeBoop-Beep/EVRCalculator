import assert from "node:assert/strict";
import test from "node:test";

import { getPokemonSetInsights } from "./pokemonSetInsightsClient.js";

// ---------------------------------------------------------------------------
// Phase 6C: getPokemonSetInsights had no in-flight join. The Insights fetch
// effect already had a request-key ref (so /insights only fired once per
// activation), but a concurrent StrictMode remount duplicate could still slip
// through the ref's release-on-cleanup window — the client-level join closes
// that. Same guard pattern as pokemonSetMarketClient.js /
// pokemonSetCardsClient.js.
// ---------------------------------------------------------------------------

function makeInsightsPayload() {
  return {
    set: { id: "set-1", name: "Test Set", slug: "testSet" },
    summary: {},
    recommendation: {},
    ripScore: {},
    interpretation: {},
    ripStatistics: {},
    outcomeDistribution: { percentiles: [], distributionBins: [], thresholdBins: [] },
    simulationDrivers: [],
    rarityContribution: [],
    historyTrend: [],
    desirability: {},
    desirabilityValidation: {},
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

test("getPokemonSetInsights joins concurrent identical calls into a single fetch", async () => {
  const stub = stubFetchJson(() => makeInsightsPayload());
  try {
    const [first, second] = await Promise.all([
      getPokemonSetInsights("set-dedupe-ins"),
      getPokemonSetInsights("set-dedupe-ins"),
    ]);
    assert.equal(stub.getCallCount(), 1, "two concurrent identical calls must issue exactly one network fetch");
    assert.deepEqual(first, second);

    await getPokemonSetInsights("set-dedupe-ins");
    assert.equal(stub.getCallCount(), 2, "a call after the first resolves must fetch again, not reuse a stale in-flight entry");
  } finally {
    stub.restore();
  }
});

test("getPokemonSetInsights does not join calls for a different set id", async () => {
  const stub = stubFetchJson(() => makeInsightsPayload());
  try {
    await Promise.all([
      getPokemonSetInsights("set-dedupe-ins-a"),
      getPokemonSetInsights("set-dedupe-ins-b"),
    ]);
    assert.equal(stub.getCallCount(), 2, "distinct set ids must not be joined together");
  } finally {
    stub.restore();
  }
});
