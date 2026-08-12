import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { toSetSlug } from "@/lib/explore/ripStatisticsRouting";
import { buildSitemapEntries } from "@/lib/seo/sitemapEntries.mjs";

// The targets loader fetches with `cache: "no-store"` (its own bounded process
// cache is the single freshness boundary — see ripStatisticsServer.js), so this
// route cannot be statically exported. Declaring that explicitly is the fix for
// the build-time "couldn't be rendered statically" error; the set list is
// live data and a build-time snapshot of it would go stale immediately.
export const dynamic = "force-dynamic";

/**
 * Framework-native sitemap route — Next App Router serves this at /sitemap.xml.
 *
 * This file only fetches and wires the CANONICAL helpers. Which URLs are
 * index-worthy, how they are ordered and whether a lastModified is honest all
 * live in lib/seo/sitemapEntries.mjs, where they are tested with fixtures.
 *
 * The eligibility gate and the slug function are the same ones the ranking
 * surfaces and the set routes use, so the sitemap cannot list a set the site
 * hides, or a URL shape the site does not link to. The targets payload is the
 * cached one the ranking surfaces already read, so serving the sitemap costs no
 * additional backend request inside the cache window, and a backend failure
 * degrades to the hub URLs rather than an empty or erroring sitemap.
 */
export default async function sitemap() {
  const payload = await getRipStatisticsTargets({ limit: 200 }).catch(() => null);
  return buildSitemapEntries(Array.isArray(payload?.targets) ? payload.targets : [], {
    isEligibleSet: isPublicAnalyticsEligiblePokemonSet,
    toSlug: toSetSlug,
  });
}
