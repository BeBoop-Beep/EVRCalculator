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
  title: "Best Pokémon Sets to Rip Right Now — inDex",
  // "Overall RIP" is the current public name of the headline metric (see
  // /Research and the set page verdict card); the retired "RIP Score" label
  // must not come back through metadata.
  description:
    "Current Pokémon set rankings by Overall RIP, with Financial RIP, Collector Appeal and modeled opening economics for every ranked set.",
  ogTitle: "Best Pokémon Sets to Rip Right Now",
  ogDescription:
    "See which Pokémon sets rank strongest to open right now, ranked by Overall RIP with opening economics and collector appeal.",
});
