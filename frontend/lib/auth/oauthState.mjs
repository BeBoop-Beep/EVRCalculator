import { sanitizeReturnPath } from "./returnPath.mjs";

// Carries the post-auth destination across the OAuth round trip WITHOUT
// putting it in the Supabase `redirectTo` query string (see buildAuthCallbackUrl
// in returnPath.mjs — that URL must stay stable and allow-list friendly).
// Short-lived, same-site, path-only, never holds a token or credential.
export const OAUTH_RETURN_COOKIE = "pkce_return_path";
export const OAUTH_RETURN_COOKIE_MAX_AGE = 300; // 5 minutes: long enough for a Google round trip, short enough to not linger.

// Not httpOnly: it must be written from client JS immediately before
// `signInWithOAuth()` redirects the browser away. The value is only ever an
// internal path (already sanitized before being stored), so client
// readability carries no meaningful risk.
export function serializeOAuthReturnCookie(nextPath, { secure = true } = {}) {
  const safe = sanitizeReturnPath(nextPath);
  const attrs = [
    `${OAUTH_RETURN_COOKIE}=${encodeURIComponent(safe)}`,
    "Path=/",
    `Max-Age=${OAUTH_RETURN_COOKIE_MAX_AGE}`,
    "SameSite=Lax",
  ];
  if (secure) attrs.push("Secure");
  return attrs.join("; ");
}

// Expires the transient OAuth-return cookie immediately. Used both by the
// callback route (server-side, on every response) and by the client when
// signInWithOAuth() fails before the browser ever leaves the page — the
// cookie was already written and would otherwise linger for up to
// OAUTH_RETURN_COOKIE_MAX_AGE with nothing left to consume it.
export function clearOAuthReturnCookie({ secure = true } = {}) {
  const attrs = [`${OAUTH_RETURN_COOKIE}=`, "Path=/", "Max-Age=0", "SameSite=Lax"];
  if (secure) attrs.push("Secure");
  return attrs.join("; ");
}

// An explicit `next` query param always wins, even a malformed one: it means
// this is a server-generated email link (signup confirmation, password
// recovery) that intentionally carries its own destination and was never
// preceded by a request that could set the OAuth cookie. The cookie is only
// consulted when there is no query `next` at all — i.e. a genuine OAuth
// round trip, where the query-free callback URL never carries one. This
// ordering also prevents a stale cookie left over from an earlier OAuth
// attempt from hijacking an email-link callback's destination. Both sources
// pass through the same sanitizer, so a missing or tampered value falls back
// to "/" rather than ever becoming an open redirect.
export function resolveCallbackNext({ queryNext, cookieNext } = {}) {
  if (typeof queryNext === "string" && queryNext) {
    return sanitizeReturnPath(queryNext);
  }
  if (typeof cookieNext === "string" && cookieNext) {
    return sanitizeReturnPath(cookieNext);
  }
  return sanitizeReturnPath(undefined);
}
