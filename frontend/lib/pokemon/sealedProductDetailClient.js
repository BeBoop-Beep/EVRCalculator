function text(value) {
  const normalized = value == null ? "" : String(value).trim();
  return normalized || null;
}

export function normalizeSealedProductDetail(payload) {
  if (!payload || typeof payload !== "object") return null;
  return {
    set: payload.set || {}, product: payload.product || {},
    market: payload.market || { available: false, history: [], movements: {}, reason: "market_history_unavailable" },
    rip: payload.rip || { available: false, reason: "rip_unavailable" },
    comparisons: {
      sameSet: Array.isArray(payload.comparisons?.sameSet) ? payload.comparisons.sameSet : [],
      sameFamily: Array.isArray(payload.comparisons?.sameFamily) ? payload.comparisons.sameFamily : [],
    },
    meta: payload.meta || {},
  };
}

export async function getSealedProductDetail(productId, { signal } = {}) {
  const id = text(productId);
  if (!id) throw new Error("Sealed product id is required");
  const response = await fetch(`/api/tcgs/pokemon/sealed-products/${encodeURIComponent(id)}`, {
    method: "GET", cache: "no-store", signal, headers: { Accept: "application/json" },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(payload?.message || "Unable to load Pokemon sealed product detail");
    error.status = response.status; error.code = payload?.code; throw error;
  }
  return normalizeSealedProductDetail(payload);
}
