import { NextResponse } from "next/server";
import { isLegacySetDetailTabAlias } from "@/lib/explore/ripStatisticsRouting";

/**
 * Edge-compatible middleware. Two responsibilities, in this order:
 *
 *   1. Canonical URL normalization for public set-detail URLs.
 *   2. A fast auth gate on protected routes.
 *
 * Full JWT verification happens in /api/auth/me (Node.js runtime) — this
 * middleware only acts as a fast gate for obviously unauthenticated requests.
 */

const SET_DETAIL_PATH_PREFIX = "/TCGs/Pokemon/Sets/";

/**
 * Collapse the legacy spellings of the set page's DEFAULT view onto the bare
 * canonical set URL.
 *
 * `rip`, `analysis` and `analytics` all alias `overview`, and the bare set URL
 * already renders `overview` — so they are pure duplicates of the canonical
 * URL. The alias list is NOT restated here: `isLegacySetDetailTabAlias` reads
 * the same SET_DETAIL_TAB_ALIASES map the route and the client resolve tabs
 * through, so this redirect can never disagree with what the app considers an
 * alias.
 *
 * `overview` is deliberately not one of them. The set page client writes
 * `?tab=overview` on every RIP-tab click (see `updateSetDetailQueryParams` in
 * RipStatisticsPageClient), so redirecting it would put a server round-trip in
 * the middle of ordinary in-app tab navigation. It is consolidated by the
 * canonical tag instead.
 *
 * WHY HERE AND NOT IN THE ROUTE
 * The set route has a `loading.js`, so Next flushes the response shell before
 * the page component runs. A `permanentRedirect()` thrown from the page
 * therefore arrives after the 200 status line is already committed and degrades
 * to a client-side redirect — no 308 for a crawler to follow. Middleware runs
 * before anything is sent, so it can issue a real 308.
 *
 * WHY NOT IN next.config.mjs
 * A config redirect re-appends the request's query string to a path
 * destination, so stripping `tab` there would redirect the alias straight back
 * to itself. Middleware can delete exactly one parameter and keep the rest.
 */
function normalizeLegacySetDetailTab(req) {
  const { pathname, searchParams } = req.nextUrl;

  if (!pathname.startsWith(SET_DETAIL_PATH_PREFIX)) {
    return null;
  }

  if (!isLegacySetDetailTabAlias(searchParams.get("tab"))) {
    return null;
  }

  // Only `tab` is dropped. A `section` or `window` the visitor arrived with is
  // still meaningful on the default view and travels to the canonical URL.
  const url = req.nextUrl.clone();
  url.searchParams.delete("tab");
  return NextResponse.redirect(url, 308);
}

export function middleware(req) {
  const canonicalRedirect = normalizeLegacySetDetailTab(req);
  if (canonicalRedirect) {
    return canonicalRedirect;
  }

  const token = req.cookies.get("token")?.value;

  const protectedRoutes = [
    "/dashboard",
    "/profile",
    "/my-portfolio",
    "/my-collection",
    "/account-settings",
  ];

  const isProtectedRoute = protectedRoutes.some(
    (route) =>
      req.nextUrl.pathname === route ||
      req.nextUrl.pathname.startsWith(`${route}/`)
  );

  if (isProtectedRoute && !token) {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/profile/:path*",
    "/my-portfolio/:path*",
    "/my-collection/:path*",
    "/account-settings/:path*",
    // Public, unauthenticated: matched only so the legacy default-view tab
    // aliases above can be collapsed onto the canonical set URL. No auth check
    // applies to these paths — `protectedRoutes` does not contain them.
    "/TCGs/Pokemon/Sets/:setSlug*",
  ],
};
