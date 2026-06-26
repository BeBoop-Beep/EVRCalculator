function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toObject(value) {
  return value && typeof value === "object" ? value : {};
}

const PILLARS = [
  { key: "profit", title: "Profit" },
  { key: "safety", title: "Safety" },
  { key: "desirability", title: "Desirability" },
  { key: "stability", title: "Stability" },
];

export function selectRipScoreBreakdown(summary = {}, trends = {}) {
  const safeSummary = toObject(summary);
  const safeTrends = toObject(trends);
  const missingFields = [];
  const rows = PILLARS.map((pillar) => {
    const score = toOptionalNumber(safeSummary[`relative_${pillar.key}_score`] ?? safeSummary[`${pillar.key}_score`]);
    const rank = toOptionalNumber(safeSummary[`${pillar.key}_rank`]);
    const tier = safeSummary[`${pillar.key}_tier`] || null;
    if (score === null) missingFields.push(`${pillar.key}_score`);
    if (rank === null) missingFields.push(`${pillar.key}_rank`);
    return {
      ...pillar,
      score,
      scoreTrend: safeTrends[`${pillar.key}Score`] || null,
      rankValue: rank,
      rankTier: tier,
      rankDiagnostic: rank === null ? "Rank unavailable: source payload lacks rank field." : null,
    };
  });

  return {
    rows,
    sourceUsed: "summary",
    fallbackUsed: false,
    diagnostics: {
      source: "summary",
      missingFields,
      fallbackUsed: false,
    },
  };
}
