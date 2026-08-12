import { canonicalUrl } from "./siteUrl.mjs";

/**
 * One builder for every public route's metadata, so a route cannot ship a
 * canonical URL without also correcting the `og:url` that used to be inherited
 * from the root layout (which claimed the homepage for every page on the site).
 *
 * Everything here is descriptive copy and URLs. No score, weight, formula or
 * ranking input is computed, restated or disclosed by this module — dynamic
 * routes that want a real set name read it from the canonical server payload
 * they already fetched and pass it in.
 */

export const SITE_NAME = "inDex";

/**
 * `noindex, follow` — the policy for thin/placeholder pages that must stay
 * reachable (external links, in-app navigation) without competing for a search
 * result. `follow` keeps their outbound links crawlable.
 */
export const NOINDEX_FOLLOW_ROBOTS = {
  index: false,
  follow: true,
  googleBot: { index: false, follow: true },
};

export function buildRouteMetadata({
  path,
  title,
  description,
  ogTitle = null,
  ogDescription = null,
  robots = null,
}) {
  const url = canonicalUrl(path);
  const socialTitle = ogTitle || title;
  const socialDescription = ogDescription || description;

  const metadata = {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      title: socialTitle,
      description: socialDescription,
      url,
      siteName: SITE_NAME,
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title: socialTitle,
      description: socialDescription,
    },
  };

  if (robots) {
    metadata.robots = robots;
  }

  return metadata;
}
