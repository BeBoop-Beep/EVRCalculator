import { selectEvRepresentativenessPublicV1 } from "../../explore/evRepresentativenessSelector.mjs";

/**
 * The product's page inherits the SET's own confirmed EV realization
 * horizon (packs to reach 80% of openers realizing 80% of long-run EV).
 * This is deliberately NOT a product-specific convergence calculation -
 * there is exactly one EV representativeness implementation
 * (selectEvRepresentativenessPublicV1), reused here rather than forked, and
 * it only ever resolves when `rip.setEvRepresentativeness` carries the
 * SAME calculationRunId as `rip.calculationRunId` (the product's own
 * validated RIP run).
 */
export function selectSetEvRealizationHeadline(rip) {
  const projection = selectEvRepresentativenessPublicV1(
    rip?.setEvRepresentativeness,
    rip?.calculationRunId,
  );
  return projection?.realizationHorizon || null;
}

export const PRODUCT_MARKET_WINDOWS = Object.freeze([
  { key: "1D", label: "1D" }, { key: "7D", label: "7D" },
  { key: "30D", label: "30D" }, { key: "3M", label: "3M" },
  { key: "6M", label: "6M" }, { key: "1Y", label: "1Y" },
  { key: "lifetime", label: "ALL" },
]);

export function finite(value) {
  const number = Number(value);
  return value !== null && value !== undefined && Number.isFinite(number) ? number : null;
}

export function pluralFamilyLabel(label) {
  return ({
    "Elite Trainer Box": "Elite Trainer Boxes",
    "Pokémon Center Elite Trainer Box": "Pokémon Center Elite Trainer Boxes",
    "Booster Box": "Booster Boxes",
    "Enhanced Booster Box": "Enhanced Booster Boxes",
    "Booster Bundle": "Booster Bundles",
    "Loose Booster Pack": "Loose Booster Packs",
    "Sleeved Booster Pack": "Sleeved Booster Packs",
    "Half Booster Box": "Half Booster Boxes",
  })[label] || `${label || "Product"}s`;
}

export function formatStrength(rip) {
  const rank = finite(rip?.familyRank);
  const tier = String(rip?.publicTier || "").toUpperCase();
  if (rank === 1) return "Format leader";
  if (tier === "S") return "Elite in format";
  if (tier === "A") return "Strong in format";
  if (tier === "B") return "Competitive in format";
  return "Ranks within format";
}

export function productCompositionSummary(composition) {
  const packs = finite(composition?.packCount);
  const guaranteed = finite(composition?.guaranteedComponentCount);
  const guaranteedValue = finite(composition?.guaranteedComponentMarketValue);
  const parts = [];
  if (packs !== null && packs > 0) parts.push(`${packs} ${packs === 1 ? "Pack" : "Packs"}`);
  if (guaranteed !== null && guaranteed > 0) parts.push(`${guaranteed} Modeled Guaranteed ${guaranteed === 1 ? "Component" : "Components"}`);
  return {
    available: parts.length > 0 || guaranteedValue !== null,
    summary: parts.join(" + "),
    guaranteedValue: guaranteed !== null && guaranteed > 0 ? guaranteedValue : null,
  };
}

export function selectProductMarketWindow(market, key) {
  const movement = market?.movements?.[key] || {};
  const history = Array.isArray(market?.history) ? market.history : [];
  const start = movement.actualStartDate;
  const end = movement.endDate;
  return {
    movement: {
      ...movement,
      available: movement.status === "available",
      deltaAmount: movement.amount,
      deltaPercent: movement.percent,
    },
    history: start && end
      ? history.filter((point) => point?.date >= start && point?.date <= end)
      : key === "lifetime" ? history : [],
    partial: movement.status === "available" && movement.fullWindowCoverage === false,
  };
}

export function comparisonRows(detail, mode) {
  const currentId = String(detail?.product?.id || "");
  const family = detail?.product?.productFamily;
  const source = mode === "sameFamily" ? detail?.comparisons?.sameFamily : detail?.comparisons?.sameSet;
  const seen = new Set();
  return (Array.isArray(source) ? source : []).filter((row) => {
    const id = String(row?.sealedProductId || "");
    if (!id || id === currentId || seen.has(id)) return false;
    if (mode === "sameFamily" && row?.productFamily !== family) return false;
    seen.add(id);
    return true;
  }).slice(0, mode === "sameFamily" ? 5 : 10);
}

export function buildProductParentSetHref(set) {
  const slug = String(set?.slug || set?.canonicalKey || "").trim();
  return slug ? `/TCGs/Pokemon/Sets/${encodeURIComponent(slug)}` : "/TCGs/Pokemon/Sets";
}
