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

test("callback uses the canonical return-path sanitizer", () => assert.match(source, /sanitizeReturnPath/));
