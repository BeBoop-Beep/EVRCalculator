import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");
test("Pack Economics proxy is a thin caller-identity no-store boundary", () => {
  assert.match(source, /headers\.Authorization = authorization/);
  assert.match(source, /headers\.Cookie = cookie/);
  assert.match(source, /cache: "no-store"/);
  assert.match(source, /"Cache-Control": "private, no-store"/);
  assert.match(source, /Vary: "Cookie, Authorization"/);
  assert.match(source, /status: response\.status/);
  assert.doesNotMatch(source, /index_plan|canViewRankingsIntelligence/);
});
