// The same-origin Explorer proxy.
//
// This is the hop the ordinary browser session actually uses. The app's session
// is an HttpOnly `token` cookie set by /api/auth/login at path "/", so a
// same-origin fetch attaches it automatically and this route's only job is to
// carry it to the backend, which reads it through the same `_extract_token`
// path /auth/me uses.
//
// Tested here rather than only against an injected Authorization fixture,
// because an injected header proves the BACKEND works and says nothing about
// whether a logged-in browser is authenticated.

// The register hook resolves the `@/` alias the route imports.
import "../../../../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";

const { GET, POST } = await import("./route.js");

const SESSION_COOKIE = "token=eyJhbGciOiJIUzI1NiJ9.session; theme=dark";

function captureBackend(response) {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return response;
  };
  return { calls, restore: () => { globalThis.fetch = originalFetch; } };
}

const backendResponse = (status, body, contentType = "application/json") => ({
  status,
  headers: { get: (name) => (name.toLowerCase() === "content-type" ? contentType : null) },
  text: async () => JSON.stringify(body),
});

const request = (headers = {}) => {
  const lower = Object.fromEntries(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]));
  return {
    headers: { get: (name) => lower[String(name).toLowerCase()] ?? null },
    json: async () => ({ asset: "cards", mode: "all" }),
  };
};

test("the browser session cookie is carried to the backend on options", async () => {
  const backend = captureBackend(backendResponse(200, { eras: [], sets: [] }));
  try {
    const response = await GET(request({ cookie: SESSION_COOKIE }));
    assert.equal(response.status, 200);
    assert.equal(backend.calls.length, 1);
    assert.match(backend.calls[0].url, /\/market\/explorer\/query\/options$/);
    assert.equal(backend.calls[0].init.headers.Cookie, SESSION_COOKIE,
      "without this forward, a logged-in user is anonymous to the backend");
  } finally {
    backend.restore();
  }
});

test("the same session cookie is carried on the query POST", async () => {
  const backend = captureBackend(backendResponse(200, { queryFingerprint: "fp", trend: [] }));
  try {
    const response = await POST(request({ cookie: SESSION_COOKIE, "content-type": "application/json" }));
    assert.equal(response.status, 200);
    assert.equal(backend.calls[0].init.method, "POST");
    assert.equal(backend.calls[0].init.headers.Cookie, SESSION_COOKIE);
  } finally {
    backend.restore();
  }
});

test("no session means no forged credential — the 401 is passed through intact", async () => {
  const backend = captureBackend(backendResponse(401, { detail: "Not authenticated" }));
  try {
    const response = await GET(request({}));
    assert.equal(response.status, 401);
    assert.equal(backend.calls[0].init.headers.Cookie, undefined);
    assert.equal(backend.calls[0].init.headers.Authorization, undefined,
      "the proxy must never invent a credential the browser did not send");
    // The client distinguishes causes off this status, so it must survive.
    assert.deepEqual(JSON.parse(await response.text()), { detail: "Not authenticated" });
  } finally {
    backend.restore();
  }
});

test("an Authorization header is still honoured for non-browser callers", async () => {
  const backend = captureBackend(backendResponse(200, {}));
  try {
    await GET(request({ authorization: "Bearer abc" }));
    assert.equal(backend.calls[0].init.headers.Authorization, "Bearer abc");
  } finally {
    backend.restore();
  }
});

test("authenticated responses are never cached", async () => {
  const backend = captureBackend(backendResponse(200, {}));
  try {
    const response = await GET(request({ cookie: SESSION_COOKIE }));
    assert.equal(response.headers.get("Cache-Control"), "private, no-store");
    assert.equal(backend.calls[0].init.cache, "no-store");
  } finally {
    backend.restore();
  }
});

test("a malformed body is rejected before it reaches the backend", async () => {
  const backend = captureBackend(backendResponse(200, {}));
  try {
    const response = await POST({
      headers: { get: () => null },
      json: async () => { throw new SyntaxError("bad json"); },
    });
    assert.equal(response.status, 400);
    assert.equal(backend.calls.length, 0);
  } finally {
    backend.restore();
  }
});
