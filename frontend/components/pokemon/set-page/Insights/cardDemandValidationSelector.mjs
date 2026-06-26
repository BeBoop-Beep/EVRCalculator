import {
  calculatePearsonCorrelation,
  calculateSpearmanCorrelation,
  toOptionalNumber,
  toOptionalString,
} from "../sharedStats.mjs";

function getCardMarketPrice(card) {
  const value = toOptionalNumber(card?.marketPrice ?? card?.market_price ?? card?.currentPrice ?? card?.current_price);
  return value !== null && value > 0 ? value : null;
}

function getCardDemandScore(card, metricKey) {
  if (metricKey === "treatment") {
    return toOptionalNumber(card?.treatmentScore ?? card?.treatment_score);
  }
  if (metricKey === "cardAppeal") {
    return (
      toOptionalNumber(card?.cardAppealScore ?? card?.card_appeal_score) ??
      toOptionalNumber(card?.adjustedCardAppealScore ?? card?.adjusted_card_appeal_score)
    );
  }
  return (
    toOptionalNumber(card?.subjectDemandScore ?? card?.subject_demand_score) ??
    toOptionalNumber(card?.pokemonDesirabilityScore ?? card?.pokemon_desirability_score) ??
    toOptionalNumber(card?.cardDesirabilityScore ?? card?.card_desirability_score) ??
    toOptionalNumber(card?.desirabilityScore ?? card?.desirability_score)
  );
}

function isHitEligible(card) {
  const value = card?.isHitEligible ?? card?.is_hit_eligible;
  return value === true || String(value).toLowerCase() === "true";
}

function canonicalRows(correlation, metricKey) {
  if (!correlation || !["pure", "cardAppeal", "treatment"].includes(metricKey)) {
    return [];
  }
  return Array.isArray(correlation.plotRows)
    ? correlation.plotRows
    : Array.isArray(correlation.plot_rows)
    ? correlation.plot_rows
    : Array.isArray(correlation.rows)
    ? correlation.rows
    : [];
}

export function selectCardDemandValidation(rawCards, { metricKey = "pure", scopeKey = "priced", correlation = null } = {}) {
  const sourceRows = canonicalRows(correlation, metricKey);
  const rows = sourceRows.length > 0 ? sourceRows : Array.isArray(rawCards) ? rawCards : [];
  const correlationN = toOptionalNumber(correlation?.n);
  const correlationPlottedCount =
    toOptionalNumber(correlation?.plottedCount) ??
    toOptionalNumber(correlation?.plotted_count);
  const diagnostics = {
    source: sourceRows.length > 0 ? "canonical_correlation_rows" : "cards_contract",
    totalRows: rows.length,
    rowsWithMarketPrice: 0,
    rowsWithSelectedMetric: 0,
    rowsExcludedByScope: 0,
    finalPlottedRows: 0,
    firstRejectionReasons: [],
  };
  const rawPoints = [];

  rows.forEach((card) => {
    const x = getCardDemandScore(card, metricKey);
    const y = getCardMarketPrice(card);
    if (x !== null) diagnostics.rowsWithSelectedMetric += 1;
    if (y !== null) diagnostics.rowsWithMarketPrice += 1;
    if (x === null || y === null) {
      if (diagnostics.firstRejectionReasons.length < 6) {
        diagnostics.firstRejectionReasons.push(x === null ? "missing_selected_metric" : "missing_market_price");
      }
      return;
    }
    rawPoints.push({
      kind: "card",
      x,
      y,
      name: toOptionalString(card?.name ?? card?.cardName ?? card?.card_name) || "Unknown card",
      rarity: toOptionalString(card?.rarity),
      isHitEligible: isHitEligible(card),
      setValueShare: toOptionalNumber(card?.setValueShare ?? card?.set_value_share),
    });
  });

  const points = rawPoints.filter((point) => {
    if (scopeKey === "hits" && !point.isHitEligible) {
      diagnostics.rowsExcludedByScope += 1;
      return false;
    }
    if (scopeKey === "chase" && !point.isHitEligible && point.y < 10 && (point.setValueShare === null || point.setValueShare < 0.0025)) {
      diagnostics.rowsExcludedByScope += 1;
      return false;
    }
    return true;
  });

  points.sort((left, right) => left.x - right.x);
  diagnostics.finalPlottedRows = points.length;

  return {
    rows: rows.map((row) => ({ ...row })),
    rawPoints,
    points,
    pearson: calculatePearsonCorrelation(points),
    spearman: calculateSpearmanCorrelation(points),
    sampleCount: points.length,
    sourceSampleCount: correlationN ?? correlationPlottedCount ?? points.length,
    diagnostics,
  };
}
