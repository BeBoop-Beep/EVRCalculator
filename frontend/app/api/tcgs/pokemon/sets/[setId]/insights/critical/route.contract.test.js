const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const routePath = path.resolve(__dirname, "route.js");
const source = fs.readFileSync(routePath, "utf8");

test("critical insights route sends no-store for successful responses", () => {
  assert.ok(
    source.includes('const PUBLIC_ANALYTICS_CACHE_CONTROL = "no-store"'),
    'successful responses must use Cache-Control: no-store'
  );
  assert.ok(
    source.includes("proxyResponse.ok ? PUBLIC_ANALYTICS_CACHE_CONTROL : FAILED_ANALYTICS_CACHE_CONTROL"),
    "successful responses must select the no-store success cache policy"
  );
  assert.ok(source.includes('"Cache-Control": cacheControl,'), "the selected cache policy must be sent in the response");
});

test("critical insights route keeps failed responses as no-store", () => {
  assert.ok(
    source.includes('const FAILED_ANALYTICS_CACHE_CONTROL = "no-store"'),
    'failed responses must keep Cache-Control: no-store'
  );
});
