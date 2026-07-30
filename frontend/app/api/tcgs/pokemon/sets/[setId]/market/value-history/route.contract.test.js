const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const routePath = path.resolve(__dirname, "route.js");
const source = fs.readFileSync(routePath, "utf8");

// See lib/pokemon/slimSetModuleProxyContract.test.mjs for the behavioural
// days / scope->value_scope / snapshot_contract forwarding proof.

test("value-history route delegates to the shared slim set module proxy", () => {
  assert.ok(
    source.includes('from "@/lib/pokemon/slimSetModuleProxyRoute"'),
    "must import the shared slim set module proxy"
  );
  assert.ok(
    source.includes('proxySlimSetModuleRequest("value-history", request, context)'),
    'must delegate with the "value-history" module key'
  );
});

test("value-history route does not re-implement the proxy locally", () => {
  assert.ok(!source.includes("await fetch("), "must not hand-roll its own backend fetch");
  assert.ok(!source.includes("PUBLIC_ANALYTICS_CACHE_CONTROL"), "must not hand-roll its own cache-control policy");
});
