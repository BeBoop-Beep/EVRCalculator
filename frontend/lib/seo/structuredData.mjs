import { canonicalUrl } from "./siteUrl.mjs";
import { SITE_NAME } from "./routeMetadata.mjs";

/**
 * The ONE site-level schema.org entity graph.
 *
 * WHY THIS EXISTS
 * ---------------
 * Every route already emits a correct title, description, canonical and
 * `og:url`, but none of that tells a search engine *what inDex is*. Metadata
 * describes a page; an entity describes the site. Without a `WebSite` /
 * `Organization` pair, "inDex" is a bare word a crawler has to disambiguate
 * from every other product, index and dex-adjacent name on the web, and the
 * only machine-readable brand string on the site is a logo's alt text.
 *
 * WHY IT IS ONE `@graph` AND NOT TWO SCRIPTS
 * Two unrelated JSON-LD fragments are two candidate site entities. One graph
 * with stable `@id`s and a real `publisher` edge is a single coherent claim:
 * this site is published by this organization, and they share a name.
 *
 * WHY IT IS EMITTED ON THE HOMEPAGE ONLY
 * The site entity's `url` is the site root, so repeating it on every route
 * would restate the same claim on pages that are not that URL — the same
 * reason `app/layout.js` refuses to declare a shared canonical or `og:url`.
 * The homepage is the document the entity actually describes.
 *
 * EVERY FIELD BELOW IS FACTUAL AND ALREADY PUBLIC.
 * The names are the brand as the header, footer and `manifest.json` already
 * spell it; the logo is the icon `manifest.json` already ships. There is
 * deliberately no `sameAs`, no address, no founder and no legal entity: the
 * repository contains no social profile or corporate record to source them
 * from, and structured data that cannot be corroborated is a liability rather
 * than a signal. Add `sameAs` only when a real, owned profile URL exists.
 */

const WEBSITE_NODE_ID = "#website";
const ORGANIZATION_NODE_ID = "#organization";
const LOGO_NODE_ID = "#logo";

/**
 * Legitimate spellings of the same brand — the contextual forms ("inDex
 * Pokémon", "inDex Pokémon TCG") and the unspaced form a person types when
 * they mean this site. Not keywords: each one is a name this entity is
 * genuinely called.
 *
 * `inthedex.io` is deliberately NOT here. A fully-qualified domain is an
 * address, not a name, and both nodes below already state that address in
 * their `url` — repeating it as an `alternateName` adds no signal and blurs
 * the line between what the entity is called and where it lives.
 */
export const SITE_ALTERNATE_NAMES = Object.freeze([
  "inDex Pokémon",
  "inDex Pokémon TCG",
  "inthedex",
]);

/**
 * One sentence that states the entity's category in plain language. It says
 * only what the homepage, /Rankings and /Articles/how-rip-score-works already
 * say on the page, and names no score, weight or formula.
 */
export const SITE_ENTITY_DESCRIPTION =
  "inDex is a Pokémon TCG opening-intelligence platform: simulated pack openings, expected value, and Overall RIP rankings for Pokémon sets.";

/** `/icon-512.png` — the 512x512 PNG `public/manifest.json` already ships. */
const LOGO_PATH = "/icon-512.png";
const LOGO_PIXELS = 512;

export function buildSiteStructuredData() {
  const siteUrl = canonicalUrl("/");
  const websiteId = `${siteUrl}${WEBSITE_NODE_ID}`;
  const organizationId = `${siteUrl}${ORGANIZATION_NODE_ID}`;
  const logoId = `${siteUrl}${LOGO_NODE_ID}`;
  const alternateName = [...SITE_ALTERNATE_NAMES];

  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": websiteId,
        url: siteUrl,
        name: SITE_NAME,
        alternateName,
        description: SITE_ENTITY_DESCRIPTION,
        inLanguage: "en-US",
        publisher: { "@id": organizationId },
      },
      {
        "@type": "Organization",
        "@id": organizationId,
        url: siteUrl,
        name: SITE_NAME,
        alternateName,
        description: SITE_ENTITY_DESCRIPTION,
        logo: {
          "@type": "ImageObject",
          "@id": logoId,
          url: canonicalUrl(LOGO_PATH),
          contentUrl: canonicalUrl(LOGO_PATH),
          width: LOGO_PIXELS,
          height: LOGO_PIXELS,
          caption: SITE_NAME,
        },
        image: { "@id": logoId },
      },
    ],
  };
}
