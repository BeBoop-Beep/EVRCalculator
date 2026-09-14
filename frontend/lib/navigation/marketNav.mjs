export const MARKET_EXPLORER_NAV_HREF = "/Market/Explorer";

function normalized(pathname) {
  if (typeof pathname !== "string") return "";
  return (pathname.split(/[?#]/, 1)[0].replace(/\/+$/, "") || "/").toLowerCase();
}

export function isExplorerNavRouteActive(pathname) {
  const path = normalized(pathname);
  const explorer = MARKET_EXPLORER_NAV_HREF.toLowerCase();
  return path === explorer || path.startsWith(`${explorer}/`);
}

export function isMarketNavRouteActive(pathname) {
  const path = normalized(pathname);
  return (path === "/market" || path.startsWith("/market/")) && !isExplorerNavRouteActive(path);
}
