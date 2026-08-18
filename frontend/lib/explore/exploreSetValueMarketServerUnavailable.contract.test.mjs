// The cold-cache unavailable shape, in its own file because the adapter's
// process cache is module-level and a warm entry from another test would mask
// the branch under test.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";

const { getExploreSetValueMarket } = await import("./exploreSetValueMarketServer.js");

const realFetch = globalThis.fetch;
test.after(() => { globalThis.fetch = realFetch; });

test("with no cache at all the unavailable shape still declares all three keys", async () => {
  globalThis.fetch = async () => ({ ok: false, json: async () => ({}) });
  const payload = await getExploreSetValueMarket();

  assert.deepEqual(Object.keys(payload).sort(), ["marketOverview", "meta", "sets"]);
  assert.equal(payload.marketOverview, null);
  assert.deepEqual(payload.sets, []);
  assert.equal(payload.meta.requestFailed, true);
});
