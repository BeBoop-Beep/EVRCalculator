import test from "node:test";
import assert from "node:assert/strict";
import { reconcilePreparedWorkspace } from "./marketExplorerEntitlementReset.mjs";

test("Premium to Plus deterministically keeps at most three prepared markets", () => {
  assert.deepEqual(reconcilePreparedWorkspace({ plan: "plus", loadedKeys: ["a", "b", "c", "d", "e"], legacyKeys: ["raw", "sealedMarket"] }), {
    keepLoadedKeys: ["a", "b", "c"], fallbackLegacyKey: null, limit: 3,
  });
});

test("Plus to Basic keeps exactly one prepared market and has a legal fallback", () => {
  assert.deepEqual(reconcilePreparedWorkspace({ plan: "basic", loadedKeys: ["set:jungle", "set:fossil"] }), {
    keepLoadedKeys: ["set:jungle"], fallbackLegacyKey: null, limit: 1,
  });
  assert.equal(reconcilePreparedWorkspace({ plan: "basic", legacyKeys: ["sealedMarket", "raw"] }).fallbackLegacyKey, "sealedMarket");
  assert.equal(reconcilePreparedWorkspace({ plan: "basic" }).fallbackLegacyKey, "raw");
});
