import assert from "node:assert/strict";
import test from "node:test";
import { sanitizeReturnPath } from "./returnPath.mjs";

test("allows internal paths and retains safe query strings", () => {
  assert.equal(sanitizeReturnPath("/TCGs/Pokemon?tab=market"), "/TCGs/Pokemon?tab=market");
});

for (const value of ["https://evil.example", "//evil.example", "/\\evil.example", "/%5cevil.example", "javascript:alert(1)", "data:text/html,x", "%2f%2fevil.example"]) {
  test(`rejects unsafe return path ${value}`, () => assert.equal(sanitizeReturnPath(value), "/"));
}

test("removes sensitive auth parameters", () => {
  assert.equal(sanitizeReturnPath("/Market?code=secret&tab=sets&access_token=nope"), "/Market?tab=sets");
});
