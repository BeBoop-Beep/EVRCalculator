import test from "node:test";
import assert from "node:assert/strict";

import {
  FAILED_ANALYTICS_CACHE_CONTROL,
  PUBLIC_ANALYTICS_CACHE_CONTROL,
  resolveSlimSetModuleCacheControl,
} from "./slimSetModuleProxyContract.mjs";

// Regression contract: `public, s-maxage=300, stale-while-revalidate=3600` let a
// CDN/edge keep answering /overview with a payload whose Opening Profit vs Cost
// history ended on the previous market date for up to an hour AFTER the
// market-dashboard row had been rebuilt. Overview must not be shared-cached.

test("overview successes are never shared-cached", () => {
  assert.equal(resolveSlimSetModuleCacheControl("overview", { ok: true }), "no-store");
});

test("overview failures are no-store", () => {
  assert.equal(resolveSlimSetModuleCacheControl("overview", { ok: false }), "no-store");
});

test("the other slim modules keep the shared public analytics policy", () => {
  for (const moduleKey of ["top-chase", "movers", "sealed", "value-history"]) {
    assert.equal(
      resolveSlimSetModuleCacheControl(moduleKey, { ok: true }),
      PUBLIC_ANALYTICS_CACHE_CONTROL,
      `${moduleKey} success policy must be unchanged`
    );
    assert.equal(
      resolveSlimSetModuleCacheControl(moduleKey, { ok: false }),
      FAILED_ANALYTICS_CACHE_CONTROL,
      `${moduleKey} failure policy must stay no-store`
    );
  }
});

test("an unknown module falls back to the shared policy rather than throwing", () => {
  assert.equal(resolveSlimSetModuleCacheControl("unknown-module", { ok: true }), PUBLIC_ANALYTICS_CACHE_CONTROL);
  assert.equal(resolveSlimSetModuleCacheControl("unknown-module", { ok: false }), FAILED_ANALYTICS_CACHE_CONTROL);
});

test("omitting the ok flag is treated as a failure, never as a cacheable success", () => {
  assert.equal(resolveSlimSetModuleCacheControl("top-chase"), FAILED_ANALYTICS_CACHE_CONTROL);
});
