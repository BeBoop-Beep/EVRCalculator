const EXPLORE_BACKGROUNDS = Object.freeze({
  pokemon: "/images/explore/pokemon-wordmark.svg",
});

export function getExploreBackground(tcg) {
  const key = String(tcg || "").trim().toLowerCase();
  return EXPLORE_BACKGROUNDS[key] || null;
}
