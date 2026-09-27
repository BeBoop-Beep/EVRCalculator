import "../../../../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";

const { GET } = await import("./route.js");
const request = (qs) => ({ url: `http://localhost/api/market/explorer/leaf-search?${qs}`, signal: undefined });
const withFetch = async (impl, fn) => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), init }); return impl(url, init); };
  try { return await fn(calls); } finally { globalThis.fetch = original; }
};

test("leaf search proxies only the physical-leaf endpoint and never caches", async () => {
  const upstream = { query: "gengar", items: [{ asset: "cards", instrumentId: "variant-1", displayName: "Gengar" }], availability: "AVAILABLE" };
  await withFetch(async () => ({ ok: true, status: 200, json: async () => upstream }), async (calls) => {
    const response = await GET(request("asset=cards&q=gengar&limit=12"));
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("cache-control"), "no-store");
    const url = new URL(calls[0].url);
    assert.equal(url.pathname, "/market/explorer/leaves/search");
    assert.equal(url.searchParams.get("asset"), "cards");
    assert.equal(calls[0].init.cache, "no-store");
    assert.deepEqual((await response.json()).items, upstream.items);
  });
});

test("leaf search validates inputs and sanitizes upstream errors", async () => {
  await withFetch(async () => { throw new Error("must not fetch"); }, async (calls) => {
    assert.equal((await GET(request("asset=cards&q=g"))).status, 400);
    assert.equal((await GET(request("asset=unknown&q=gengar"))).status, 400);
    assert.equal((await GET(request("asset=cards&q=gengar&limit=51"))).status, 400);
    assert.equal(calls.length, 0);
  });
  await withFetch(async () => ({ ok: false, status: 500, json: async () => ({ message: "database secret", code: "LEAF_BACKEND_FAILED" }) }), async () => {
    const response = await GET(request("asset=sealed&q=booster"));
    const body = await response.json();
    assert.equal(response.status, 503);
    assert.equal(body.code, "LEAF_BACKEND_FAILED");
    assert.doesNotMatch(JSON.stringify(body), /database secret/);
  });
});
