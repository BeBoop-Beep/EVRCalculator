import { hasIndexPlusAccess } from "../access/indexPlanAccess.mjs";

const PUBLIC_PRODUCT_FIELDS = new Set([
  "sealedProductId",
  "productName",
  "productFamily",
  "packCount",
  "marketPrice",
  "priceAsOf",
  "priceSource",
  "composition",
  "availability",
]);
const PUBLIC_RIP_HEADLINE_FIELDS = new Set([
  "leaderNormalizedScore",
  "relativeScore",
  "rank",
  "tier",
  "rankedSetCount",
  "cohortSize",
  "status",
  "statusReason",
  "modelVersion",
  "marketDate",
  "asOfDate",
]);
const ADVANCED_PAYLOAD_KEYS = new Set([
  "productFamilyRankings",
  "evRepresentativeness",
  "rankings",
  "pack_paths",
  "packPaths",
  "percentiles",
  "financialRip",
  "collectorAppeal",
  "rarityContribution",
  "setRipV1",
]);
const PUBLIC_SUMMARY_FIELDS = new Set([
  "packCost",
  "pack_cost",
  "meanValue",
  "mean_value",
  "medianValue",
  "median_value",
  "probProfit",
  "prob_profit",
  "calculationRunId",
  "calculation_run_id",
]);

function publicProduct(product) {
  if (!product || typeof product !== "object") return product;
  return Object.fromEntries(
    Object.entries(product).filter(([key]) => PUBLIC_PRODUCT_FIELDS.has(key)),
  );
}

function redactDecision(decision) {
  if (!decision || typeof decision !== "object") return decision;
  const sealed =
    decision.sealedProducts && typeof decision.sealedProducts === "object"
      ? {
          ...decision.sealedProducts,
          products: (decision.sealedProducts.products || []).map(publicProduct),
        }
      : decision.sealedProducts;
  const chase =
    decision.topChase && typeof decision.topChase === "object"
      ? {
          ...decision.topChase,
          packsFor50PercentChance: null,
          packsFor90PercentChance: null,
        }
      : decision.topChase;
  return {
    ...decision,
    sealedProducts: sealed,
    topChase: chase,
    premiumMetricsIncluded: false,
  };
}

function headlineBlock(block) {
  if (!block || typeof block !== "object") return block;
  return Object.fromEntries(
    Object.entries(block).filter(([key]) =>
      PUBLIC_RIP_HEADLINE_FIELDS.has(key),
    ),
  );
}

function publicSubjectPath(path) {
  if (!path || typeof path !== "object") return path;
  const {
    packsFor50PercentChance: _packs50,
    packsFor90PercentChance: _packs90,
    packs_for_50_percent_chance: _packs50Snake,
    packs_for_90_percent_chance: _packs90Snake,
    acquisitionDistribution: _distribution,
    acquisition_distribution: _distributionSnake,
    ...publicFields
  } = path;
  return publicFields;
}

function publicCollectorSubject(subject) {
  if (!subject || typeof subject !== "object") return subject;
  const {
    diagnostics: _diagnostics,
    acquisitionAnalytics: _acquisition,
    ...publicFields
  } = subject;
  const result = { ...publicFields };
  if ("accessiblePath" in subject)
    result.accessiblePath = publicSubjectPath(subject.accessiblePath);
  if ("elitePath" in subject)
    result.elitePath = publicSubjectPath(subject.elitePath);
  if ("accessible_path" in subject)
    result.accessible_path = publicSubjectPath(subject.accessible_path);
  if ("elite_path" in subject)
    result.elite_path = publicSubjectPath(subject.elite_path);
  return result;
}

function publicCollectorAppeal(block) {
  if (!block || typeof block !== "object") return block;
  return {
    ...headlineBlock(block),
    topSubjects: Array.isArray(block.topSubjects)
      ? block.topSubjects.map(publicCollectorSubject)
      : [],
  };
}

function redactPublicRipContract(contract) {
  if (!contract || typeof contract !== "object") return contract;
  return {
    ...contract,
    overallRip: headlineBlock(contract.overallRip),
    financialRip: headlineBlock(contract.financialRip),
    collectorAppeal: publicCollectorAppeal(contract.collectorAppeal),
    audit: undefined,
  };
}

function publicOutcomeProfile(profile) {
  if (
    !profile ||
    typeof profile !== "object" ||
    !Array.isArray(profile.buckets)
  )
    return profile;
  const definitions = [
    [
      "under-half",
      "Less Than Half Back",
      (row) => row.ceilingRatio != null && Number(row.ceilingRatio) <= 0.5,
      0,
      0.5,
    ],
    [
      "half-to-cost",
      "Half Back to Under Cost",
      (row) =>
        Number(row.floorRatio) >= 0.5 &&
        row.ceilingRatio != null &&
        Number(row.ceilingRatio) <= 1,
      0.5,
      1,
    ],
    [
      "cost-to-two",
      "Recovered Cost to Under 2×",
      (row) =>
        Number(row.floorRatio) >= 1 &&
        row.ceilingRatio != null &&
        Number(row.ceilingRatio) <= 2,
      1,
      2,
    ],
    ["two-plus", "2× or More", (row) => Number(row.floorRatio) >= 2, 2, null],
  ];
  const buckets = definitions.map(
    ([key, label, predicate, floorRatio, ceilingRatio]) => ({
      key,
      label,
      floorRatio,
      ceilingRatio,
      probability: profile.buckets
        .filter(predicate)
        .reduce((sum, row) => sum + Number(row.probability || 0), 0),
      interpretation: `${label}: share of modeled openings in this return range.`,
    }),
  );
  return {
    ...profile,
    buckets,
    cumulativeProbabilities: [],
    premiumDetailIncluded: false,
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
    } else if (key === "summary") {
      result[key] = Object.fromEntries(
        Object.entries(child || {}).filter(([field]) =>
          PUBLIC_SUMMARY_FIELDS.has(field),
        ),
      );
    } else if (key === "openingOutcomeProfile") {
      result[key] = publicOutcomeProfile(child);
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
