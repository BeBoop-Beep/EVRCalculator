import test from "node:test";
import assert from "node:assert/strict";
import { PREFLIGHT_STATE, buildErrorMessage, preflightRequestSpec, resolvePreflightState } from "./marketExplorerPreflight.mjs";

test("preflight accepts only Filtered Cards and strips ranking/exact fields", () => {
  assert.deepEqual(preflightRequestSpec({ asset: "cards", eraIds: ["sv"], setIds: [], segmentIds: ["legend"], pokemonIds: ["6"], priceSegmentIds: [], releaseAgeCohortIds: [], mode: "chase", topN: 10, instrumentIds: ["stale"] }), {
    eraIds: ["sv"], setIds: [], segmentIds: ["legend"], pokemonIds: ["6"], priceSegmentIds: [], releaseAgeCohortIds: [],
  });
  assert.equal(preflightRequestSpec({ asset: "cards", membershipMode: "explicit" }), null);
  assert.equal(preflightRequestSpec({ asset: "sealed" }), null);
});

test("one match is ready while empty and projection lag remain distinct", () => {
  assert.equal(resolvePreflightState({ readiness: "PREFLIGHT_READY", matchingConstituentCount: 1 }), PREFLIGHT_STATE.ready);
  assert.equal(resolvePreflightState({ queryOutcome: "QUERY_EMPTY_NOW" }), PREFLIGHT_STATE.empty);
  assert.equal(resolvePreflightState({ readiness: "PREFLIGHT_PROJECTION_LAGGING", matchingConstituentCount: 0 }), PREFLIGHT_STATE.unavailable);
});

test("typed build outcomes have distinct user-facing behavior", () => {
  for (const code of ["QUERY_EMPTY_NOW", "QUERY_NO_HISTORY", "QUERY_BUILDING", "QUERY_CACHE_REFRESHING", "QUERY_RATE_LIMITED", "QUERY_INVALID", "QUERY_UNAVAILABLE", "QUERY_FAILED"]) {
    assert.ok(buildErrorMessage({ code, retryAfter: 15 }).length > 5, code);
  }
  assert.match(buildErrorMessage({ code: "QUERY_RATE_LIMITED", retryAfter: 15 }), /15 seconds/);
});
