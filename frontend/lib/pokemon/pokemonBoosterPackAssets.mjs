/** Explicit registry of authentic local booster-pack photography. */
export const BOOSTER_PACK_ASSETS = Object.freeze({
  ascendedHeroes: { src: "/images/pokemon/booster-packs/ascendedHeroes.webp", width: 3000, height: 4000 },
  blackBolt: { src: "/images/pokemon/booster-packs/blackBolt.webp", width: 3000, height: 4000 },
  chaosRising: { src: "/images/pokemon/booster-packs/chaosRising.webp", width: 3000, height: 4000 },
  destinedRivals: { src: "/images/pokemon/booster-packs/destinedRivals.webp", width: 3000, height: 4000 },
  journeyTogether: { src: "/images/pokemon/booster-packs/journeyTogether.webp", width: 3000, height: 4000 },
  megaEvolution: { src: "/images/pokemon/booster-packs/megaEvolution.webp", width: 3000, height: 4000 },
  paldeaEvolved: { src: "/images/pokemon/booster-packs/paldeaEvolved.webp", width: 3000, height: 4000 },
  paldeanFates: { src: "/images/pokemon/booster-packs/paldeanFates.webp", width: 3000, height: 4000 },
  paradoxRift: { src: "/images/pokemon/booster-packs/paradoxRift.webp", width: 3000, height: 4000 },
  perfectOrder: { src: "/images/pokemon/booster-packs/perfectOrder.webp", width: 3000, height: 4000 },
  // Supplied filename is intentionally preserved; the registry owns the canonical mapping.
  phantasmalFlames: { src: "/images/pokemon/booster-packs/phatasmalFlames.webp", width: 3000, height: 4000 },
  pitchBlack: { src: "/images/pokemon/booster-packs/pitchBlack.webp", width: 3000, height: 4000 },
  prismaticEvolutions: { src: "/images/pokemon/booster-packs/prismaticEvolutions.webp", width: 3000, height: 4000 },
  scarletAndViolet151: { src: "/images/pokemon/booster-packs/scarletAndViolet151.webp", width: 3000, height: 4000 },
  scarletAndVioletBase: { src: "/images/pokemon/booster-packs/scarletAndVioletBaseSet.webp", width: 3000, height: 4000 },
  stellarCrown: { src: "/images/pokemon/booster-packs/stellarCrown.webp", width: 3000, height: 4000 },
  surgingSparks: { src: "/images/pokemon/booster-packs/surigngSparks.webp", width: 3000, height: 4000 },
  twilightMasquerade: { src: "/images/pokemon/booster-packs/twilightMasquerade.webp", width: 3000, height: 4000 },
  whiteFlare: { src: "/images/pokemon/booster-packs/whiteFlare.webp", width: 3000, height: 4000 },
});

export function resolvePokemonBoosterPackAsset(canonicalSetKey) {
  const key = String(canonicalSetKey || "").trim();
  return Object.prototype.hasOwnProperty.call(BOOSTER_PACK_ASSETS, key)
    ? BOOSTER_PACK_ASSETS[key]
    : null;
}

/** DB artwork remains authoritative; curated local art fills only known loose-pack gaps. */
export function resolveLooseBoosterPackArtwork({ productImageUrl, setCanonicalKey } = {}) {
  const canonicalProductImage = typeof productImageUrl === "string" ? productImageUrl.trim() : "";
  if (canonicalProductImage) {
    return { src: canonicalProductImage, source: "product" };
  }
  const localAsset = resolvePokemonBoosterPackAsset(setCanonicalKey);
  return localAsset ? { ...localAsset, source: "local" } : null;
}
