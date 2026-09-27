const numeric = (value) => { if (value === null || value === undefined || value === "") return null; const number = Number(value); return Number.isFinite(number) ? number : null; };
const displayedScore = (value) => { const score = numeric(value); return score === null ? null : Math.round((score + Number.EPSILON) * 10) / 10; };

export function formatBenchmarkScore(value) {
  const score = numeric(value);
  return score === null ? "Unavailable" : `${displayedScore(score).toFixed(1)} / 10`;
}

export function benchmarkPosition(value) {
  const score = numeric(value);
  if (score === null) return "Unavailable";
  const displayed = displayedScore(score);
  if (displayed > 5) return "Above Pokémon benchmark";
  if (displayed < 5) return "Below Pokémon benchmark";
  return "At Pokémon benchmark";
}

export function normalizeBenchmarkMetric(row, context = {}) {
  const score = row?.benchmark_status === "available" ? numeric(row?.benchmark_score) : null;
  return {
    available: score !== null,
    metricKey: row?.metric_key || null,
    score,
    scoreDisplay: formatBenchmarkScore(score),
    position: benchmarkPosition(score),
    rawModelValue: numeric(row?.raw_model_value),
    benchmarkRawValue: numeric(row?.benchmark_raw_value),
    rank: numeric(row?.rank), cohortSize: numeric(row?.cohort_size),
    modelStatus: row?.model_status || "unavailable", benchmarkStatus: row?.benchmark_status || "unavailable",
    modelReason: row?.model_reason || null, benchmarkReason: row?.benchmark_reason || null,
    sourceMarketDate: row?.source_market_date || null,
    financialEvidenceStatus: row?.financial_evidence_status || "not_applicable",
    financialEvidence: {
      marketDate: row?.financial_evidence_market_date || null,
      costPerPack: numeric(row?.cost_per_pack), expectedValuePerPack: numeric(row?.expected_value_per_pack),
      p50ValuePerPack: numeric(row?.p50_value_per_pack), chanceToRecoverCost: numeric(row?.chance_to_recover_cost),
      modeledReturnOnSpend: numeric(row?.modeled_return_on_spend),
    },
    openingEconomicsReference: context.openingEconomicsReference || null,
    inheritance: { parentSetId: row?.parent_set_id || null, sourceEntityType: row?.source_entity_type || null, sourceEntityId: row?.source_entity_id || null, modelStatus: row?.model_status || null },
  };
}

export function benchmarkMetric(rows, entityType, entityId, metricKey, context) {
  const row = (rows || []).find((item) => item?.entity_type === entityType && String(item?.entity_id) === String(entityId) && item?.metric_key === metricKey);
  return normalizeBenchmarkMetric(row, context);
}

export function formatBenchmarkFreshness(freshness) {
  const value = freshness?.benchmarkMarketDate || freshness?.modelSourceDate;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return null;
  return `As of ${new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`))}`;
}
