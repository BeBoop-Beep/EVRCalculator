import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./AuthPopover.js", import.meta.url), "utf8");

test("Google OAuth is one continue flow available from login and signup", () => {
  assert.match(source, /const showProviders = \["login", "signup"\]\.includes\(state\.mode\)/);
  assert.match(source, /const continueWithProvider = async \(provider\)/);
  assert.match(source, /signInWithOAuth\(\{ provider, options: \{ redirectTo: callbackUrl\(\) \} \}\)/);
  assert.match(source, /onClick=\{\(\) => continueWithProvider\("google"\)\}/);
});

test("provider redirects use the canonical auth callback builder", () => {
  assert.match(source, /buildAuthCallbackUrl\(window\.location\.origin, next\)/);
});
