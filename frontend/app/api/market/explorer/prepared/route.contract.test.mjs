import "../../../../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";

const { GET } = await import("./route.js");
const request = (cookie = "token=premium-session") => ({
  nextUrl: new URL("http://localhost/api/market/explorer/prepared?kind=screen&screen=rarity-leaders&limit=10"),
  headers: { get: (name) => name.toLowerCase() === "cookie" ? cookie : null },
});

test("Premium Screen request reaches the prepared Screen service with its session", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return { status: 200, headers: { get: () => "application/json" }, text: async () => JSON.stringify({ results: [{ market_key: "rarity:sir" }] }) };
  };
  try {
    const response = await GET(request());
    assert.equal(response.status, 200);
    assert.match(calls[0].url, /\/market\/explorer\/prepared-screen\?screen=rarity-leaders&limit=10$/);
    assert.equal(calls[0].init.headers.Cookie, "token=premium-session");
  } finally { globalThis.fetch = originalFetch; }
});

test("Screen backend transport failure preserves a safe structured code", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new TypeError("connection refused"); };
  try {
    const response = await GET(request());
    assert.equal(response.status, 503);
    assert.equal((await response.json()).code, "PREPARED_PROXY_UNAVAILABLE");
  } finally { globalThis.fetch = originalFetch; }
});

test("Prepared constituent pages are forwarded, generation-pinned, with the caller's session", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return { status: 409, headers: { get: () => "application/json" }, text: async () => JSON.stringify({ code: "GENERATION_MISMATCH", generationId: "gen-new" }) };
  };
  try {
    const response = await GET({
      nextUrl: new URL("http://localhost/api/market/explorer/prepared?kind=constituents&marketKey=set%3Ajungle&generationId=gen-old&limit=100&afterRank=0"),
      headers: { get: (name) => name.toLowerCase() === "cookie" ? "token=plus-session" : null },
    });
    assert.equal(response.status, 409, "a generation mismatch reaches the client as a structured 409");
    assert.match(calls[0].url, /\/market\/explorer\/prepared-constituents\?marketKey=set%3Ajungle&generationId=gen-old&limit=100&afterRank=0$/);
    assert.equal(calls[0].init.headers.Cookie, "token=plus-session");
    assert.equal((await response.json()).code, "GENERATION_MISMATCH");
  } finally { globalThis.fetch = originalFetch; }
});

test("Single-market comparison bodies (with entitlement-only context) are forwarded verbatim", async () => {
  const { POST } = await import("./route.js");
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), body: JSON.parse(init.body) });
    return { status: 200, headers: { get: () => "application/json" }, text: async () => "{}" };
  };
  try {
    await POST({ headers: { get: () => null }, json: async () => ({ marketKeys: ["set:jungle"], contextMarketKeys: ["era:ex"] }) });
    assert.match(calls[0].url, /\/market\/explorer\/prepared-comparison$/);
    assert.deepEqual(calls[0].body, { marketKeys: ["set:jungle"], contextMarketKeys: ["era:ex"] });
  } finally { globalThis.fetch = originalFetch; }
});
