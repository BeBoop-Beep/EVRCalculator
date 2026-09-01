// A neutral, non-production base used only to let the URL parser validate and
// decompose a same-origin relative path. It is deliberately NOT a real host —
// sanitizeReturnPath() never needs to know whether the app's public canonical
// domain is the apex or `www` (see lib/seo/siteUrl.mjs for that policy). A
// relative path that survives the leading-slash/backslash/control-character
// checks below is safe on whatever origin it is ultimately joined to.
const RETURN_PATH_BASE = "http://return-path.invalid";

// Built from char codes (rather than a literal control-character range in the
// regex) so no raw control bytes live in this source file.
const CONTROL_CHAR_RE = new RegExp(
  `[${String.fromCharCode(0)}-${String.fromCharCode(31)}${String.fromCharCode(127)}]`,
);

export function sanitizeReturnPath(value, fallback = "/") {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return fallback;
  if (value.includes(String.fromCharCode(92)) || CONTROL_CHAR_RE.test(value)) return fallback;
  try {
    const decoded = decodeURIComponent(value);
    if (!decoded.startsWith("/") || decoded.startsWith("//") || decoded.includes("\\") || CONTROL_CHAR_RE.test(decoded)) return fallback;
    const parsed = new URL(value, RETURN_PATH_BASE);
    if (parsed.origin !== RETURN_PATH_BASE) return fallback;
    for (const key of ["code", "token", "access_token", "refresh_token", "token_hash"]) parsed.searchParams.delete(key);
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
}

// Validates that `value` is a well-formed http(s) origin. This has nothing to
// do with the SEO canonical-domain policy — it only checks that a string is
// safe to build a URL from, for whichever origin actually initiated the
// request (the browser's own origin client-side, or a server-trusted origin
// server-side — see runtimeUrls.js for that decision).
export function normalizeAuthOrigin(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const parsed = new URL(value);
    if (!["http:", "https:"].includes(parsed.protocol)) return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

// The OAuth (Google/Apple) redirect target. Deliberately stable and query-free
// so it matches Supabase's redirect allow-list exactly regardless of where the
// user is headed after sign-in — see lib/auth/oauthState.mjs for how the
// post-auth destination travels instead (a short-lived same-site cookie, not
// a query parameter).
export function buildAuthCallbackUrl(origin) {
  const normalized = normalizeAuthOrigin(origin);
  if (!normalized) throw new Error("A valid origin is required to build the auth callback URL.");
  return new URL("/auth/callback", normalized).toString();
}

// Server-generated email links (signup confirmation, password recovery) are
// opened directly from an email client, possibly on a different device, so
// there is no prior request on which to set a same-site cookie. Those flows
// keep the return path in the query string; the callback route consumes the
// cookie mechanism first and only falls back to this query param.
export function buildAuthCallbackUrlWithNext(origin, next = "/") {
  const callback = new URL(buildAuthCallbackUrl(origin));
  callback.searchParams.set("next", sanitizeReturnPath(next));
  return callback.toString();
}

export function currentReturnPath() {
  if (typeof window === "undefined") return "/";
  return sanitizeReturnPath(`${window.location.pathname}${window.location.search}`);
}
