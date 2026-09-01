export const CANONICAL_APP_ORIGIN = "https://inthedex.io";

export function normalizeAuthOrigin(value, fallback = CANONICAL_APP_ORIGIN) {
  if (typeof value !== "string" || !value.trim()) return fallback;
  try {
    const parsed = new URL(value);
    if (!["http:", "https:"].includes(parsed.protocol)) return fallback;
    const hostname = parsed.hostname.toLowerCase();
    if (hostname === "inthedex.io" || hostname === "www.inthedex.io") return CANONICAL_APP_ORIGIN;
    return parsed.origin;
  } catch {
    return fallback;
  }
}

export function sanitizeReturnPath(value, fallback = "/") {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return fallback;
  if (value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) return fallback;
  try {
    const decoded = decodeURIComponent(value);
    if (!decoded.startsWith("/") || decoded.startsWith("//") || decoded.includes("\\")) return fallback;
    const parsed = new URL(value, CANONICAL_APP_ORIGIN);
    if (parsed.origin !== CANONICAL_APP_ORIGIN) return fallback;
    for (const key of ["code", "token", "access_token", "refresh_token", "token_hash"]) parsed.searchParams.delete(key);
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
}

export function buildAuthCallbackUrl(origin, next = "/") {
  const callback = new URL("/auth/callback", normalizeAuthOrigin(origin));
  callback.searchParams.set("next", sanitizeReturnPath(next));
  return callback.toString();
}

export function currentReturnPath() {
  if (typeof window === "undefined") return "/";
  return sanitizeReturnPath(`${window.location.pathname}${window.location.search}`);
}
