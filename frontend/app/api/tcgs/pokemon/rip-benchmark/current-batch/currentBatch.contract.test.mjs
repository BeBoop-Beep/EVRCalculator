import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");

test("Product batch route bounds backend fanout and rejects browser model authority", () => {
  assert.match(source, /entities\.length > 200/);
  assert.match(source, /entities\.slice\(index \* 10, index \* 10 \+ 10\)/);
  assert.match(source, /benchmark_key !== undefined/);
  assert.match(source, /calibration_version !== undefined/);
  assert.match(source, /MIXED_BENCHMARK_GENERATIONS/);
});

test("Product batch route forwards user auth and stays private", () => {
  assert.match(source, /headers\.Authorization = authorization/);
  assert.match(source, /headers\.Cookie = cookie/);
  assert.match(source, /private, no-store/);
  assert.doesNotMatch(source, /service.role|service_role|SUPABASE_SERVICE/);
});
