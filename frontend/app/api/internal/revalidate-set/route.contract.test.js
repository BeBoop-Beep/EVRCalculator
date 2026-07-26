const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const routePath = path.resolve(__dirname, "route.js");
const source = fs.readFileSync(routePath, "utf8");

test("revalidate-set route invalidates the shell cache tag", () => {
  assert.ok(
    source.includes("`pokemon-set-shell:${setId}`"),
    "must revalidate the pokemon-set-shell:<setId> tag"
  );
  assert.ok(source.includes("revalidateTag(shellTag)"), "must call revalidateTag on the shell tag");
});

test("revalidate-set route invalidates the overview cache tag per window", () => {
  assert.ok(
    source.includes("`pokemon-set-overview:${setId}:${window}`"),
    "must revalidate the pokemon-set-overview:<setId>:<window> tag"
  );
  assert.ok(source.includes("revalidateTag(overviewTag)"), "must call revalidateTag on the overview tag");
});

test("revalidate-set route is guarded by a shared secret", () => {
  assert.ok(source.includes("SET_REVALIDATION_SECRET"), "must read SET_REVALIDATION_SECRET");
  assert.ok(source.includes("x-revalidate-secret"), "must read the x-revalidate-secret header");
  assert.ok(source.includes('status: 401'), "must return 401 when unauthorized");
});

test("revalidate-set route requires a setId", () => {
  assert.ok(source.includes('code: "SET_ID_REQUIRED"'), "must reject requests without setId");
});

test("revalidate-set route refuses when the secret is unconfigured", () => {
  // isAuthorized returns false when SET_REVALIDATION_SECRET is empty — no
  // anonymous cache busting.
  assert.ok(
    source.includes("if (!expected)") && source.includes("return false"),
    "must refuse (not allow) when the secret env var is unset"
  );
});
