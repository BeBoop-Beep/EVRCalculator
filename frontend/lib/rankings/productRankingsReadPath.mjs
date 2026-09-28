async function payload(response) {
  return response.json().catch(() => null);
}

export async function loadProductRankingsAuthorities({
  fetchImpl = fetch,
  normalizeOverallProductResult,
} = {}) {
  const [lensResponse, overallResponse] = await Promise.all([
    fetchImpl("/api/explore/rankings/lens?lens=products", { cache: "no-store" }),
    fetchImpl("/api/explore/product-rankings/overall?budget=full_market", { cache: "no-store" }),
  ]);
  const [familyPayload, overallPayload] = await Promise.all([
    payload(lensResponse),
    payload(overallResponse),
  ]);
  if (!lensResponse.ok || familyPayload?.status !== "available") {
    throw new Error(familyPayload?.message || "Product rankings are unavailable");
  }
  if (!overallResponse.ok || overallPayload?.available !== true) {
    throw new Error(overallPayload?.message || "Full Market product rankings are unavailable");
  }
  return {
    state: {
      status: "ready",
      productFamilyRankings: familyPayload.productFamilyRankings || null,
    },
    overallResult: normalizeOverallProductResult(overallPayload),
  };
}
