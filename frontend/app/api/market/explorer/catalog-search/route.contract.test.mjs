import "../../../../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";

const { GET } = await import("./route.js");
const request = (qs, cookie = "token=t", authorization = "Bearer x") => ({
  url: `http://localhost/api/market/explorer/catalog-search?${qs}`,
  headers: { get: (name) => ({ cookie, authorization })[name.toLowerCase()] ?? null },
  signal: undefined,
});
const withFetch = async (impl, fn) => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), init }); return impl(url, init); };
  try { return await fn(calls); } finally { globalThis.fetch = original; }
};

test("forwards cookie + authorization, bounds limit, never caches", async () => {
  await withFetch(async () => ({ ok: true, status: 200, json: async () => ({ results: [{ label: "Fossil" }] }) }), async (calls) => {
    const response = await GET(request("asset=cards&q=fossil&limit=500"));
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("cache-control"), "no-store");
    const url = new URL(calls[0].url);
    assert.equal(url.pathname, "/market/explorer/catalog/search");
    assert.equal(url.searchParams.get("limit"), "50");
    assert.equal(url.searchParams.get("asset"), "cards");
    assert.equal(calls[0].init.headers.cookie, "token=t");
    assert.equal(calls[0].init.headers.authorization, "Bearer x");
    assert.equal(calls[0].init.cache, "no-store");
    assert.deepEqual((await response.json()).results, [{ label: "Fossil" }]);
  });
});

test("validates q min length and asset without touching the backend", async () => {
  await withFetch(async () => { throw new Error("must not fetch"); }, async (calls) => {
    assert.equal((await GET(request("asset=cards&q=g"))).status, 400);
    assert.equal((await GET(request("asset=weapons&q=gengar"))).status, 400);
    assert.equal(calls.length, 0);
  });
});

test("never leaks raw upstream error text; structured failure codes only", async () => {
  await withFetch(async () => ({ ok: false, status: 500, json: async () => ({ message: "PostgREST: relation \"x\" does not exist", code: "PGRST205" }) }), async () => {
    const response = await GET(request("asset=cards&q=gengar"));
    const body = await response.json();
    assert.equal(response.status, 503);
    assert.doesNotMatch(JSON.stringify(body), /PostgREST|relation/);
    assert.ok(body.code);
  });
  await withFetch(async () => { throw new TypeError("connect ECONNREFUSED"); }, async () => {
    const response = await GET(request("asset=sealed&q=gengar"));
    assert.equal(response.status, 503);
    assert.equal((await response.json()).code, "CATALOG_SEARCH_PROXY_UNAVAILABLE");
  });
});
