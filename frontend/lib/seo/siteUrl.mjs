/**
 * The ONE canonical public origin for inDex.
 *
 * WHY THIS IS NOT `NEXT_PUBLIC_BASE_URL`
 * --------------------------------------
 * `getFrontendBaseUrl()` (lib/runtimeUrls.js) answers "where is this running",
 * which is `http://localhost:3000` in development and could be a preview host
 * in a branch deploy. A canonical URL, an `og:url` and a sitemap entry answer a
 * different question — "what is the ONE public address of this page" — and must
 * never advertise localhost or a preview host to a crawler. Those two questions
 * had one answer before this module existed, which is why the only production
 * domain in the frontend was a literal pasted into `app/layout.js`.
 *
 * `NEXT_PUBLIC_SITE_URL` exists as the override for the (uncommon) case where a
 * deployment genuinely publishes under a different public origin. When it is
 * absent — which is the normal case, including local production builds — the
 * production origin below is used, so a canonical tag is correct even when the
 * server answering the request is not the production one.
 *
 * `https://www.inthedex.io` is the host the site's existing public metadata
 * already claimed (`openGraph.url` in `app/layout.js`) and one of the two
 * origins the backend allows (`ALLOWED_ORIGINS` in backend/.env.example). The
 * apex `https://inthedex.io` appears in `.env.example` as the *runtime* base
 * URL; if the apex is the address that actually serves traffic, set
 * `NEXT_PUBLIC_SITE_URL=https://inthedex.io` rather than editing this constant,
 * and make sure the other origin permanently redirects to it.
 */
export const PRODUCTION_SITE_ORIGIN = "https://www.inthedex.io";

function normalizeOrigin(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null;
    }
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return null;
  }
}

/** The origin every canonical URL, `og:url` and sitemap entry is built from. */
export function getCanonicalSiteOrigin() {
  return normalizeOrigin(process.env.NEXT_PUBLIC_SITE_URL) || PRODUCTION_SITE_ORIGIN;
}

/**
 * Absolute canonical URL for an internal path.
 *
 * Query strings and hashes are deliberately dropped: the canonical identity of
 * every page in this app is its path. Tab/section/window query variants are
 * presentation state, and pointing them at the bare path is the whole point of
 * the canonical policy (see the set-detail policy in
 * `app/TCGs/Pokemon/Sets/[setSlug]/page.js`).
 */
export function canonicalUrl(pathname = "/") {
  const origin = getCanonicalSiteOrigin();
  const rawPath = String(pathname || "/").trim();
  const pathOnly = rawPath.split("?")[0].split("#")[0];
  if (!pathOnly || pathOnly === "/") {
    return `${origin}/`;
  }
  const withLeadingSlash = pathOnly.startsWith("/") ? pathOnly : `/${pathOnly}`;
  // No trailing slash on sub-paths — Next serves and links to these paths
  // without one, so a trailing-slash canonical would name a URL the app never
  // produces.
  return `${origin}${withLeadingSlash.replace(/\/+$/, "")}`;
}
