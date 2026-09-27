import "../../../../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";

const { GET } = await import("./route.js");
const request = (qs) => ({ url: `http://localhost/api/market/explorer/asset-options?${qs}`, headers: { get: () => null }, signal: undefined });

test("forwards a valid asset, no-store, passes the DB-published payload through", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url) => { calls.push(String(url)); return { ok: true, status: 200, json: async () => ({ asset: "sealed", types: [] }) }; };
  try {
    const response = await GET(request("asset=sealed"));
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.match(calls[0], /\/market\/explorer\/asset-options\?asset=sealed$/);
    assert.deepEqual(await response.json(), { asset: "sealed", types: [] });
    assert.equal((await GET(request("asset=weapons"))).status, 400);
  } finally { globalThis.fetch = original; }
});

test("upstream failure returns a structured code, never raw error text", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 500, json: async () => ({ message: "syntax error at or near", code: "ASSET_OPTIONS_FAILED" }) });
  try {
    const response = await GET(request("asset=cards"));
    const body = await response.json();
    assert.equal(response.status, 503);
    assert.doesNotMatch(JSON.stringify(body), /syntax error/);
  } finally { globalThis.fetch = original; }
});
