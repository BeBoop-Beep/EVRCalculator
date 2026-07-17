/**
 * Configuration for Explore page ranking mode dropdown.
 *
 * RIP-contract modes read the CANONICAL backend objects — `rip` (Overall RIP),
 * `rip.financialRip.components.*` (the three Financial RIP pillars), and
 * `universalSetDesirability` — actual scores with ranks/tiers computed against
 * the backend-authorized public cohort. The legacy relative/pack score fields
 * are a cohort min-max presentation over the old 33-set population and must not
 * power public ranking again. Fields are dot-paths resolved by getFieldValue.
 *
 * The pillars moved out of `rip.components.*` when Overall RIP became Financial
 * RIP plus a desirability adjustment: RIP is no longer a weighted average of
 * four pillars, so it has no `components` of its own. The desirability lens
 * reads `universalSetDesirability`, the authoritative score — not CA7, which is
 * a simulation-only diagnostic and is absent wherever a pull model is.
 */

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function getFieldValue(target, fieldPath) {
  if (!target || !fieldPath) {
    return null;
  }
  let value = target;
  for (const key of String(fieldPath).split(".")) {
    if (value === null || value === undefined || typeof value !== "object") {
      return null;
    }
    value = value[key];
  }
  return value === undefined ? null : value;
}

export const EXPLORE_RANKING_MODES = {
  overall: {
    id: "overall",
    label: "Best Overall",
    title: "Best Sets to Rip Right Now",
    subtitle: "Sets ranked by the strongest overall opening profile.",
    tooltip: "Sets ranked by the strongest overall opening profile.",
    scoreLabel: "RIP SCORE",
    tierLabel: "TIER",
    scoreField: "rip.score",
    rankField: "rip.rank",
    tierField: "rip.tier",
    scoreFormat: "decimal",
    description: "Overall RIP score combines all factors for a comprehensive ranking.",
  },
  profit: {
    id: "profit",
    label: "Most Profitable",
    title: "Most Profitable Sets",
    subtitle: "Sets ranked by their profit profile, including chance to beat cost, Expected Value, and upside.",
    tooltip: "Sets ranked by their profit profile, including chance to beat cost, Expected Value, and upside.",
    scoreLabel: "PROFIT SCORE",
    tierLabel: "PROFIT TIER",
    scoreField: "rip.financialRip.components.profit.score",
    rankField: "rip.financialRip.components.profit.rank",
    tierField: "rip.financialRip.components.profit.tier",
    scoreFormat: "decimal",
    description: "Profit score focuses on return potential and margin above pack cost.",
  },
  safety: {
    id: "safety",
    label: "Safest Opens",
    title: "Safest Sets to Open",
    subtitle: "Sets ranked by how well they protect against rough openings.",
    tooltip: "Sets ranked by how well they protect against rough openings.",
    scoreLabel: "SAFETY SCORE",
    tierLabel: "SAFETY TIER",
    scoreField: "rip.financialRip.components.safety.score",
    rankField: "rip.financialRip.components.safety.rank",
    tierField: "rip.financialRip.components.safety.tier",
    scoreFormat: "decimal",
    description: "Safety score emphasizes protection from downside and loss mitigation.",
  },
  desirability: {
    id: "desirability",
    label: "Set Desirability",
    title: "Most Desirable Sets",
    subtitle: "Sets ranked by the popularity and depth of the Pokémon subjects they contain, independent of price.",
    tooltip: "Set Desirability measures the popularity and depth of the Pokémon subjects represented in a set. It does not use card prices or predict future value.",
    scoreLabel: "SET DESIRABILITY",
    tierLabel: "TIER",
    // The authoritative score, and its ALL-SET rank (of 135) rather than the
    // 21-set simulated cohort rank the retired CA7 lens quoted. CA7 needs a
    // pull model; this does not, so this lens covers every scored set.
    scoreField: "universalSetDesirability.score",
    rankField: "universalSetDesirability.rank",
    tierField: null,
    scoreFormat: "decimal",
    description: "Set Desirability measures how popular and deep a set's Pokémon roster is, independent of price.",
  },
  stability: {
    id: "stability",
    label: "Most Consistent",
    title: "Most Consistent Sets",
    subtitle: "Sets ranked by how steady their opening profile is across many simulated packs.",
    tooltip: "Sets ranked by how steady their opening profile is across many simulated packs.",
    scoreLabel: "STABILITY SCORE",
    tierLabel: "STABILITY TIER",
    scoreField: "rip.financialRip.components.stability.score",
    rankField: "rip.financialRip.components.stability.rank",
    tierField: "rip.financialRip.components.stability.tier",
    scoreFormat: "decimal",
    description: "Stability score measures consistency and predictability of outcomes.",
  },
  experience: {
    id: "experience",
    label: "Opening Experience",
    title: "Best Opening Experience",
    subtitle: "Sets ranked by how often the pack feels good to open, not just the highest ceiling.",
    tooltip: "Sets ranked by how often the pack feels good to open, not just the highest ceiling.",
    scoreLabel: "EXPERIENCE",
    tierLabel: "TIER",
    scoreField: "relative_experience_score",
    rankField: "experience_rank",
    tierField: "experience_tier",
    scoreFormat: "decimal",
    description: "Experience score measures how consistently satisfying a pack opening feels.",
  },
  chase: {
    id: "chase",
    label: "Chase Potential",
    title: "Best Chase Potential",
    subtitle: "Sets ranked by how strong the chase-card opportunity is compared with the cost to open.",
    tooltip: "Sets ranked by how strong the chase-card opportunity is compared with the cost to open.",
    scoreLabel: "CHASE SCORE",
    tierLabel: "TIER",
    scoreField: "relative_chase_potential_score",
    rankField: "chase_potential_rank",
    tierField: "chase_potential_tier",
    scoreFormat: "decimal",
    description: "Chase score measures the opportunity for landing high-value target cards.",
  },
  averageReturn: {
    id: "averageReturn",
    label: "Best Expected Value",
    title: "Best Expected Value",
    subtitle: "Sets ranked by mean simulated pack value compared against pack cost.",
    tooltip: "Sets ranked by mean simulated pack value compared against pack cost.",
    scoreLabel: "EV VS COST",
    tierLabel: "TIER",
    scoreField: "mean_value_to_cost_ratio",
    rankField: "mean_value_to_cost_rank",
    tierField: "mean_value_to_cost_tier",
    scoreFormat: "ratio",
    description: "Expected Value vs Cost shows the mean value-to-cost ratio across all simulated packs.",
  },
  upside: {
    id: "upside",
    label: "Biggest Upside",
    title: "Biggest Upside",
    subtitle: "Sets ranked by blended ceiling quality using Big Hit Upside (P95) and God Pull Upside (P99).",
    tooltip: "Sets ranked by blended ceiling quality using Big Hit Upside (P95) and God Pull Upside (P99). This is separate from either individual upside metric.",
    scoreLabel: "BIGGEST UPSIDE",
    tierLabel: "TIER",
    scoreField: "relative_biggest_upside_score",
    rankField: "biggest_upside_rank",
    tierField: "biggest_upside_tier",
    scoreFormat: "decimal",
    description: "Biggest Upside blends P95 and P99 value-to-cost ratios so broad high-end strength matters more than a single extreme spike.",
  },
  godPullUpside: {
    id: "godPullUpside",
    label: "God Pull Upside",
    title: "God Pull Upside",
    subtitle: "Ranks sets by the P99 simulated outcome compared with pack cost.",
    tooltip: "Ranks sets by the 99th percentile simulated outcome compared with pack cost. This represents rare tail upside, not a likely pack result.",
    scoreLabel: "GOD PULL UPSIDE",
    tierLabel: "TIER",
    scoreField: "p99_value_to_cost_ratio",
    rankField: "p99_value_to_cost_rank",
    tierField: "p99_value_to_cost_tier",
    scoreFormat: "ratio",
    description: "God Pull Upside isolates the P99 outcome vs pack cost to focus on rare tail upside.",
  },
};

export function getModeConfig(modeId) {
  return EXPLORE_RANKING_MODES[modeId] || EXPLORE_RANKING_MODES.overall;
}

export function getScoreField(modeId) {
  return getModeConfig(modeId).scoreField;
}

export function getRankField(modeId) {
  return getModeConfig(modeId).rankField;
}

export function getTierField(modeId) {
  return getModeConfig(modeId).tierField || "rip.tier";
}

export function getScoreForMode(target, modeId) {
  return toNumber(getFieldValue(target, getScoreField(modeId)));
}

export function getRankForMode(target, modeId) {
  const field = getRankField(modeId);
  if (!field) {
    return null;
  }
  return toNumber(getFieldValue(target, field));
}

export function getTierForMode(target, modeId) {
  const value = getFieldValue(target, getTierField(modeId));
  return value === null || value === undefined ? null : String(value);
}

export function formatModeScore(value, format = "decimal") {
  const num = toNumber(value);
  if (num === null) {
    return "—";
  }

  if (format === "ratio") {
    return `${num.toFixed(1)}x`;
  }

  return num.toFixed(1);
}
