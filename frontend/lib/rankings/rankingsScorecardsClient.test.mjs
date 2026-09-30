import assert from "node:assert/strict";
import test from "node:test";
import { createRankingsSessionCache } from "./rankingsSessionCache.mjs";
import { readRankingsScorecards, scorecardSetTarget } from "./rankingsScorecardsClient.mjs";

test("one entity payload is reused across tab reads", async () => {
  let calls = 0;
  const fetchImpl = async (url, init) => {
    calls += 1;
    assert.equal(url, "/api/tcgs/pokemon/rankings/scorecards?entity_type=set");
    assert.deepEqual(init, { credentials: "include", cache: "no-store" });
    return { ok: true, json: async () => ({ status: "available", rows: [{ entityId: "s1" }] }) };
  };
  const sessionCache = createRankingsSessionCache("paid-user");
  await readRankingsScorecards("set", { fetchImpl, sessionCache });
  await readRankingsScorecards("set", { fetchImpl, sessionCache });
  assert.equal(calls, 1);
});

test("set scorecard identity maps artwork without deriving a score", () => {
  assert.deepEqual(scorecardSetTarget({ entityId: "s1", name: "Set", canonicalKey: "set", logoImageUrl: "logo.png", symbolImageUrl: "symbol.png", era: { eraId: "e1", eraName: "Era" } }), { target_type: "set", target_id: "s1", setId: "s1", name: "Set", canonical_key: "set", era: "Era", eraId: "e1", logo_image_url: "logo.png", symbol_image_url: "symbol.png" });
});
