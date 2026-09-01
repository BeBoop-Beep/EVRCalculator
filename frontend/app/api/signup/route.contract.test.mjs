import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");

test("signup confirmation uses a trusted, configured application origin, not the raw request Host", () => {
  assert.match(source, /buildAuthCallbackUrlWithNext\(getFrontendBaseUrl\(\), next\)/);
  assert.match(source, /emailRedirectTo: callback/);
  assert.doesNotMatch(source, /new URL\(request\.url\)\.origin/);
  assert.doesNotMatch(source, /request\.headers\.get\(["']host["']\)/i);
});
