import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const layout = fs.readFileSync(path.resolve("app/layout.js"), "utf8");
const rankingsHook = fs.readFileSync(path.resolve("lib/rankings/useRankingsAccess.js"), "utf8");
const authContext = fs.readFileSync(path.resolve("components/AuthContext.js"), "utf8");

test("root auth resolution cannot seed entitlement from a 150ms timeout", () => {
  assert.ok(layout.includes("await getAuthenticatedUserFromCookies()"));
  assert.ok(!layout.includes("getAuthenticatedUserFromCookiesWithTimeout"));
  assert.ok(!layout.includes("WithTimeout(150)"));
});

test("Rankings remains reactive to the current AuthContext user", () => {
  assert.ok(rankingsHook.includes("const auth = useAuth()"));
  assert.ok(rankingsHook.includes("resolveRankingsAccess(auth?.user)"));
});

test("a same-page login hydrates identity before refreshing entitlement-aware RSC", () => {
  const refreshStart = authContext.indexOf("const refreshUser");
  const refreshEnd = authContext.indexOf("const login", refreshStart);
  const refreshBlock = authContext.slice(refreshStart, refreshEnd);
  const userUpdate = refreshBlock.indexOf("setUser(nextUser)");
  assert.ok(userUpdate >= 0);
  assert.ok(refreshBlock.indexOf("router.refresh()", userUpdate) > userUpdate);
  assert.match(refreshBlock, /setAuthStatus\("resolving"\)/);
  assert.match(refreshBlock, /finally[\s\S]*setAuthStatus\("resolved"\)/);
  assert.match(rankingsHook, /requestKey: `\$\{identity\}:\$\{access\.accessMode\}`/);
});
