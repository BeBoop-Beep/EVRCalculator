import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
const proxy = fs.readFileSync(new URL("../../../../../lib/rankings/ripBenchmarkProxy.js", import.meta.url), "utf8");
test("Benchmark proxy forwards identity, preserves upstream status, and disables caching", () => { for (const value of ["Authorization", "Cookie", "response.status", '"Cache-Control": "private, no-store"', 'Vary: "Cookie, Authorization"']) assert.ok(proxy.includes(value)); });
test("browser cannot select benchmark authority", () => { assert.ok(proxy.includes("benchmark_key")); assert.ok(proxy.includes("calibration_version")); assert.ok(proxy.includes("MODEL_AUTHORITY_FORBIDDEN")); assert.ok(!proxy.includes("service_role")); });
