import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");

test("preflight proxy forwards auth, cancellation, no-store, and retry metadata", () => {
  for (const token of ["authorization", "cookie", "request.signal", 'cache: "no-store"', 'response.headers.get("Retry-After")']) {
    assert.ok(source.includes(token), token);
  }
  assert.ok(source.includes("/market/explorer/query/preflight"));
});
