export const SEALED_MARKET_WINDOWS = Object.freeze([
  { key: "7D", label: "7D" },
  { key: "30D", label: "30D" },
  { key: "3M", label: "3M" },
  { key: "LT", label: "LT" },
]);

const FAMILY_LABELS = {
  booster_box: "Booster Box",
  enhanced_booster_box: "Enhanced Booster Box",
  elite_trainer_box: "ETB",
  pokemon_center_elite_trainer_box: "PC ETB",
  booster_bundle: "Booster Bundle",
  booster_pack: "Booster Pack",
  sleeved_booster_pack: "Sleeved Pack",
};

export function compactSealedProductLabel(product) {
  const base = FAMILY_LABELS[product?.productFamily] || product?.productFamilyLabel || "Sealed Product";
  return product?.variantLabel ? `${base} — ${product.variantLabel}` : base;
}

export function selectSealedProduct(payload, selectedId) {
  const products = Array.isArray(payload?.products) ? payload.products : [];
  return products.find((item) => String(item.sealedProductId) === String(selectedId))
    || products.find((item) => String(item.sealedProductId) === String(payload?.defaultProductId))
    || products[0]
    || null;
}

export function selectSealedWindow(product, windowKey = "30D") {
  const movement = product?.movements?.[windowKey] || {};
  const endDate = movement.endDate || product?.priceAsOf;
  const history = Array.isArray(product?.history) ? product.history : [];
  const visibleHistory = windowKey === "LT" || !movement.requestedStartDate
    ? history
    : history.filter((point) => point.date >= movement.requestedStartDate && (!endDate || point.date <= endDate));
  return { movement, history: visibleHistory };
}
