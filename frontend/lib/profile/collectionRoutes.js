export const COLLECTION_DETAIL_TABS = ["overview", "analytics", "history", "details"];

export function getDefaultCollectionDetailTab() {
  return COLLECTION_DETAIL_TABS[0];
}

export function normalizeCollectionDetailTab(tab) {
  if (!tab) return getDefaultCollectionDetailTab();
  const normalized = String(tab).toLowerCase();
  return COLLECTION_DETAIL_TABS.includes(normalized) ? normalized : getDefaultCollectionDetailTab();
}

export function buildMyCollectionListRoute() {
  return "/my-portfolio/collection";
}

export function buildCardRoute(cardId) {
  return `/cards/${encodeURIComponent(String(cardId || ""))}`;
}

export function buildSealedProductRoute(productId) {
  return `/sealed-products/${encodeURIComponent(String(productId || ""))}`;
}

export function buildPublicCollectibleRouteFromEntry(entry) {
  if (!entry) return "/";
  if (entry.collectible_type === "sealed_product") {
    return buildSealedProductRoute(entry.collectible_id);
  }
  return buildCardRoute(entry.collectible_id);
}

export function buildMyCollectionEntryRoute(entry, tab) {
  const section = entry?.collectible_type === "sealed_product" ? "products" : "cards";
  const base = `/my-portfolio/${section}/${encodeURIComponent(String(entry?.id || ""))}`;
  const normalizedTab = normalizeCollectionDetailTab(tab);
  return normalizedTab === getDefaultCollectionDetailTab() ? base : `${base}/${normalizedTab}`;
}

export function buildPublicCollectionListRoute(username) {
  return `/u/${encodeURIComponent(String(username || ""))}`;
}

export function buildShowcaseAssetHref({ asset, mode = "public", username = "" }) {
  if (!asset) {
    return mode === "owner" ? buildMyCollectionListRoute() : buildPublicCollectionListRoute(username);
  }

  if (mode === "owner") {
    if (asset.id && asset.collectible_type) {
      return buildMyCollectionEntryRoute(asset);
    }

    if (asset.collectible_type === "sealed_product") {
      return buildSealedProductRoute(asset.collectible_id);
    }

    return buildCardRoute(asset.collectible_id);
  }

  if (asset.collectible_type && asset.collectible_id) {
    return buildPublicCollectibleRouteFromEntry(asset);
  }

  return buildPublicCollectionListRoute(username);
}
