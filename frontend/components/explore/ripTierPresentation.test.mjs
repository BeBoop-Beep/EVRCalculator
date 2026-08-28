import assert from "node:assert/strict";
import test from "node:test";
import { publicLeaderScoreTier } from "./ripTierPresentation.mjs";

test("component display tiers mirror canonical public leader score bands", () => {
  assert.equal(publicLeaderScoreTier(95.49), "A");
  assert.equal(publicLeaderScoreTier(95.5), "S");
  assert.equal(publicLeaderScoreTier(89.5), "A");
  assert.equal(publicLeaderScoreTier(79.5), "B");
  assert.equal(publicLeaderScoreTier(64.5), "C");
  assert.equal(publicLeaderScoreTier(49.5), "D");
  assert.equal(publicLeaderScoreTier(49.49), "F");
  assert.equal(publicLeaderScoreTier(null), null);
});
