import { hasIndexPlusAccess } from "../access/indexPlanAccess.mjs";

const PUBLIC_PRODUCT_FIELDS = new Set([
  "sealedProductId", "productName", "productFamily", "packCount", "marketPrice",
  "priceAsOf", "priceSource", "composition", "availability",
]);
const PUBLIC_RIP_HEADLINE_FIELDS = new Set([
  "leaderNormalizedScore", "relativeScore", "rank", "tier", "rankedSetCount", "cohortSize",
  "status", "statusReason", "modelVersion", "marketDate", "asOfDate",
]);
const ADVANCED_PAYLOAD_KEYS = new Set([
  "productFamilyRankings", "evRepresentativeness", "rankings", "pack_paths", "packPaths",
]);

function publicProduct(product) {
  if (!product || typeof product !== "object") return product;
  return Object.fromEntries(Object.entries(product).filter(([key]) => PUBLIC_PRODUCT_FIELDS.has(key)));
}

function redactDecision(decision) {
  if (!decision || typeof decision !== "object") return decision;
  const sealed = decision.sealedProducts && typeof decision.sealedProducts === "object"
    ? { ...decision.sealedProducts, products: (decision.sealedProducts.products || []).map(publicProduct) }
    : decision.sealedProducts;
  const chase = decision.topChase && typeof decision.topChase === "object"
    ? { ...decision.topChase, packsFor50PercentChance: null, packsFor90PercentChance: null }
    : decision.topChase;
  return { ...decision, sealedProducts: sealed, topChase: chase, premiumMetricsIncluded: false };
}

function headlineBlock(block) {
  if (!block || typeof block !== "object") return block;
  return Object.fromEntries(Object.entries(block).filter(([key]) => PUBLIC_RIP_HEADLINE_FIELDS.has(key)));
}

function redactPublicRipContract(contract) {
  if (!contract || typeof contract !== "object") return contract;
  return {
    ...contract,
    overallRip: headlineBlock(contract.overallRip),
    financialRip: headlineBlock(contract.financialRip),
    collectorAppeal: headlineBlock(contract.collectorAppeal),
    audit: undefined,
  };
}

function redactNode(value) {
  if (Array.isArray(value)) return value.map(redactNode);
  if (!value || typeof value !== "object") return value;
  const result = {};
  for (const [key, child] of Object.entries(value)) {
    if (ADVANCED_PAYLOAD_KEYS.has(key)) {
      result[key] = Array.isArray(child) ? [] : null;
    } else if (key === "ripDecision") {
      result[key] = redactDecision(child);
    } else if (/^publicRipContractV\d+$/.test(key)) {
      result[key] = redactPublicRipContract(child);
    } else {
      result[key] = redactNode(child);
    }
  }
  return result;
}

/** Server response boundary: Basic clients never receive proprietary RIP values. */
export function applySetRipEntitlement(payload, user) {
  if (hasIndexPlusAccess(user?.index_plan)) return payload;
  return redactNode(payload);
}
