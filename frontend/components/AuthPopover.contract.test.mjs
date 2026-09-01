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

test("provider redirects use the stable, query-free canonical auth callback builder", () => {
  assert.match(source, /const callbackUrl = \(\) => buildAuthCallbackUrl\(window\.location\.origin\)/);
});

test("the OAuth return destination is stored in the short-lived cookie before redirecting to the provider", () => {
  assert.match(source, /document\.cookie = serializeOAuthReturnCookie\(destination, \{ secure: window\.location\.protocol === "https:" \}\)/);
  // Cookie must be set before the provider redirect kicks off, not after.
  const cookieIndex = source.indexOf("document.cookie = serializeOAuthReturnCookie");
  const oauthCallIndex = source.indexOf("signInWithOAuth(");
  assert.ok(cookieIndex > -1 && oauthCallIndex > -1 && cookieIndex < oauthCallIndex);
});

test("server-generated email links (signup confirmation, password reset) embed next via the query-based builder", () => {
  assert.match(source, /emailRedirectTo: buildAuthCallbackUrlWithNext\(window\.location\.origin, destination\)/);
  assert.match(source, /redirectTo: buildAuthCallbackUrlWithNext\(window\.location\.origin, resetNext\)/);
});
