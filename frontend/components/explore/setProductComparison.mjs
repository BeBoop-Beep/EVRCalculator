export const SET_PRODUCT_FAMILY_ORDER = [
  "loose_booster_pack",
  "sleeved_booster_pack",
  "booster_bundle",
  "elite_trainer_box",
  "half_booster_box",
  "pokemon_center_elite_trainer_box",
  "booster_box",
  "enhanced_booster_box",
];

export function buildFamilyRankLookup(productFamilyRankings) {
  const lookup = new Map();
  const families = productFamilyRankings?.families;
  if (!families || typeof families !== "object") return lookup;
  for (const block of Object.values(families)) {
    const size = Number(block?.count ?? block?.currentlyRankableCount);
    for (const row of Array.isArray(block?.products) ? block.products : []) {
      const id = row?.sealedProductId;
      const rank = Number(row?.familyRank);
      if (!id || !Number.isFinite(rank) || !Number.isFinite(size) || size <= 0) continue;
      lookup.set(String(id), {
        familyRank: rank,
        familySize: Number(row?.familyCohortSize ?? row?.familySize ?? size),
        familyTier: row?.familyTier ?? null,
        overallRipLeaderScore: Number.isFinite(Number(row?.overallRipLeaderScore)) ? Number(row.overallRipLeaderScore) : null,
        publicTier: row?.publicTier ?? null,
        productFamilyLabel: row?.productFamilyLabel ?? block?.label ?? null,
        productImageUrl: row?.productImageUrl ?? null,
        setCanonicalKey: row?.setCanonicalKey ?? null,
      });
    }
  }
  return lookup;
}

export function groupProductsByFamily(products) {
  const order = [];
  const groups = new Map();
  for (const product of products || []) {
    const key = product.family || "unknown";
    if (!groups.has(key)) {
      groups.set(key, []);
      order.push(key);
    }
    groups.get(key).push(product);
  }
  return order
    .slice()
    .sort((a, b) => {
      const ai = SET_PRODUCT_FAMILY_ORDER.indexOf(a), bi = SET_PRODUCT_FAMILY_ORDER.indexOf(b);
      return (ai < 0 ? SET_PRODUCT_FAMILY_ORDER.length : ai) - (bi < 0 ? SET_PRODUCT_FAMILY_ORDER.length : bi);
    })
    .map((family) => ({ family, products: groups.get(family) }));
}
