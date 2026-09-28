import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
const proxy = fs.readFileSync(new URL("../../../../../lib/rankings/ripBenchmarkProxy.js", import.meta.url), "utf8");
const currentBatch = fs.readFileSync(new URL("./current-batch/route.js", import.meta.url), "utf8");
const financialHistory = fs.readFileSync(new URL("./financial-history/route.js", import.meta.url), "utf8");
const overview = fs.readFileSync(new URL("./overview-headlines/route.js", import.meta.url), "utf8");
test("Benchmark proxy forwards identity, preserves upstream status, and disables caching", () => { for (const value of ["Authorization", "Cookie", "response.status", '"Cache-Control": "private, no-store"', 'Vary: "Cookie, Authorization"']) assert.ok(proxy.includes(value)); });
test("browser cannot select benchmark authority", () => { assert.ok(proxy.includes("benchmark_key")); assert.ok(proxy.includes("calibration_version")); assert.ok(proxy.includes("MODEL_AUTHORITY_FORBIDDEN")); assert.ok(!proxy.includes("service_role")); });

test("Product batch and Financial history remain thin caller-identity proxies", () => {
  assert.match(currentBatch, /proxyRipBenchmark\(request, "current-batch"\)/);
  assert.match(financialHistory, /proxyRipBenchmark\(request, "financial-history"\)/);
  assert.doesNotMatch(currentBatch, /Promise\.all\(chunks/);
  assert.doesNotMatch(currentBatch, /service_role/);
  assert.doesNotMatch(financialHistory, /service_role/);
});

test("Overview headlines is a public cacheable projection with no caller identity forwarding", () => {
  assert.match(overview, /\/tcgs\/pokemon\/rip-benchmark\/overview-headlines/);
  assert.match(overview, /s-maxage=300/);
  assert.doesNotMatch(overview, /Authorization|request\.headers|get\("cookie"\)/);
});
