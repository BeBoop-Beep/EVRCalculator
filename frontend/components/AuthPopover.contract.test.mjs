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
  assert.match(source, /document\.cookie = serializeOAuthReturnCookie\(destination, \{ secure \}\)/);
  // Cookie must be set before the provider redirect kicks off, not after.
  const cookieIndex = source.indexOf("document.cookie = serializeOAuthReturnCookie");
  const oauthCallIndex = source.indexOf("signInWithOAuth(");
  assert.ok(cookieIndex > -1 && oauthCallIndex > -1 && cookieIndex < oauthCallIndex);
});

test("a failed OAuth initiation clears the transient return-path cookie instead of leaving it stale", () => {
  assert.match(source, /document\.cookie = clearOAuthReturnCookie\(\{ secure: window\.location\.protocol === "https:" \}\)/);
  // The clear must happen in the catch block, after the cookie was set, before the error is surfaced.
  const cookieIndex = source.indexOf("document.cookie = serializeOAuthReturnCookie");
  const catchIndex = source.indexOf("} catch (error) {", cookieIndex);
  const clearIndex = source.indexOf("document.cookie = clearOAuthReturnCookie", catchIndex);
  const dispatchErrorIndex = source.indexOf('dispatch({ type: "error"', clearIndex);
  assert.ok(catchIndex > -1 && clearIndex > catchIndex && dispatchErrorIndex > clearIndex);
});

test("server-generated email links (signup confirmation, password reset) embed next via the query-based builder", () => {
  assert.match(source, /emailRedirectTo: buildAuthCallbackUrlWithNext\(window\.location\.origin, destination\)/);
  assert.match(source, /redirectTo: buildAuthCallbackUrlWithNext\(window\.location\.origin, resetNext\)/);
});
