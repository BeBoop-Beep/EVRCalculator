import assert from "node:assert/strict";
import test from "node:test";

import {
  AUTH_CANARY_NAVIGATION,
  AuthCanaryError,
  authIdentityFingerprint,
  authenticatedUserFromPayload,
  loadAuthCanaryConfig,
  safeAuthCanaryConfigSummary,
  safeAuthCanaryFailure,
} from "./authCanary.mjs";


test("auth canary config requires explicit HTTPS credentials", () => {
  assert.throws(() => loadAuthCanaryConfig({}), /auth_canary_base_url_missing/);
  assert.throws(
    () =>
      loadAuthCanaryConfig({
        SENTINEL_AUTH_CANARY_BASE_URL: "http://example.com",
        SENTINEL_AUTH_CANARY_EMAIL: "qa@example.com",
        SENTINEL_AUTH_CANARY_PASSWORD: "secret",
      }),
    /auth_canary_base_url_requires_https/,
  );

  const config = loadAuthCanaryConfig({
    SENTINEL_AUTH_CANARY_BASE_URL: "https://index.example.test/some/path",
    SENTINEL_AUTH_CANARY_EMAIL: "qa@example.com",
    SENTINEL_AUTH_CANARY_PASSWORD: "secret",
    SENTINEL_AUTH_CANARY_TIMEOUT_MS: "12345",
  });
  assert.equal(config.baseUrl, "https://index.example.test");
  assert.equal(config.timeoutMs, 12345);
});

test("localhost HTTP remains available for local QA only", () => {
  const config = loadAuthCanaryConfig({
    SENTINEL_AUTH_CANARY_BASE_URL: "http://127.0.0.1:3000",
    SENTINEL_AUTH_CANARY_EMAIL: "qa@example.com",
    SENTINEL_AUTH_CANARY_PASSWORD: "secret",
  });
  assert.equal(config.baseUrl, "http://127.0.0.1:3000");
});

test("safe config summary never exposes email or password", () => {
  const config = loadAuthCanaryConfig({
    SENTINEL_AUTH_CANARY_BASE_URL: "https://index.example.test",
    SENTINEL_AUTH_CANARY_EMAIL: "qa@example.com",
    SENTINEL_AUTH_CANARY_PASSWORD: "super-secret-value",
  });
  const rendered = JSON.stringify(safeAuthCanaryConfigSummary(config));
  assert.equal(rendered.includes("qa@example.com"), false);
  assert.equal(rendered.includes("super-secret-value"), false);
  assert.equal(rendered.includes("credentialsConfigured"), true);
});

test("identity fingerprint is stable and opaque", () => {
  const one = authIdentityFingerprint({ id: "user-123", email: "qa@example.com" });
  const two = authIdentityFingerprint({ id: "user-123", email: "other@example.com" });
  const three = authIdentityFingerprint({ id: "user-456" });
  assert.equal(one, two);
  assert.notEqual(one, three);
  assert.equal(one.length, 16);
  assert.equal(one.includes("user-123"), false);
});

test("me payload must be authenticated and structured", () => {
  assert.deepEqual(authenticatedUserFromPayload(200, { user: { id: "u1" } }), { id: "u1" });
  assert.throws(() => authenticatedUserFromPayload(401, {}), /auth_canary_me_http_error/);
  assert.throws(
    () => authenticatedUserFromPayload(200, { user: null }),
    /auth_canary_me_payload_invalid/,
  );
});

test("navigation contract covers the user-reported cross-page surfaces", () => {
  assert.deepEqual(
    AUTH_CANARY_NAVIGATION.map((entry) => entry.pathname),
    ["/Market", "/Rankings", "/TCGs/Pokemon/Sets"],
  );
});

test("safe failure exposes only stage and controlled code", () => {
  const failure = safeAuthCanaryFailure(
    new AuthCanaryError("auth_canary_header_logged_out"),
    "Rankings",
  );
  assert.deepEqual(failure, {
    status: "failed",
    stage: "Rankings",
    code: "auth_canary_header_logged_out",
  });
});
