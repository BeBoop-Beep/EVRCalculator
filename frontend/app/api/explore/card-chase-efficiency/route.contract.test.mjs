import fs from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const source = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");
test("Premium ranking proxy forwards auth and never caches", () => {
  assert.match(source, /headers\.get\(["']authorization["']\)/);
  assert.match(source, /headers\.get\(["']cookie["']\)/);
  assert.match(source, /cache:\s*["']no-store["']/);
  assert.match(source, /private, no-store/);
  assert.match(source, /searchParams\.append/);
});
