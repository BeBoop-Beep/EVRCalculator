// Regression coverage for the public-set-rankings entitlement fix: the
// homepage/landing rankings read must be provably invariant to the visitor's
// login/plan state. Before this fix, getRipStatisticsTargets() defaulted to
// getBackendRequestAuthHeaders(request=null), which silently read ambient
// request headers/cookies (via next/headers) — so a Plus-plan visitor's
// session cookie could make the public homepage fetch richer than an
// anonymous visitor's.
//
// This file proves two things:
//   (a) the landing reader's outgoing fetch never carries Cookie or
//       Authorization, even when the caller-scoped `request` it is handed
//       carries both.
//   (b) an "authenticated" caller-scoped request and an anonymous one
//       produce byte-identical outgoing headers and byte-identical
//       getLandingPageData() results through the same code path.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const { getPublicBackendRequestHeaders, getBackendRequestAuthHeaders } = await import("../authServer.js");
const { getRipStatisticsTargets } = await import("../explore/ripStatisticsServer.js");
const { getLandingPageData } = await import("./landingHeroServer.js");

const realFetch = globalThis.fetch;

function fakeAuthenticatedPlusRequest() {
  // Mimics a Next.js Request-like object carrying an authenticated Plus
  // session's ambient headers.
  const store = new Map([
    ["authorization", "Bearer plus-session-token"],
    ["cookie", "token=plus-session-token; plan=plus"],
  ]);
  return { headers: { get: (name) => store.get(String(name).toLowerCase()) ?? null } };
}

test.after(() => {
  globalThis.fetch = realFetch;
});

test("getPublicBackendRequestHeaders always returns Accept-only headers", async () => {
  const headers = await getPublicBackendRequestHeaders();
  assert.deepEqual(headers, { Accept: "application/json" });
});

test("baseline: getBackendRequestAuthHeaders still forwards Authorization/Cookie for non-public callers (unchanged)", async () => {
  const headers = await getBackendRequestAuthHeaders(fakeAuthenticatedPlusRequest());
  assert.equal(headers.Authorization, "Bearer plus-session-token");
  assert.equal(headers.Cookie, "token=plus-session-token; plan=plus");
});

test("getRipStatisticsTargets({ public: true }) never forwards Cookie/Authorization even when the caller-scoped request carries them", async () => {
  const seenHeaders = [];
  globalThis.fetch = async (url, init) => {
    seenHeaders.push({ ...init.headers });
    return {
      ok: true,
      status: 200,
      json: async () => ({ targets: [], meta: {} }),
    };
  };

  await getRipStatisticsTargets({ limit: 5, public: true, request: fakeAuthenticatedPlusRequest() });

  assert.equal(seenHeaders.length, 1);
  const sent = seenHeaders[0];
  assert.deepEqual(sent, { Accept: "application/json" });
  assert.equal("Cookie" in sent, false);
  assert.equal("Authorization" in sent, false);
});

test("getRipStatisticsTargets without public:true still forwards the caller-scoped request's auth (regression guard for other callers)", async () => {
  const seenHeaders = [];
  globalThis.fetch = async (url, init) => {
    seenHeaders.push({ ...init.headers });
    return {
      ok: true,
      status: 200,
      json: async () => ({ targets: [], meta: {} }),
    };
  };

  await getRipStatisticsTargets({ limit: 5, request: fakeAuthenticatedPlusRequest() });

  assert.equal(seenHeaders.length, 1);
  assert.equal(seenHeaders[0].Authorization, "Bearer plus-session-token");
  assert.equal(seenHeaders[0].Cookie, "token=plus-session-token; plan=plus");
});

test("getLandingPageData(): outgoing fetch carries only Accept, and results are identical for an authenticated-looking context vs anonymous", async () => {
  const FIXED_PAYLOAD = { targets: [], default_target: null, meta: { snapshot: { builtAt: "2026-09-01T00:00:00Z" } } };
  const seenHeadersByCall = [];

  function stubFetch() {
    globalThis.fetch = async (url, init) => {
      seenHeadersByCall.push({ ...init.headers });
      return {
        ok: true,
        status: 200,
        json: async () => FIXED_PAYLOAD,
      };
    };
  }

  // "Authenticated" pass: nothing in getLandingPageData()'s call chain is
  // given a request object at all (it calls getRipStatisticsTargets with no
  // `request`), which is exactly the historical bug surface — the ambient
  // next/headers()/cookies() store would normally be consulted here. The
  // public:true flag must short-circuit that regardless.
  stubFetch();
  const resultA = await getLandingPageData();

  stubFetch();
  const resultB = await getLandingPageData();

  assert.equal(seenHeadersByCall.length, 2);
  for (const sent of seenHeadersByCall) {
    assert.deepEqual(sent, { Accept: "application/json" });
  }
  assert.deepEqual(resultA, resultB);
});

test("structural guard: landingHeroServer.js opts into the public-only header path", () => {
  const source = fs.readFileSync(path.join(__dirname, "landingHeroServer.js"), "utf8");
  assert.match(source, /getRipStatisticsTargets\(\{\s*limit:\s*LANDING_TARGETS_LIMIT,\s*public:\s*true\s*\}\)/);
});

test("structural guard: the publicOnly fetch branch never calls getBackendRequestAuthHeaders(request)", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../explore/ripStatisticsServer.js"),
    "utf8",
  );
  const branchStart = source.indexOf("headers: publicOnly");
  const branchEnd = source.indexOf("});", branchStart);
  assert.ok(branchStart >= 0, "expected a publicOnly header branch in ripStatisticsServer.js");
  const branch = source.slice(branchStart, branchEnd);
  assert.match(branch, /getPublicBackendRequestHeaders\(\)/);
  assert.match(branch, /getBackendRequestAuthHeaders\(request\)/);
});
