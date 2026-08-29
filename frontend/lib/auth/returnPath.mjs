export function sanitizeReturnPath(value, fallback = "/") {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return fallback;
  if (value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) return fallback;
  try {
    const decoded = decodeURIComponent(value);
    if (!decoded.startsWith("/") || decoded.startsWith("//") || decoded.includes("\\")) return fallback;
    const parsed = new URL(value, "https://www.inthedex.io");
    if (parsed.origin !== "https://www.inthedex.io") return fallback;
    for (const key of ["code", "token", "access_token", "refresh_token", "token_hash"]) parsed.searchParams.delete(key);
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
}

export function currentReturnPath() {
  if (typeof window === "undefined") return "/";
  return sanitizeReturnPath(`${window.location.pathname}${window.location.search}`);
}
