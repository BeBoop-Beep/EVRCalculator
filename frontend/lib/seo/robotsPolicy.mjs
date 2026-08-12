import { canonicalUrl, getCanonicalSiteOrigin } from "./siteUrl.mjs";

/**
 * The crawl policy, as data.
 *
 * It lives here rather than inside app/robots.js so it can be asserted directly
 * by a test — app/* modules import through the "@/" bundler alias, which the
 * repo's `tsx --test` runner cannot resolve (same reason ripTierPresentation.mjs
 * is dependency-free).
 *
 * DELIBERATELY SMALL. Everything public is allowed; the disallow list names only
 * account-scoped, transactional and internal-API families — pages that are
 * meaningless to a signed-out crawler. It is NOT authentication (middleware.js
 * still gates the protected routes) and it is NOT how thin public pages are
 * handled: those carry `noindex, follow` metadata, which keeps their outbound
 * links crawlable. Disallowing them here would do the opposite — the crawler
 * would never fetch the page, so it would never see the `noindex` either.
 *
 * `/_next/` and `/images/` are intentionally absent: blocking the CSS, JS and
 * images a page needs stops search engines rendering it correctly.
 */
export const DISALLOWED_PATH_PREFIXES = Object.freeze([
  "/api/",
  "/dashboard",
  "/account-settings",
  "/profile",
  // BOTH spellings. /my-collection is the internal route; /my-portfolio is the
  // public URL it was renamed to (next.config.mjs 308s the old path to the new
  // one and rewrites it back internally). Listing only /my-collection left the
  // rule guarding a URL that redirects away while the address the app actually
  // links to stayed crawlable.
  "/my-collection",
  "/my-portfolio",
  "/cart",
  "/checkout",
  "/login",
  "/signup",
  "/waitlist/verify",
]);

export function buildRobotsPolicy() {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [...DISALLOWED_PATH_PREFIXES],
      },
    ],
    sitemap: canonicalUrl("/sitemap.xml"),
    host: getCanonicalSiteOrigin(),
  };
}
