import assert from "node:assert/strict";
import test from "node:test";

import { buildDeploymentIdentity } from "./deploymentIdentity.mjs";


test("prefers Vercel deployment identity when available", () => {
  const result = buildDeploymentIdentity({
    VERCEL: "1",
    VERCEL_GIT_COMMIT_SHA: "a".repeat(40),
    VERCEL_GIT_COMMIT_REF: "main",
    VERCEL_ENV: "production",
    GIT_SHA: "b".repeat(40),
  });
  assert.deepEqual(result, {
    status: "ok",
    build: "a".repeat(40),
    ref: "main",
    environment: "production",
    provider: "vercel",
  });
});

test("falls back to generic/local build identity without exposing other env values", () => {
  const result = buildDeploymentIdentity({
    GIT_SHA: "c".repeat(40),
    GIT_BRANCH: "develop",
    NODE_ENV: "test",
    DATABASE_URL: "must-not-leak",
  });
  assert.deepEqual(result, {
    status: "ok",
    build: "c".repeat(40),
    ref: "develop",
    environment: "test",
    provider: "local",
  });
  assert.equal(JSON.stringify(result).includes("must-not-leak"), false);
});

test("development fallback is explicit when no deployment SHA exists", () => {
  const result = buildDeploymentIdentity({ NODE_ENV: "development" });
  assert.equal(result.build, "development");
  assert.equal(result.ref, null);
  assert.equal(result.environment, "development");
});
