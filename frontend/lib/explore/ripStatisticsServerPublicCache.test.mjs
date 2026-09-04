// Production stability effort (2026-09-04): the publicOnly cohort (used by
// the Homepage landing reader) must get a bounded process cache + in-flight
// join, while the authenticated cohort must remain uncached (entitlement
// safety — see ripStatisticsServerCacheIdentity.test.mjs).

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";

const { getRipStatisticsTargets, __resetRipStatisticsTargetsCacheForTests } = await import(
  "./ripStatisticsServer.js"
);

const realFetch = globalThis.fetch;
test.after(() => { globalThis.fetch = realFetch; });

function stubOkFetch(onCall) {
  return async (...args) => {
    onCall?.(...args);
    return {
      ok: true,
      status: 200,
      json: async () => ({ targets: [{ targetId: "set-1" }], meta: { snapshot: { builtAt: "t0" } } }),
    };
  };
}

test("a warm publicOnly request inside the TTL makes no backend request", async () => {
  __resetRipStatisticsTargetsCacheForTests();
  let callCount = 0;
  globalThis.fetch = stubOkFetch(() => { callCount += 1; });
  await getRipStatisticsTargets({ limit: 60, public: true });
  await getRipStatisticsTargets({ limit: 60, public: true });
  assert.equal(callCount, 1);
});

test("concurrent publicOnly misses join a single in-flight backend request", async () => {
  __resetRipStatisticsTargetsCacheForTests();
  let callCount = 0;
  globalThis.fetch = async (...args) => {
    callCount += 1;
    await new Promise((resolve) => setTimeout(resolve, 10));
    return stubOkFetch()(...args);
  };
  await Promise.all([
    getRipStatisticsTargets({ limit: 60, public: true }),
    getRipStatisticsTargets({ limit: 60, public: true }),
  ]);
  assert.equal(callCount, 1);
});

test("the authenticated (non-public) path is never cached across calls", async () => {
  __resetRipStatisticsTargetsCacheForTests();
  let callCount = 0;
  globalThis.fetch = stubOkFetch(() => { callCount += 1; });
  await getRipStatisticsTargets({ limit: 60, public: false });
  await getRipStatisticsTargets({ limit: 60, public: false });
  assert.equal(callCount, 2, "authenticated reads must hit the backend every time");
});
