import assert from "node:assert/strict";
import test from "node:test";
import { buildAuthCallbackUrl, buildAuthCallbackUrlWithNext, normalizeAuthOrigin, sanitizeReturnPath } from "./returnPath.mjs";

test("allows internal paths and retains safe query strings", () => {
  assert.equal(sanitizeReturnPath("/TCGs/Pokemon?tab=market"), "/TCGs/Pokemon?tab=market");
});

for (const value of ["https://evil.example", "//evil.example", "/\\evil.example", "/%5cevil.example", "javascript:alert(1)", "data:text/html,x", "%2f%2fevil.example"]) {
  test(`rejects unsafe return path ${value}`, () => assert.equal(sanitizeReturnPath(value), "/"));
}

test("rejects control characters, including URL-encoded ones", () => {
  assert.equal(sanitizeReturnPath("/foo" + String.fromCharCode(10) + "bar"), "/");
  assert.equal(sanitizeReturnPath("/foo" + String.fromCharCode(0) + "bar"), "/");
  assert.equal(sanitizeReturnPath("/foo%0abar"), "/");
});

test("removes sensitive auth parameters", () => {
  assert.equal(sanitizeReturnPath("/Market?code=secret&tab=sets&access_token=nope"), "/Market?tab=sets");
  assert.equal(sanitizeReturnPath("/x?token_hash=abc&refresh_token=def&token=ghi&keep=1"), "/x?keep=1");
});

test("falls back to a custom default", () => {
  assert.equal(sanitizeReturnPath("not-a-path", "/fallback"), "/fallback");
});

test("does not depend on any single production canonical domain to validate a path", () => {
  // The sanitizer must accept the same safe relative path regardless of which
  // real hostname (apex, www, localhost) it will eventually be joined to.
  assert.equal(sanitizeReturnPath("/Rankings"), "/Rankings");
});

test("normalizeAuthOrigin accepts well-formed http(s) origins and rejects the rest", () => {
  assert.equal(normalizeAuthOrigin("https://inthedex.io"), "https://inthedex.io");
  assert.equal(normalizeAuthOrigin("https://www.inthedex.io/some/path"), "https://www.inthedex.io");
  assert.equal(normalizeAuthOrigin("http://localhost:3000"), "http://localhost:3000");
  assert.equal(normalizeAuthOrigin("javascript:alert(1)"), null);
  assert.equal(normalizeAuthOrigin("not a url"), null);
  assert.equal(normalizeAuthOrigin(""), null);
  assert.equal(normalizeAuthOrigin(null), null);
});

test("buildAuthCallbackUrl is stable and query-free regardless of destination", () => {
  assert.equal(buildAuthCallbackUrl("http://localhost:3000"), "http://localhost:3000/auth/callback");
  assert.equal(buildAuthCallbackUrl("https://inthedex.io"), "https://inthedex.io/auth/callback");
  assert.equal(buildAuthCallbackUrl("https://www.inthedex.io"), "https://www.inthedex.io/auth/callback");
});

test("buildAuthCallbackUrl throws rather than silently falling back for an invalid origin", () => {
  assert.throws(() => buildAuthCallbackUrl("javascript:alert(1)"));
  assert.throws(() => buildAuthCallbackUrl(""));
});

test("buildAuthCallbackUrlWithNext embeds a sanitized next for server-generated email links", () => {
  assert.equal(
    buildAuthCallbackUrlWithNext("http://localhost:3000", "/TCGs/Pokemon?tab=market"),
    "http://localhost:3000/auth/callback?next=%2FTCGs%2FPokemon%3Ftab%3Dmarket",
  );
  assert.equal(
    buildAuthCallbackUrlWithNext("https://inthedex.io", "/Market?code=secret&tab=sets"),
    "https://inthedex.io/auth/callback?next=%2FMarket%3Ftab%3Dsets",
  );
});
