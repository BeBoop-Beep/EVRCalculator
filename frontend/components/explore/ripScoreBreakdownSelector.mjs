// The four pillar cards under the RIP hero.
//
// CANONICAL CONTRACT ONLY. Rows come from the backend's `rip.components` —
// actual component scores, backend-computed ranks/tiers against the public
// cohort, the configured weight, and the direct contribution (score x weight).
// The legacy `relative_*_score` fields are a cohort min-max presentation and
// are deliberately not read, even as a fallback: a silently min-maxed pillar
// is a different number wearing the same label. Missing canonical data renders
// as unavailable (see the rankDiagnostic), never as a legacy score.
//
// The fourth pillar is Collector Appeal (CA7). The backend keys it
// `desirability` inside rip.components for weight-config compatibility; the
// public label is Collector Appeal, and relabeling happens HERE, in exactly
// one place.

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

// Display order per the product spec: financial pillars by weight, then the
// Collector Appeal pillar.
const PILLARS = [
  { key: "profit", title: "Profit", trendKey: "profitScore" },
  { key: "safety", title: "Safety", trendKey: "safetyScore" },
  { key: "stability", title: "Stability", trendKey: "stabilityScore" },
  { key: "desirability", title: "Collector Appeal", trendKey: "desirabilityScore" },
];

export function selectRipScoreBreakdown(rip = {}, trends = {}, options = {}) {
  const safeRip = toObject(rip);
  const components = toObject(safeRip.components);
  const safeTrends = toObject(trends);
  const requestTimeout = options?.requestTimeout === true || options?.payload?.meta?.requestTimeout === true;
  const hasContract = Object.keys(components).length > 0;
  const missingFields = [];

  const rows = PILLARS.map((pillar) => {
    const component = toObject(components[pillar.key]);
    const score = toOptionalNumber(component.score);
    const rank = toOptionalNumber(component.rank);
    const tier = component.tier ?? null;
    if (score === null) missingFields.push(`${pillar.key}.score`);
    if (rank === null) missingFields.push(`${pillar.key}.rank`);
    return {
      key: pillar.key,
      title: pillar.title,
      score,
      scoreTrend: safeTrends[pillar.trendKey] || null,
      rankValue: rank,
      rankTier: tier,
      cohortSize: toOptionalNumber(component.cohortSize),
      weight: toOptionalNumber(component.weight),
      contribution: toOptionalNumber(component.contribution),
      rankDiagnostic:
        rank === null
          ? requestTimeout
            ? "Rank loading: set page snapshot request timed out; retrying."
            : hasContract
            ? "Rank unavailable: canonical RIP component lacks a rank."
            : "Rank unavailable: canonical RIP contract missing from payload."
          : null,
    };
  });

  return {
    rows,
    sourceUsed: "rip.components",
    fallbackUsed: false,
    diagnostics: {
      source: "rip.components",
      status: requestTimeout ? "loading" : hasContract ? "ready" : "unavailable",
      requestTimeout,
      missingFields: requestTimeout ? [] : missingFields,
      fallbackUsed: false,
    },
  };
}
