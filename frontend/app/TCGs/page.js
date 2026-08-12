import ComingSoonPage from "@/components/coming-soon/ComingSoonPage";
import { NOINDEX_FOLLOW_ROBOTS } from "@/lib/seo/routeMetadata.mjs";

// A "coming soon" placeholder with no content of its own. Kept reachable (it is
// a real path in the URL hierarchy and is linked internally) but excluded from
// search results, with `follow` so its outbound links still carry.
export const metadata = { robots: NOINDEX_FOLLOW_ROBOTS };

export default function TCGsPage() {
  return (
    <ComingSoonPage
      title="TCGs are coming soon"
      body="We&rsquo;re building dedicated TCG pages for browsing sets, cards, market data, and collecting tools. Stay tuned - and join the waitlist from the homepage for updates."
      variant="feature"
      ctaLabel="Back to home"
      ctaHref="/"
    />
  );
}
