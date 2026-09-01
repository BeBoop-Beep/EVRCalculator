import assert from "node:assert/strict";
import test from "node:test";
import { OAUTH_RETURN_COOKIE, OAUTH_RETURN_COOKIE_MAX_AGE, resolveCallbackNext, serializeOAuthReturnCookie } from "./oauthState.mjs";

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

test("resolveCallbackNext prefers the cookie (this browser's own OAuth attempt) over the query", () => {
  assert.equal(
    resolveCallbackNext({ queryNext: "/somewhere-else", cookieNext: "/my-portfolio?tab=sealed" }),
    "/my-portfolio?tab=sealed",
  );
});

test("resolveCallbackNext falls back to the query next when there is no cookie (email links)", () => {
  assert.equal(resolveCallbackNext({ queryNext: "/Market", cookieNext: undefined }), "/Market");
});

test("resolveCallbackNext falls back safely when both are missing or malformed", () => {
  assert.equal(resolveCallbackNext({}), "/");
  assert.equal(resolveCallbackNext({ queryNext: "https://evil.example", cookieNext: "" }), "/");
  assert.equal(resolveCallbackNext({ queryNext: null, cookieNext: "//evil.example" }), "/");
});
