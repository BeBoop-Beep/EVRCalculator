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
  const authResolution = refreshBlock.indexOf('runAuthResolution("strong")');
  assert.ok(authResolution >= 0);
  assert.ok(refreshBlock.indexOf("router.refresh()", authResolution) > authResolution);
  assert.match(rankingsHook, /requestKey: `\$\{identity\}:\$\{access\.accessMode\}`/);
});

test("server initialUser owns first paint and route changes use one soft reconciliation", () => {
  assert.match(authContext, /useState\(initialUser\)/);
  assert.match(authContext, /if \(!initialUser\) void syncUser\(\)/);
  assert.match(authContext, /if \(previousPathname !== pathname\) void syncUser\(\)/);
  assert.match(authContext, /const syncUser = useCallback\(\(\) => runAuthResolution\("soft"\)/);
  const syncStart = authContext.indexOf("const syncUser");
  const refreshStart = authContext.indexOf("const refreshUser", syncStart);
  assert.ok(!authContext.slice(syncStart, refreshStart).includes("router.refresh"));
});

test("latest auth request wins and a soft sync cannot supersede strong refresh", () => {
  assert.match(authContext, /createAuthRequestCoordinator\(\)/);
  assert.match(authContext, /requestCoordinatorRef\.current\.begin\(mode\)/);
  assert.match(authContext, /requestCoordinatorRef\.current\.isCurrent\(request\)/);
});

test("only meaningful canonical auth changes increment authRevision", () => {
  const commitStart = authContext.indexOf("const commitUser");
  const resolutionStart = authContext.indexOf("const runAuthResolution", commitStart);
  const commitBlock = authContext.slice(commitStart, resolutionStart);
  assert.match(commitBlock, /canonicalUsersEqual/);
  assert.equal((commitBlock.match(/setAuthRevision/g) || []).length, 1);
});
