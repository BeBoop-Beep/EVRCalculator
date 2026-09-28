import assert from "node:assert/strict";
import test from "node:test";
import {
  beginLastGoodRefresh,
  failLastGoodRefresh,
  isRenderableEraState,
  isRenderableProductState,
  isRenderableSetState,
} from "./rankingsLastGoodState.mjs";

const error = new Error("N+1 unavailable");

for (const [name, ready, predicate] of [
  ["Era", { status: "ready", contract: { eras: [1] }, benchmark: { rows: [1] }, cacheIdentity: "user-a:publication-n" }, isRenderableEraState],
  ["Set", { status: "ready", targets: [{ id: 1 }], benchmark: { rows: [1] }, cacheIdentity: "user-a:publication-n" }, isRenderableSetState],
  ["Product", { status: "ready", productFamilyRankings: { families: {} }, benchmark: { rows: [1] } }, isRenderableProductState],
]) {
  test(`${name} keeps valid N renderable while N+1 loads and fails`, () => {
    const loading = beginLastGoodRefresh(ready, predicate);
    assert.equal(loading.status, "ready");
    assert.equal(loading.refreshing, true);
    assert.equal(predicate(loading), true);
    const failed = failLastGoodRefresh(loading, error, predicate, {});
    assert.equal(failed.status, "ready");
    assert.equal(failed.refreshing, false);
    assert.equal(failed.refreshError, error.message);
    assert.equal(predicate(failed), true);
    assert.equal(failed.contract || failed.targets || failed.productFamilyRankings, ready.contract || ready.targets || ready.productFamilyRankings);
  });
}

test("an initial failure with no valid prior payload is destructive", () => {
  const loading = beginLastGoodRefresh({ status: "idle", contract: null }, isRenderableEraState);
  assert.equal(loading.status, "loading");
  const failed = failLastGoodRefresh(loading, error, isRenderableEraState, { contract: null, benchmark: null });
  assert.equal(failed.status, "error");
  assert.equal(failed.error, error.message);
  assert.equal(isRenderableEraState(failed), false);
});
