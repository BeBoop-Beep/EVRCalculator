import assert from "node:assert/strict";
import test from "node:test";
import {
  AUTH_RESOLUTION,
  canonicalUsersEqual,
  createAuthRequestCoordinator,
  reconcileAuthResult,
  resolveCurrentUser,
} from "./clientAuthLifecycle.mjs";

const existingUser = {
  id: "user-1",
  email: "collector@example.com",
  username: "collector",
  display_name: "Card Collector",
  avatar_url: "https://example.test/avatar.png",
  index_plan: "plus",
  preferences: { theme: "dark" },
};

function response(status, payload) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => payload,
  };
}

test("canonical resolver requests the cookie-backed endpoint without caching", async () => {
  const calls = [];
  const result = await resolveCurrentUser({
    fetchImpl: async (...args) => {
      calls.push(args);
      return response(200, { user: existingUser });
    },
  });

  assert.equal(result.kind, AUTH_RESOLUTION.AUTHENTICATED);
  assert.deepEqual(result.user, existingUser);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/api/auth/me");
  assert.equal(calls[0][1].credentials, "include");
  assert.equal(calls[0][1].cache, "no-store");
});

test("200 reconciliation retains the complete canonical profile", async () => {
  const canonical = { ...existingUser, display_name: "Updated", extra_profile_field: "kept" };
  const result = await resolveCurrentUser({ fetchImpl: async () => response(200, { user: canonical }) });
  const reconciled = reconcileAuthResult(existingUser, result);
  assert.equal(reconciled.changed, true);
  assert.deepEqual(reconciled.user, canonical);
});

for (const status of [401, 403]) {
  test(`${status} is authoritative and clears the user`, async () => {
    const result = await resolveCurrentUser({ fetchImpl: async () => response(status, {}) });
    assert.deepEqual(reconcileAuthResult(existingUser, result), {
      user: null,
      changed: true,
      degraded: false,
    });
  });
}

test("500 preserves the existing authenticated presentation", async () => {
  const result = await resolveCurrentUser({ fetchImpl: async () => response(500, {}) });
  assert.deepEqual(reconcileAuthResult(existingUser, result), {
    user: existingUser,
    changed: false,
    degraded: true,
  });
});

test("network and parse failures preserve the existing authenticated presentation", async () => {
  const network = await resolveCurrentUser({ fetchImpl: async () => { throw new Error("offline"); } });
  const parse = await resolveCurrentUser({
    fetchImpl: async () => ({ status: 200, ok: true, json: async () => { throw new SyntaxError("bad json"); } }),
  });
  assert.equal(reconcileAuthResult(existingUser, network).user, existingUser);
  assert.equal(reconcileAuthResult(existingUser, parse).user, existingUser);
  assert.equal(network.kind, AUTH_RESOLUTION.TRANSIENT_FAILURE);
  assert.equal(parse.kind, AUTH_RESOLUTION.TRANSIENT_FAILURE);
});

test("unchanged canonical state does not request an auth revision", () => {
  const reordered = {
    preferences: { theme: "dark" },
    index_plan: "plus",
    display_name: "Card Collector",
    username: "collector",
    avatar_url: "https://example.test/avatar.png",
    email: "collector@example.com",
    id: "user-1",
  };
  assert.equal(canonicalUsersEqual(existingUser, reordered), true);
  assert.equal(reconcileAuthResult(existingUser, {
    kind: AUTH_RESOLUTION.AUTHENTICATED,
    user: reordered,
  }).changed, false);
});

test("a stale route response cannot overwrite a newer request", () => {
  const coordinator = createAuthRequestCoordinator();
  const routeB = coordinator.begin("soft");
  const routeC = coordinator.begin("soft");
  assert.equal(routeB.controller.signal.aborted, true);
  assert.equal(coordinator.isCurrent(routeB), false);
  assert.equal(coordinator.isCurrent(routeC), true);
});

test("strong explicit refresh wins over background reconciliation", () => {
  const coordinator = createAuthRequestCoordinator();
  const routeSync = coordinator.begin("soft");
  const loginRefresh = coordinator.begin("strong");
  const ignoredNavigation = coordinator.begin("soft");
  assert.equal(routeSync.controller.signal.aborted, true);
  assert.equal(ignoredNavigation, null);
  assert.equal(coordinator.isCurrent(loginRefresh), true);
});
