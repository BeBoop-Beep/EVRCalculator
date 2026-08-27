import fs from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const source = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");
test("exact-card Premium proxy forwards auth and variant identity", () => {
  assert.match(source, /headers\.get\(["']authorization["']\)/);
  assert.match(source, /headers\.get\(["']cookie["']\)/);
  assert.match(source, /variant_id/);
  assert.match(source, /cache:\s*["']no-store["']/);
});
