import { money, ratioAsPercent } from "./openingEconomicsSelector.mjs";

const finite = value => value !== null && value !== "" && Number.isFinite(Number(value)) ? Number(value) : null;
export const SET_PACK_COLUMNS = [
  ["productFamilies", "Product Families"], ["products", "Products"], ["packPrice", "Avg Cost / Pack"], ["modelBreakEven", "Break-Even / Pack"], ["typicalOpening", "Typical Opening / Pack"],
  ["modeledReturn", "Modeled Return"], ["entertainmentCost", "Entertainment Cost"], ["typicalRetention", "Typical Retention"],
  ["chanceToRecoverCost", "Chance to Recover Cost"]
];
export function projectSetPackMetric(target) {
  return { raw: { set_id: target?.setId, canonical_key: target?.setCanonicalKey, name: target?.setName }, setId: target?.setId, setName: target?.setName, canonicalKey: target?.setCanonicalKey,
    logo: target?.logoImageUrl || target?.symbolImageUrl, canonicalRank: target?.canonicalSetRipRank,
    productFamilies: finite(target?.productFamilyCount), products: finite(target?.productSkuCount),
    packPrice: finite(target?.averageCostPerPack), modelBreakEven: finite(target?.averageModelBreakEvenPerPack),
    typicalOpening: finite(target?.typicalOpeningPerPack), modeledReturn: finite(target?.modeledReturnOnSpend),
    entertainmentCost: finite(target?.averageEntertainmentCostPerPack), typicalRetention: finite(target?.typicalRetention),
    chanceToRecoverCost: finite(target?.chanceToRecoverCost), familyEconomics: target?.familyEconomics || [] };
}
export function mergeSetEconomics(sets, targets) {
  const identities = new Map((targets || []).map(target => [String(target.set_id || target.target_id), target]));
  return (sets || []).map(economics => {
    const identity = identities.get(String(economics.setId)) || {};
    return {...economics, canonicalSetRipRank: identity.canonicalSetRipRank ?? identity.setRipV1?.rank,
      logoImageUrl: identity.logo_image_url, symbolImageUrl: identity.symbol_image_url};
  });
}
export function sortSetPackMetrics(targets, key, direction="desc") {
  const sign = direction === "asc" ? 1 : -1;
  return (targets || []).map(projectSetPackMetric).sort((a,b) => { const av=finite(a[key]), bv=finite(b[key]); if(av===null)return bv===null?(a.canonicalRank||999)-(b.canonicalRank||999):1;if(bv===null)return -1;return sign*(av-bv)||(a.canonicalRank||999)-(b.canonicalRank||999); });
}
export const formatSetMetric = (key, value) => ["productFamilies","products"].includes(key) ? (value == null ? null : String(value)) : ["modeledReturn","typicalRetention","chanceToRecoverCost"].includes(key) ? ratioAsPercent(value) : money(value);
