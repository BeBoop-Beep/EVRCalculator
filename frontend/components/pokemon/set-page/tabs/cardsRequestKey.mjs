import { PRICING_SNAPSHOT_CONTRACT_VERSION } from "@/lib/pokemon/pricingSnapshotContract.mjs";

export function buildCardsRequestKey({ setId, section, sort, sortDirection, query, rarity, movementFilter, movementSort, movementMetric, page, pageSize = 60, pricingContractVersion = PRICING_SNAPSHOT_CONTRACT_VERSION }) {
  return JSON.stringify({
    set: String(setId || ""),
    pricingContractVersion,
    section: section || null,
    sort: sort || null,
    sortDirection: sortDirection || null,
    query: query || null,
    rarity: rarity || null,
    movementFilter: movementFilter || null,
    movementSort: movementSort || null,
    movementMetric: movementMetric || null,
    page: Number(page) || 1,
    pageSize: Number(pageSize) || 60,
  });
}

export function buildCardsScopeKey(request) {
  return buildCardsRequestKey({ ...request, page: 0 }).replace('"page":1', '"page":0');
}
