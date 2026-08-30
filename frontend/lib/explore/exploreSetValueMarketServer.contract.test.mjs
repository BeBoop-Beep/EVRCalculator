// The Market server adapter must carry the WHOLE published snapshot contract.
//
// The regression this guards: the adapter used to rebuild the response as
// { sets, meta } and silently dropped `marketOverview`, so the published Raw /
// Top 10 Chase index families never reached the page.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";

const SNAPSHOT = {
  marketOverview: {
    contractVersion: "pokemon-market-overview-v1",
    marketDate: "2024-03-04",
    coverage: { eligibleSetCount: 3, rawCardCount: 111, chaseCardCount: 30, cohortFingerprint: "abc" },
    raw: { basketValue: 1234.5, indexValue: 104.5, historyStartDate: "2024-01-01", changes: {}, trend: [] },
    topChase: { basketValue: 555.5, indexValue: 97.25, historyStartDate: "2024-01-01", changes: {}, trend: [] },
  },
  sets: [{ setId: "set-a", currentSetValue: 10 }],
  initialSelectedSetMovers: { setId: "set-a", window: "7d", movers: [{ cardId: "card-a" }] },
  meta: { snapshot: { marketDate: "2024-03-04" } },
};

const { normalizeExploreSetValueMarket, unavailableExploreSetValueMarket } = await import("./exploreSetValueMarketServer.js");

const realFetch = globalThis.fetch;
const realNow = Date.now;

function stubFetch(handler) {
  globalThis.fetch = async (...args) => handler(...args);
}

test.after(() => {
  globalThis.fetch = realFetch;
  Date.now = realNow;
});

test("the adapter preserves marketOverview, sets, the default 7D movers seed and meta", () => {
  const payload = normalizeExploreSetValueMarket(SNAPSHOT);

  assert.deepEqual(Object.keys(payload).sort(), ["initialSelectedSetMovers", "marketOverview", "meta", "sets"]);
  assert.equal(payload.marketOverview.contractVersion, "pokemon-market-overview-v1");
  assert.equal(payload.marketOverview.raw.indexValue, 104.5);
  assert.equal(payload.marketOverview.topChase.basketValue, 555.5);
  assert.equal(payload.sets.length, 1);
  assert.equal(payload.initialSelectedSetMovers.window, "7d");
  assert.equal(payload.initialSelectedSetMovers.movers.length, 1);
  assert.equal(payload.meta.snapshot.marketDate, "2024-03-04");
});

test("a stale cached payload still carries its marketOverview when the request fails", () => {
  const payload = unavailableExploreSetValueMarket(normalizeExploreSetValueMarket(SNAPSHOT));

  assert.equal(payload.meta.stale, true);
  assert.equal(payload.meta.requestFailed, true);
  assert.ok(payload.marketOverview, "stale fallback must not drop marketOverview");
  assert.equal(payload.marketOverview.raw.indexValue, 104.5);
  assert.equal(payload.sets.length, 1);
  assert.equal(payload.initialSelectedSetMovers.window, "7d");
});
