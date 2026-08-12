import StickyNav from "@/components/StickyNav";
import GlobalMobileBottomNav from "@/components/GlobalMobileBottomNav";
import { CartContextProvider } from "@/components/Cart/CartContext";
import { AuthProvider } from "@/components/AuthContext";
import RouteTransitionFeedback from "@/components/navigation/RouteTransitionFeedback";
import { getAuthenticatedUserFromCookiesWithTimeout } from "@/lib/authServer";
import { getCanonicalSiteOrigin } from "@/lib/seo/siteUrl.mjs";
import { SITE_NAME } from "@/lib/seo/routeMetadata.mjs";
import { Manrope } from "next/font/google";
import { Suspense } from "react";
import "./styles/globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

/**
 * SITE-WIDE FALLBACK METADATA ONLY.
 *
 * Every field here is INHERITED by any route that does not declare its own, so
 * this object must never claim to be a specific page.
 *
 * `openGraph.url` used to be hard-coded to `https://www.inthedex.io/` here,
 * which meant Rankings, Market, Research and every set page told crawlers and
 * social scrapers that they *were* the homepage. It is removed rather than
 * corrected: a route's `og:url` is now set by `buildRouteMetadata` alongside
 * that route's canonical, and a route with no `og:url` is better than a route
 * with a wrong one.
 *
 * `alternates.canonical` is deliberately NOT declared here for the same reason
 * — a canonical inherited by every page is exactly the duplicate-signal problem
 * canonicals exist to solve. `metadataBase` below is the one URL-shaped field
 * that is safe to share, because Next only uses it to resolve relative
 * metadata URLs.
 */
export const metadata = {
  metadataBase: new URL(getCanonicalSiteOrigin()),
  title: "inDex — Collectible Intelligence",
  description: "Your collectible intelligence platform for pack simulations, EV insights, market signals, and collection analytics.",
  openGraph: {
    title: "inDex — Collectible Intelligence",
    description: "Your collectible intelligence platform for pack simulations, EV insights, market signals, and collection analytics.",
    siteName: SITE_NAME,
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "inDex — Collectible Intelligence",
    description: "Your collectible intelligence platform for pack simulations, EV insights, market signals, and collection analytics.",
  },
  manifest: "/manifest.json",
  icons: {
    icon: [{ url: "/inDex.png", type: "image/png" }],
    shortcut: ["/inDex.png"],
    apple: [{ url: "/inDex.png", type: "image/png" }]
  },
};

export default async function RootLayout({ children }) {
  const authResult = await getAuthenticatedUserFromCookiesWithTimeout(150);
  const initialUser = authResult?.user || null;

  return (
    <html lang="en">
      <body className={`${manrope.variable} flex flex-col min-h-screen`}>
        {/* Header */}
        <CartContextProvider>
          <AuthProvider initialUser={initialUser}>
            <StickyNav />
            {/*
              RouteTransitionFeedback calls useSearchParams(), which requires a
              Suspense boundary — without one it bails the whole route out to
              client-side rendering. The boundary is deliberately wrapped around
              ONLY this indicator, not around <main>: it must never be the reason
              page content is withheld from the server-rendered HTML. The
              fallback is null because a transition indicator has nothing to show
              before it knows the current route.
            */}
            <Suspense fallback={null}>
              <RouteTransitionFeedback />
            </Suspense>
            <main className="app-canvas flex-1 w-full pb-[calc(5.25rem+env(safe-area-inset-bottom))] lg:pb-0">{children}</main>
            <GlobalMobileBottomNav />
          </AuthProvider>
        </CartContextProvider>
      </body>
    </html>
  );
}
