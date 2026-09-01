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

// The cookie (this browser's own OAuth attempt) always wins over a `next`
// query param, which only exists for server-generated email links that never
// had a chance to set it. Both pass through the same sanitizer, so a missing
// or tampered cookie/query value falls back to "/" rather than ever becoming
// an open redirect.
export function resolveCallbackNext({ queryNext, cookieNext } = {}) {
  if (typeof cookieNext === "string" && cookieNext) {
    return sanitizeReturnPath(cookieNext);
  }
  return sanitizeReturnPath(queryNext);
}
