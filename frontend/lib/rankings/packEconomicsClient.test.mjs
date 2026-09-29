import assert from "node:assert/strict";
import test from "node:test";
import { createRankingsSessionCache } from "./rankingsSessionCache.mjs";
import { readPackEconomics } from "./packEconomicsClient.mjs";

test("Pack Economics is fetched once and reused on tab revisit", async () => {
  let calls = 0;
  const fetchImpl = async (url, init) => { calls += 1; assert.equal(url, "/api/tcgs/pokemon/rankings/pack-economics"); assert.deepEqual(init, { credentials: "include", cache: "no-store" }); return { ok: true, json: async () => ({ status: "available", sets: [{ setId: "s1" }] }) }; };
  const sessionCache = createRankingsSessionCache("plus");
  await readPackEconomics({ fetchImpl, sessionCache });
  await readPackEconomics({ fetchImpl, sessionCache });
  assert.equal(calls, 1);
});
