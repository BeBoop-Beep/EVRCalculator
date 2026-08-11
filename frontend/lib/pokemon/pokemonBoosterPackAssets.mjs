/** Explicit registry of authentic local booster-pack photography. */
export const BOOSTER_PACK_ASSETS = Object.freeze({
  ascendedHeroes: { src: "/images/pokemon/booster-packs/ascendedHeroes.webp", width: 4000, height: 3000 },
  blackBolt: { src: "/images/pokemon/booster-packs/blackBolt.webp", width: 4000, height: 3000 },
  chaosRising: { src: "/images/pokemon/booster-packs/chaosRising.webp", width: 4000, height: 3000 },
  destinedRivals: { src: "/images/pokemon/booster-packs/destinedRivals.webp", width: 4000, height: 3000 },
  journeyTogether: { src: "/images/pokemon/booster-packs/journeyTogether.webp", width: 4000, height: 3000 },
  megaEvolution: { src: "/images/pokemon/booster-packs/megaEvolution.webp", width: 4000, height: 3000 },
  paldeaEvolved: { src: "/images/pokemon/booster-packs/paldeaEvolved.webp", width: 4000, height: 3000 },
  paldeanFates: { src: "/images/pokemon/booster-packs/paldeanFates.webp", width: 4000, height: 3000 },
  paradoxRift: { src: "/images/pokemon/booster-packs/paradoxRift.webp", width: 4000, height: 3000 },
  perfectOrder: { src: "/images/pokemon/booster-packs/perfectOrder.webp", width: 4000, height: 3000 },
  // Supplied filename is intentionally preserved; the registry owns the canonical mapping.
  phantasmalFlames: { src: "/images/pokemon/booster-packs/phatasmalFlames.webp", width: 4000, height: 3000 },
  pitchBlack: { src: "/images/pokemon/booster-packs/pitchBlack.webp", width: 4000, height: 3000 },
  prismaticEvolutions: { src: "/images/pokemon/booster-packs/prismaticEvolutions.webp", width: 4000, height: 3000 },
  scarletAndViolet151: { src: "/images/pokemon/booster-packs/scarletAndViolet151.webp", width: 4000, height: 3000 },
  scarletAndVioletBase: { src: "/images/pokemon/booster-packs/scarletAndVioletBaseSet.webp", width: 4000, height: 3000 },
  stellarCrown: { src: "/images/pokemon/booster-packs/stellarCrown.webp", width: 4000, height: 3000 },
  surgingSparks: { src: "/images/pokemon/booster-packs/surigngSparks.webp", width: 4000, height: 3000 },
  twilightMasquerade: { src: "/images/pokemon/booster-packs/twilightMasquerade.webp", width: 4000, height: 3000 },
  whiteFlare: { src: "/images/pokemon/booster-packs/whiteFlare.webp", width: 3000, height: 4000 },
});

export function resolvePokemonBoosterPackAsset(canonicalSetKey) {
  const key = String(canonicalSetKey || "").trim();
  return Object.prototype.hasOwnProperty.call(BOOSTER_PACK_ASSETS, key)
    ? BOOSTER_PACK_ASSETS[key]
    : null;
}
