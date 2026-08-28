import { canonicalUrl } from "./siteUrl.mjs";

/**
 * The sitemap as a PURE projection of the canonical targets payload the ranking
 * surfaces already fetch. app/sitemap.js does the fetching; everything that
 * decides which URLs are index-worthy lives here so it can be tested with
 * fixtures instead of the network.
 *
 * WHAT IS IN IT
 *   * the canonical hub URLs (including the one published article, which is a
 *     real indexable destination rather than a redirect), and
 *   * the bare canonical URL of every set that is BOTH a real ranking target
 *     and public-analytics eligible.
 *
 * The set filter is the same one the public ranking surfaces use
 * (isPublicAnalyticsEligiblePokemonSet), so a set appears only when its page
 * actually has the canonical scores that make it worth indexing. The far larger
 * catalog of sets that merely have a working route is NOT enumerated: a sitemap
 * asserts "this is a complete, canonical page", not "this route resolves".
 *
 * WHAT IS DELIBERATELY EXCLUDED
 *   * /Explore, /Explore/top-10 and /Research — permanent redirects. A sitemap
 *     lists the destination (already present), never the redirecting URL.
 *   * /Explore/rip-statistics, /TCGs, /TCGs/Pokemon, /TCGs/Pokemon/Analytics —
 *     noindex placeholders/legacy entry points.
 *   * every query variant (?tab=, ?section=, ?window=, ?card_sort=, ?movement=,
 *     sort/filter state) — all of them canonicalize to a URL already listed.
 *   * account, cart, checkout and auth routes.
 *   * card and sealed-product detail URLs. Those routes exist, but existence is
 *     not the bar — they are not yet complete public pages with a stable public
 *     identity, so listing them would be a promise the sitemap cannot keep.
 *
 * LASTMODIFIED
 * `run_at` is the timestamp of the ranking calculation run that produced the
 * set's published numbers — a real publication timestamp for that page's
 * content. It is passed through when present and OMITTED when absent. Nothing
 * here substitutes `new Date()`: stamping every URL with the moment the sitemap
 * was requested is fabricated freshness, which is worse than no signal. The hub
 * URLs carry no lastModified for exactly that reason — there is no publication
 * timestamp for them to reuse.
 */

export const SITEMAP_HUB_PATHS = Object.freeze([
  "/",
  "/Rankings",
  "/Market",
  "/Articles",
  "/Articles/how-rip-score-works",
  "/Articles/how-we-simulated-one-million-pokemon-pack-openings",
  "/Articles/how-we-validated-our-pokemon-pack-simulation-using-expected-value",
  "/Articles/why-expected-value-alone-isnt-enough",
  "/Articles/how-financial-rip-works",
  "/Articles/how-collector-appeal-works",
  "/Articles/how-representative-is-pokemon-pack-expected-value",
  "/Articles/how-chase-efficiency-works",
  "/TCGs/Pokemon/Sets",
]);

function toLastModified(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? new Date(parsed) : null;
}

/**
 * `isEligibleSet` and `toSlug` are INJECTED rather than imported so this module
 * stays a plain `.mjs` with no bundler-alias or CommonJS dependency — the same
 * constraint that keeps ripTierPresentation.mjs dependency-free, because the
 * repo's `tsx --test` runner cannot import the `.js` modules that own them.
 *
 * They are not pluggable policy: app/sitemap.js wires the ONE canonical public
 * eligibility gate (isPublicAnalyticsEligiblePokemonSet) and the ONE canonical
 * slug function (toSetSlug), and the contract test wires exactly those same two
 * functions, so what is tested here is the real filter and the real slugs.
 */
export function buildSitemapEntries(targets, { isEligibleSet, toSlug } = {}) {
  if (typeof isEligibleSet !== "function" || typeof toSlug !== "function") {
    throw new TypeError(
      "buildSitemapEntries requires the canonical isEligibleSet and toSlug helpers — a sitemap must not invent its own eligibility or slug rules."
    );
  }

  const bySlug = new Map();

  (Array.isArray(targets) ? targets : [])
    .filter((target) => String(target?.target_type || "").toLowerCase() === "set")
    .filter((target) => isEligibleSet(target))
    .forEach((target) => {
      // A set with no name is dropped rather than slugged from its opaque
      // target id. `toSlug` would happily fall back to the id and emit
      // /Sets/5e99f658-…, which is not the public URL shape anything on the
      // site links to — advertising it in a sitemap would be inventing a URL.
      const name = String(target?.name || "").trim();
      if (!name) {
        return;
      }
      const slug = toSlug(name);
      if (!slug || bySlug.has(slug)) {
        return;
      }
      bySlug.set(slug, toLastModified(target?.run_at));
    });

  const setEntries = Array.from(bySlug.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([slug, lastModified]) => {
      const entry = { url: canonicalUrl(`/TCGs/Pokemon/Sets/${encodeURIComponent(slug)}`) };
      if (lastModified) {
        entry.lastModified = lastModified;
      }
      return entry;
    });

  return [...SITEMAP_HUB_PATHS.map((path) => ({ url: canonicalUrl(path) })), ...setEntries];
}
