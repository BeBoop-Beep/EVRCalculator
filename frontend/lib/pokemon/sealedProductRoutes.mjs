function usableText(value) {
  if (value == null) return null;
  const normalized = String(value).trim();
  return normalized || null;
}

/** The single frontend builder for canonical sealed-product detail URLs. */
export function buildSealedProductHref(productOrId) {
  const id = productOrId && typeof productOrId === "object"
    ? usableText(productOrId.sealedProductId ?? productOrId.sealed_product_id ?? productOrId.productPageId ?? productOrId.product_id ?? productOrId.id)
    : usableText(productOrId);
  return id ? `/sealed-products/${encodeURIComponent(id)}` : null;
}
