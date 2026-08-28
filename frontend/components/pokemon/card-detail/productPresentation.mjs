import { buildSealedProductHref as buildCanonicalSealedProductHref } from "../../../lib/pokemon/sealedProductRoutes.mjs";

const EXPECTED_LABELS = {
  loose_booster_pack: ["Expected Packs to Pull", "eligible packs"],
  sleeved_booster_pack: [
    "Expected Sleeved Booster Packs to Pull",
    "Sleeved Booster Packs",
  ],
  booster_bundle: ["Expected Booster Bundles to Pull", "Booster Bundles"],
  elite_trainer_box: ["Expected ETBs to Pull", "Elite Trainer Boxes"],
  pokemon_center_elite_trainer_box: [
    "Expected PC ETBs to Pull",
    "Pokémon Center Elite Trainer Boxes",
  ],
  booster_box: ["Expected Booster Boxes to Pull", "Booster Boxes"],
  half_booster_box: [
    "Expected Half Booster Boxes to Pull",
    "Half Booster Boxes",
  ],
};

export function orderCardProducts(products) {
  const unique = new Map();
  for (const product of Array.isArray(products) ? products : []) {
    const id = String(product?.sealedProductId || "").trim();
    if (id && !unique.has(id)) unique.set(id, product);
  }
  return [...unique.values()].sort((left, right) => {
    const support =
      Number(Boolean(right.available)) - Number(Boolean(left.available));
    if (support) return support;
    // Supported products arrive in the authoritative chase-contract order.
    // Modern Array.prototype.sort is stable, so returning zero preserves it.
    if (left.available && right.available) return 0;
    return (
      String(left.productName || left.productFamilyLabel || "").localeCompare(
        String(right.productName || right.productFamilyLabel || ""),
      ) ||
      String(left.sealedProductId).localeCompare(String(right.sealedProductId))
    );
  });
}

export function productDisplayPrice(product) {
  const supported = Number(product?.productPrice);
  if (Number.isFinite(supported) && supported > 0) return supported;
  const catalog = Number(product?.currentPrice);
  return Number.isFinite(catalog) && catalog > 0 ? catalog : null;
}

export function expectedProductsCopy(product) {
  const [label, plural] = EXPECTED_LABELS[product?.productFamily] || [
    "Expected Products to Pull",
    "selected products",
  ];
  return {
    label,
    tooltip:
      product?.productFamily === "loose_booster_pack"
        ? "The long-run expected number of eligible packs opened per copy of this card. This is an average, not a guarantee."
        : `The long-run expected number of ${plural} opened per copy of this card. This is an average, not a guarantee that the card will appear within that many products.`,
  };
}

export function buildSealedProductHref(product) {
  return buildCanonicalSealedProductHref(product?.productPageId);
}
