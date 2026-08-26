import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const layout = fs.readFileSync(path.resolve("app/layout.js"), "utf8");
const rankingsHook = fs.readFileSync(path.resolve("lib/rankings/useRankingsAccess.js"), "utf8");

test("root auth resolution cannot seed entitlement from a 150ms timeout", () => {
  assert.ok(layout.includes("await getAuthenticatedUserFromCookies()"));
  assert.ok(!layout.includes("getAuthenticatedUserFromCookiesWithTimeout"));
  assert.ok(!layout.includes("WithTimeout(150)"));
});

test("Rankings remains reactive to the current AuthContext user", () => {
  assert.ok(rankingsHook.includes("const auth = useAuth()"));
  assert.ok(rankingsHook.includes("resolveRankingsAccess(auth?.user)"));
});
