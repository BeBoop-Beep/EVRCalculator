// Global TCGs navigation contract, kept in a plain module so the destination
// and the active-route rule are testable without rendering the header.

// Pokémon is the only live TCG, so the global TCGs category resolves straight
// to its Sets catalog. The /TCGs/* URL family is unchanged.
export const TCGS_NAV_HREF = "/TCGs/Pokemon/Sets";

// A primary nav item is active on its own path and anywhere beneath it, so
// TCGs stays lit across /TCGs, /TCGs/Pokemon and every set detail page.
export function isTopNavRouteActive(pathname, path) {
  if (typeof pathname !== "string" || typeof path !== "string") return false;
  return pathname === path || pathname.startsWith(`${path}/`);
}
