const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const routePath = path.resolve(__dirname, "route.js");
const source = fs.readFileSync(routePath, "utf8");

// Query forwarding, the bounded timeout and the cache-control policy are all
// implemented once in lib/pokemon/slimSetModuleProxy*, and are covered
// behaviourally by lib/pokemon/slimSetModuleProxyContract.test.mjs plus
// lib/pokemon/slimSetModuleProxyRoute.contract.test.js. This file only pins
// that the route delegates there with the right module key, so it cannot grow
// a divergent copy of the proxy again.

test("overview route delegates to the shared slim set module proxy", () => {
  assert.ok(
    source.includes('from "@/lib/pokemon/slimSetModuleProxyRoute"'),
    "must import the shared slim set module proxy"
  );
  assert.ok(
    source.includes('proxySlimSetModuleRequest("overview", request, context)'),
    'must delegate with the "overview" module key'
  );
});

test("overview route does not re-implement the proxy locally", () => {
  assert.ok(!source.includes("await fetch("), "must not hand-roll its own backend fetch");
  assert.ok(!source.includes("PUBLIC_ANALYTICS_CACHE_CONTROL"), "must not hand-roll its own cache-control policy");
  assert.ok(
    !source.includes('searchParams?.get("window")'),
    "must not hand-roll param forwarding outside the shared contract table"
  );
});
