import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");

test("callback exchanges PKCE code, bridges server-side, and writes only the app cookie", () => {
  assert.match(source, /exchangeCodeForSession/);
  assert.match(source, /exchangeSupabaseSession/);
  assert.match(source, /setAppSessionCookie/);
  assert.doesNotMatch(source, /searchParams\.set\([^,]*(token|access_token)/);
});

test("callback resolves next via the cookie-first mechanism, not by re-deciding it inline", () => {
  assert.match(source, /resolveCallbackNext/);
});

test("callback clears the short-lived OAuth return cookie on every response path", () => {
  const redirectCount = (source.match(/NextResponse\.redirect\(/g) || []).length;
  const clearCount = (source.match(/clearReturnCookie\(/g) || []).length;
  assert.ok(redirectCount >= 3, "expected multiple redirect paths (success, provider error, exchange failure, unexpected error)");
  assert.equal(clearCount, redirectCount + 1, "every redirect (plus the clearReturnCookie definition itself) should route through clearReturnCookie");
});

test("callback treats a provider error param as failure without forwarding it into the redirect", () => {
  assert.match(source, /searchParams\.get\("error"\)/);
  assert.doesNotMatch(source, /errorRedirect\.searchParams\.set\("authError",\s*providerError/);
});

test("callback uses the canonical return-path sanitizer", () => assert.match(source, /sanitizeReturnPath/));
