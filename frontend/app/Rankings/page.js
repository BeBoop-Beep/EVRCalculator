import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";

/**
 * /Rankings is the CANONICAL address of the leaderboard. /Explore permanently
 * redirects here (see `redirects()` in next.config.mjs), so the shared page
 * implementation still lives in ../Explore/page.js but the canonical identity,
 * title and social metadata belong to this route and are declared here — not
 * re-exported from a path that no longer answers requests.
 */
export { default } from "../Explore/page";

export const metadata = buildRouteMetadata({
  path: "/Rankings",
  title: "Pokémon Rankings — Sets, Products, Cards, and Eras | inDex",
  // "RIP Score" is the current public name of the headline metric (see
  // /Articles/how-rip-score-works and the set page verdict card); the retired "RIP Score" label
  // must not come back through metadata.
  description:
    "Compare Pokémon sets, eras, products, and cards across RIP Score, opening economics, and other ranking systems.",
  ogTitle: "Pokémon Rankings",
  ogDescription:
    "See which Pokémon sets rank strongest to open right now, ranked by RIP Score with opening economics and collector appeal.",
});
