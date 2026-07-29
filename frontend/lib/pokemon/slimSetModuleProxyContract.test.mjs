import assert from "node:assert/strict";
import test from "node:test";

import {
  BACKEND_FETCH_TIMEOUT_MS,
  FAILED_ANALYTICS_CACHE_CONTROL,
  PUBLIC_ANALYTICS_CACHE_CONTROL,
  buildSlimSetModuleBackendUrl,
  buildSlimSetModuleProxyErrorBody,
  isAbortError,
  resolveForwardedQueryParams,
  slimSetModuleProxyErrorStatus,
} from "./slimSetModuleProxyContract.mjs";

const BASE = "http://backend.test";

function query(pairs) {
  return new URLSearchParams(pairs);
}

function forwarded(moduleKey, pairs) {
  return Object.fromEntries(resolveForwardedQueryParams(moduleKey, query(pairs)));
}

// ---------------------------------------------------------------------------
// The two drops this branch shipped: overview lost snapshot_contract and
// movers lost movement. Both clients send them (getPokemonSetOverview /
// getPokemonSetMarketMovers in pokemonSetMarketClient.js).
// ---------------------------------------------------------------------------

test("overview forwards snapshot_contract to the backend", () => {
  const params = forwarded("overview", { window: "365d", snapshot_contract: "set-value-v2" });
  assert.equal(params.snapshot_contract, "set-value-v2");
  assert.equal(params.window, "365d");
});

test("movers forwards movement to the backend", () => {
  const params = forwarded("movers", {
    window: "7D",
    limit: "10",
    movement: "all",
    snapshot_contract: "pricing-v4",
  });
  assert.equal(params.movement, "all");
  assert.equal(params.window, "7D");
  assert.equal(params.limit, "10");
  assert.equal(params.snapshot_contract, "pricing-v4");
});

test("movers forwards a non-default movement value unchanged", () => {
  assert.equal(forwarded("movers", { movement: "heating" }).movement, "heating");
  assert.equal(forwarded("movers", { movement: "cooling" }).movement, "cooling");
});

test("top-chase retains window, limit and snapshot_contract", () => {
  const params = forwarded("top-chase", { window: "365d", limit: "10", snapshot_contract: "pricing-v4" });
  assert.deepEqual(params, { window: "365d", limit: "10", snapshot_contract: "pricing-v4" });
});

test("value-history forwards days, snapshot_contract, and renames scope to value_scope", () => {
  const params = forwarded("value-history", { days: "365", scope: "standard", snapshot_contract: "set-value-v2" });
  assert.equal(params.days, "365");
  assert.equal(params.value_scope, "standard");
  assert.equal(params.snapshot_contract, "set-value-v2");
  assert.ok(!("scope" in params), "the backend parameter name is value_scope");
});

test("value-history prefers an explicit value_scope over the scope alias", () => {
  const params = forwarded("value-history", { value_scope: "hits", scope: "standard" });
  assert.equal(params.value_scope, "hits");
});

// ---------------------------------------------------------------------------
// Forwarding must not invent values. An absent param stays absent so the
// backend keeps its own default (e.g. movement -> "all", window -> "30D").
// ---------------------------------------------------------------------------

test("absent and empty params are omitted rather than sent blank", () => {
  assert.deepEqual(forwarded("movers", {}), {});
  assert.deepEqual(forwarded("movers", { window: "", movement: "" }), {});
});

test("only allowlisted params reach the backend", () => {
  const params = forwarded("overview", { window: "365d", limit: "999", movement: "heating", evil: "1" });
  assert.deepEqual(params, { window: "365d" });
});

test("values are forwarded unchanged, never normalized by the proxy", () => {
  // Window meanings, limit semantics and contract-version strings are the
  // client's and the backend's business, not the proxy's.
  const params = forwarded("movers", { window: "7d", limit: "0010", snapshot_contract: "pricing-v4" });
  assert.equal(params.window, "7d");
  assert.equal(params.limit, "0010");
});

// ---------------------------------------------------------------------------
// Backend URL construction
// ---------------------------------------------------------------------------

test("backend URL uses the module's backend path and encodes the set id", () => {
  const url = buildSlimSetModuleBackendUrl({
    baseUrl: BASE,
    moduleKey: "movers",
    setId: "ascended heroes",
    searchParams: query({ window: "7D", movement: "all" }),
  });
  assert.equal(url.pathname, "/tcgs/pokemon/sets/ascended%20heroes/market/movers");
  assert.equal(url.searchParams.get("movement"), "all");
});

test("each module targets its own backend path", () => {
  const pathFor = (moduleKey) =>
    buildSlimSetModuleBackendUrl({ baseUrl: BASE, moduleKey, setId: "s", searchParams: query({}) }).pathname;
  assert.equal(pathFor("overview"), "/tcgs/pokemon/sets/s/overview");
  assert.equal(pathFor("top-chase"), "/tcgs/pokemon/sets/s/market/top-chase");
  assert.equal(pathFor("movers"), "/tcgs/pokemon/sets/s/market/movers");
  assert.equal(pathFor("value-history"), "/tcgs/pokemon/sets/s/market/value-history");
});

test("an unknown module key fails loudly instead of proxying to a wrong path", () => {
  assert.throws(() => resolveForwardedQueryParams("not-a-module", query({})), /Unknown slim set module proxy contract/);
});

// ---------------------------------------------------------------------------
// Bounded completion policy
// ---------------------------------------------------------------------------

test("the backend fetch timeout is bounded and conservative", () => {
  assert.ok(Number.isFinite(BACKEND_FETCH_TIMEOUT_MS), "timeout must be a finite number of ms");
  assert.ok(BACKEND_FETCH_TIMEOUT_MS >= 5_000, "must not be so short it fails healthy slow reads");
  assert.ok(BACKEND_FETCH_TIMEOUT_MS <= 20_000, "must be short enough that a stall becomes a retryable error");
});

test("a timeout is a retryable 504 and a transport failure a retryable 502", () => {
  assert.equal(slimSetModuleProxyErrorStatus(true), 504);
  assert.equal(slimSetModuleProxyErrorStatus(false), 502);

  const timedOut = buildSlimSetModuleProxyErrorBody({ moduleKey: "movers", setId: "s", timedOut: true });
  assert.equal(timedOut.code, "POKEMON_SET_MARKET_MOVERS_PROXY_TIMEOUT");
  assert.equal(timedOut.retryable, true);
  assert.match(timedOut.message, /timed out/i);

  const failed = buildSlimSetModuleProxyErrorBody({ moduleKey: "movers", setId: "s", timedOut: false });
  assert.equal(failed.code, "POKEMON_SET_MARKET_MOVERS_PROXY_ERROR");
  assert.equal(failed.retryable, true);
});

test("each module reports its own error code so one failure is attributable", () => {
  const codeFor = (moduleKey) =>
    buildSlimSetModuleProxyErrorBody({ moduleKey, setId: "s", timedOut: true }).code;
  assert.equal(codeFor("overview"), "POKEMON_SET_OVERVIEW_PROXY_TIMEOUT");
  assert.equal(codeFor("top-chase"), "POKEMON_SET_TOP_CHASE_PROXY_TIMEOUT");
  assert.equal(codeFor("value-history"), "POKEMON_SET_VALUE_HISTORY_PROXY_TIMEOUT");
});

test("abort errors are recognized as timeouts", () => {
  assert.ok(isAbortError({ name: "AbortError" }));
  assert.ok(isAbortError(new Error("The operation was aborted")));
  assert.ok(!isAbortError(new Error("ECONNREFUSED")));
});

test("failed responses are never cached and successful ones keep the public policy", () => {
  assert.equal(FAILED_ANALYTICS_CACHE_CONTROL, "no-store");
  assert.equal(PUBLIC_ANALYTICS_CACHE_CONTROL, "public, s-maxage=300, stale-while-revalidate=3600");
});
