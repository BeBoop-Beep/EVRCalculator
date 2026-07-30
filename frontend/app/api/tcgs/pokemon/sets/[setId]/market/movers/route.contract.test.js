const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const routePath = path.resolve(__dirname, "route.js");
const source = fs.readFileSync(routePath, "utf8");

// See lib/pokemon/slimSetModuleProxyContract.test.mjs for the behavioural
// window/limit/movement/snapshot_contract forwarding proof — movement was the
// param this proxy used to drop.

test("movers route delegates to the shared slim set module proxy", () => {
  assert.ok(
    source.includes('from "@/lib/pokemon/slimSetModuleProxyRoute"'),
    "must import the shared slim set module proxy"
  );
  assert.ok(
    source.includes('proxySlimSetModuleRequest("movers", request, context)'),
    'must delegate with the "movers" module key'
  );
});

test("movers route does not re-implement the proxy locally", () => {
  assert.ok(!source.includes("await fetch("), "must not hand-roll its own backend fetch");
  assert.ok(!source.includes("PUBLIC_ANALYTICS_CACHE_CONTROL"), "must not hand-roll its own cache-control policy");
});
