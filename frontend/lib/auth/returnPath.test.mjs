import assert from "node:assert/strict";
import test from "node:test";
import { buildAuthCallbackUrl, normalizeAuthOrigin, sanitizeReturnPath } from "./returnPath.mjs";

test("allows internal paths and retains safe query strings", () => {
  assert.equal(sanitizeReturnPath("/TCGs/Pokemon?tab=market"), "/TCGs/Pokemon?tab=market");
});

for (const value of ["https://evil.example", "//evil.example", "/\\evil.example", "/%5cevil.example", "javascript:alert(1)", "data:text/html,x", "%2f%2fevil.example"]) {
  test(`rejects unsafe return path ${value}`, () => assert.equal(sanitizeReturnPath(value), "/"));
}

test("removes sensitive auth parameters", () => {
  assert.equal(sanitizeReturnPath("/Market?code=secret&tab=sets&access_token=nope"), "/Market?tab=sets");
});

test("preserves the initiating HTTP origin for PKCE callbacks", () => {
  assert.equal(normalizeAuthOrigin("https://inthedex.io"), "https://inthedex.io");
  assert.equal(normalizeAuthOrigin("https://www.inthedex.io/some/path"), "https://www.inthedex.io");
  assert.equal(normalizeAuthOrigin("http://localhost:3000"), "http://localhost:3000");
});

test("builds the exact localhost callback used by development", () => {
  assert.equal(
    buildAuthCallbackUrl("http://localhost:3000", "/TCGs/Pokemon?tab=market"),
    "http://localhost:3000/auth/callback?next=%2FTCGs%2FPokemon%3Ftab%3Dmarket",
  );
});

test("builds the production callback and sanitizes the return destination", () => {
  assert.equal(
    buildAuthCallbackUrl("https://inthedex.io", "/Market?code=secret&tab=sets"),
    "https://inthedex.io/auth/callback?next=%2FMarket%3Ftab%3Dsets",
  );
});

test("keeps www callbacks on www when that host initiates PKCE", () => {
  assert.equal(
    buildAuthCallbackUrl("https://www.inthedex.io", "/Rankings"),
    "https://www.inthedex.io/auth/callback?next=%2FRankings",
  );
});
