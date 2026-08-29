import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { normalizeSealedProductDetail } from "@/lib/pokemon/sealedProductDetailClient";

const DETAIL_REVALIDATE_SECONDS = 120;

export const getSealedProductDetailServer = cache(async function getSealedProductDetailServer(productId) {
  const id = String(productId ?? "").trim();
  if (!id) {
    const error = new Error("Sealed product id is required");
    error.status = 404;
    throw error;
  }
  const response = await fetch(`${getBackendApiBaseUrl()}/tcgs/pokemon/sealed-products/${encodeURIComponent(id)}`, {
    headers: { Accept: "application/json" },
    next: {
      revalidate: DETAIL_REVALIDATE_SECONDS,
      tags: [`pokemon-sealed-product-detail:${id}`],
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(payload?.message || "Unable to load Pokemon sealed product detail");
    error.status = response.status;
    error.code = payload?.code;
    throw error;
  }
  return normalizeSealedProductDetail(payload);
});
