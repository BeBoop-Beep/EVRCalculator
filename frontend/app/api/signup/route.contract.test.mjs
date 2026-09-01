import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");

test("signup confirmation uses the canonical auth callback builder", () => {
  assert.match(source, /buildAuthCallbackUrl\(new URL\(request\.url\)\.origin, next\)/);
  assert.match(source, /emailRedirectTo: callback/);
});
