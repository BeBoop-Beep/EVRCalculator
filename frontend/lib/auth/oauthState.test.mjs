import assert from "node:assert/strict";
import test from "node:test";
import { OAUTH_RETURN_COOKIE, OAUTH_RETURN_COOKIE_MAX_AGE, clearOAuthReturnCookie, resolveCallbackNext, serializeOAuthReturnCookie } from "./oauthState.mjs";

test("serializeOAuthReturnCookie sanitizes the path and sets a short-lived, same-site cookie", () => {
  const cookie = serializeOAuthReturnCookie("/Market?tab=sets");
  assert.match(cookie, new RegExp(`^${OAUTH_RETURN_COOKIE}=%2FMarket%3Ftab%3Dsets`));
  assert.match(cookie, /Path=\//);
  assert.match(cookie, new RegExp(`Max-Age=${OAUTH_RETURN_COOKIE_MAX_AGE}`));
  assert.match(cookie, /SameSite=Lax/);
  assert.match(cookie, /Secure/);
});

test("serializeOAuthReturnCookie omits Secure on non-https (local dev)", () => {
  const cookie = serializeOAuthReturnCookie("/Market", { secure: false });
  assert.doesNotMatch(cookie, /Secure/);
});

test("serializeOAuthReturnCookie refuses to store an unsafe destination", () => {
  const cookie = serializeOAuthReturnCookie("https://evil.example");
  assert.match(cookie, new RegExp(`^${OAUTH_RETURN_COOKIE}=%2F(;|$)`));
});

test("clearOAuthReturnCookie expires the cookie immediately, same-site", () => {
  const cookie = clearOAuthReturnCookie();
  assert.match(cookie, new RegExp(`^${OAUTH_RETURN_COOKIE}=;`));
  assert.match(cookie, /Path=\//);
  assert.match(cookie, /Max-Age=0/);
  assert.match(cookie, /SameSite=Lax/);
  assert.match(cookie, /Secure/);
});

test("clearOAuthReturnCookie omits Secure on non-https (local dev)", () => {
  const cookie = clearOAuthReturnCookie({ secure: false });
  assert.doesNotMatch(cookie, /Secure/);
});

test("an explicit query next beats a stale OAuth cookie (email-link callback wins over leftover OAuth state)", () => {
  assert.equal(
    resolveCallbackNext({ queryNext: "/Market?tab=sets", cookieNext: "/my-portfolio?tab=sealed" }),
    "/Market?tab=sets",
  );
});

test("the OAuth cookie is used only when there is no query next at all (a genuine OAuth round trip)", () => {
  assert.equal(resolveCallbackNext({ queryNext: undefined, cookieNext: "/my-portfolio?tab=sealed" }), "/my-portfolio?tab=sealed");
  assert.equal(resolveCallbackNext({ queryNext: null, cookieNext: "/my-portfolio" }), "/my-portfolio");
  assert.equal(resolveCallbackNext({ queryNext: "", cookieNext: "/my-portfolio" }), "/my-portfolio");
});

test("a malformed query next still takes precedence over a valid cookie, per the intended precedence", () => {
  // The query param being present (even if unsafe/malformed) signals an
  // email-link callback; it must not silently fall through to a leftover
  // OAuth cookie from an unrelated browser tab or earlier attempt.
  assert.equal(resolveCallbackNext({ queryNext: "https://evil.example", cookieNext: "/my-portfolio" }), "/");
  assert.equal(resolveCallbackNext({ queryNext: "//evil.example", cookieNext: "/Market" }), "/");
});

test("falls back safely when both are missing or malformed", () => {
  assert.equal(resolveCallbackNext({}), "/");
  assert.equal(resolveCallbackNext({ queryNext: "https://evil.example", cookieNext: "" }), "/");
  assert.equal(resolveCallbackNext({ queryNext: null, cookieNext: "//evil.example" }), "/");
});
