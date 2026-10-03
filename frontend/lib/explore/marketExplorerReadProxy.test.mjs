import test from "node:test";
import assert from "node:assert/strict";
import { EXPLORER_REQUEST_BOUNDS_MS } from "./marketExplorerBoundedRequest.mjs";
import {
  EXPLORER_PROXY_BOUNDS_MS,
  fetchExplorerRead,
  isRetryableExplorerRead,
} from "./marketExplorerReadProxy.mjs";

const response = (status, body) => ({
  status,
  ok: status >= 200 && status < 300,
  headers: new Headers({ "content-type": "application/json" }),
  text: async () => JSON.stringify(body),
});

test("an approximately eight-second proxy response cannot lose to the browser deadline", async () => {
  const clock = [0, 8007];
  const result = await fetchExplorerRead({
    url: "http://backend/prepared",
    timeoutMs: EXPLORER_PROXY_BOUNDS_MS.prepared,
    operation: "prepared",
    fetchImpl: async () => response(200, { markets: [] }),
    now: () => clock.shift() ?? 8007,
    setTimer: () => 1,
    clearTimer: () => {},
  });
  assert.equal(result.elapsedMs, 8007);
  assert.ok(EXPLORER_PROXY_BOUNDS_MS.prepared > 8007);
  assert.ok(EXPLORER_REQUEST_BOUNDS_MS.prepared > EXPLORER_PROXY_BOUNDS_MS.prepared);
  assert.ok(EXPLORER_REQUEST_BOUNDS_MS.constituents > EXPLORER_PROXY_BOUNDS_MS.constituents);
  assert.ok(EXPLORER_REQUEST_BOUNDS_MS.assetOptions > EXPLORER_PROXY_BOUNDS_MS.assetOptions);
  assert.ok(EXPLORER_REQUEST_BOUNDS_MS.search > EXPLORER_PROXY_BOUNDS_MS.catalogSearch);
});

test("one transient PGRST002 503 succeeds on the single retry", async () => {
  let calls = 0;
  const result = await fetchExplorerRead({
    url: "http://backend/options",
    timeoutMs: 6500,
    operation: "asset_options",
    fetchImpl: async () => ++calls === 1
      ? response(503, { code: "PGRST002" })
      : response(200, { types: [] }),
  });
  assert.equal(calls, 2);
  assert.equal(result.attempts, 2);
  assert.equal(result.response.status, 200);
});

test("auth, entitlement, invalid, unknown, and generation mismatch are never retried", async () => {
  for (const scenario of [
    [400, "PREPARED_COMPARISON_INVALID"],
    [401, "AUTH_REQUIRED"],
    [403, "ACTIVE_MARKET_LIMIT"],
    [404, "UNKNOWN_MARKET"],
    [409, "GENERATION_MISMATCH"],
  ]) {
    let calls = 0;
    const result = await fetchExplorerRead({
      url: "http://backend/read",
      timeoutMs: 6500,
      operation: "test",
      fetchImpl: async () => { calls += 1; return response(scenario[0], { code: scenario[1] }); },
    });
    assert.equal(calls, 1, scenario[1]);
    assert.equal(result.response.status, scenario[0]);
  }
});

test("retry classification is narrow and excludes deterministic timeouts", () => {
  assert.equal(isRetryableExplorerRead({ status: 503, code: "PGRST002" }), true);
  assert.equal(isRetryableExplorerRead({ status: 503, code: "ASSET_OPTIONS_UNAVAILABLE" }), false);
  assert.equal(isRetryableExplorerRead({ status: 504, code: "PREPARED_COMPARISON_TIMEOUT" }), false);
  assert.equal(isRetryableExplorerRead({ status: 409, code: "GENERATION_MISMATCH" }), false);
});
