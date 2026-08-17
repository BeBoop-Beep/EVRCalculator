/**
 * Resolve the decorative booster-pack image for the hero backdrop.
 *
 * NO NEW DATA READ. This is a pure selector over the sealed-market payload the
 * homepage ALREADY fetches for the opening spotlight set
 * (`getSetSealedPayload` in landingSetMedia.js). It issues no request of its
 * own, so adding the backdrop costs the page zero additional round trips.
 *
 * LADDER, in the order the brief sets out:
 *   1. a booster-pack image belonging to the current dynamic spotlight set
 *   2. any other sealed-product image from that SAME set
 *   3. the documented static fallback asset (see HERO_BOOSTER_PACK_FALLBACK)
 *   4. null — the hero renders exactly as it does today, with no backdrop
 *
 * Steps 1 and 2 are live: the moment `sealed_products.image_small_url` /
 * `image_large_url` are populated and surfaced by the sealed contract, the
 * backdrop starts rendering the real product for whichever set is currently
 * spotlighted, and it changes with the spotlight. As of this writing those
 * columns are empty for all 1,698 rows and the published sealed payload carries
 * names, families and prices but no artwork, so the ladder falls through.
 *
 * STATIC FALLBACK. The brief permits an existing Pokemon 151 booster-pack asset
 * as a visual fallback, but explicitly forbids generating one or downloading
 * one. No such asset exists in this repository (`frontend/public/images`
 * contains brand marks and Explore illustrations only), so the fallback slot is
 * intentionally empty and step 4 applies. Dropping a real pack render at the
 * path below is the only change needed to activate it — nothing else has to
 * move.
 */

/**
 * Path to a locally stored booster-pack render, relative to `frontend/public`.
 * `null` while no such asset exists in the repository. Set this to e.g.
 * "/images/landing/booster-pack-151.webp" once one is added.
 */
export const HERO_BOOSTER_PACK_FALLBACK = null;

/** Most pack-like first: the backdrop should read as a booster pack. */
const PACK_FAMILY_PRIORITY = [
  "loose_booster_pack",
  "sleeved_booster_pack",
  "booster_bundle",
  "booster_box",
  "elite_trainer_box",
  "pokemon_center_elite_trainer_box",
];

function trimmed(value) {
  const text = typeof value === "string" ? value.trim() : "";
  return text || null;
}

/**
 * A usable image is a non-empty absolute http(s) URL or a root-relative path.
 * Anything else (a bare filename, a data URI, a placeholder token) is treated
 * as absent rather than rendered and left to fail in the browser.
 */
function usableSrc(value) {
  const src = trimmed(value);
  if (!src) return null;
  if (src.startsWith("/")) return src;
  return /^https?:\/\//i.test(src) ? src : null;
}

/** The sealed contract is served in both camelCase and snake_case shapes. */
function readProductImage(product) {
  return (
    usableSrc(product?.imageLargeUrl) ||
    usableSrc(product?.image_large_url) ||
    usableSrc(product?.imageSmallUrl) ||
    usableSrc(product?.image_small_url) ||
    usableSrc(product?.imageUrl) ||
    usableSrc(product?.image_url) ||
    null
  );
}

function readFamily(product) {
  return String(product?.productFamily || product?.product_family || product?.product_type || "")
    .trim()
    .toLowerCase();
}

/**
 * @param {object|null} sealedPayload the already-fetched /market/sealed payload
 * @param {{ setName?: string|null }} [options]
 * @returns {{ src: string, source: "booster_pack"|"sealed_product"|"fallback", family: string|null }|null}
 */
export function selectHeroBoosterPackImage(sealedPayload, { setName = null } = {}) {
  const products = Array.isArray(sealedPayload?.products) ? sealedPayload.products : [];

  const withImages = products
    .map((product) => ({ family: readFamily(product), src: readProductImage(product) }))
    .filter((entry) => entry.src);

  // 1 + 2 — the same set's own product art, most pack-like family first. Any
  // family not in the priority list still qualifies under step 2; it simply
  // sorts last.
  let best = null;
  let bestRank = Number.POSITIVE_INFINITY;
  for (const entry of withImages) {
    const rank = PACK_FAMILY_PRIORITY.indexOf(entry.family);
    const effective = rank === -1 ? PACK_FAMILY_PRIORITY.length : rank;
    if (effective < bestRank) {
      best = entry;
      bestRank = effective;
    }
  }

  if (best) {
    return {
      src: best.src,
      source: bestRank === 0 ? "booster_pack" : "sealed_product",
      family: best.family || null,
      setName: trimmed(setName),
    };
  }

  // 3 — documented static fallback, only if one is actually present.
  const fallback = usableSrc(HERO_BOOSTER_PACK_FALLBACK);
  if (fallback) {
    return { src: fallback, source: "fallback", family: "booster_pack", setName: null };
  }

  // 4 — no valid imagery: the hero keeps its current composition untouched.
  return null;
}
