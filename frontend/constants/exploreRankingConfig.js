/**
 * Configuration for Explore page ranking mode dropdown.
 * Public Explore score modes must use relative score fields only.
 */

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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
    scoreField: "relative_pack_score",
    rankField: "pack_rank",
    tierField: "pack_tier",
    scoreFormat: "decimal",
    description: "Overall RIP score combines all factors for a comprehensive ranking.",
  },
  profit: {
    id: "profit",
    label: "Most Profitable",
    title: "Most Profitable Sets",
    subtitle: "Sets ranked by their profit profile, including chance to beat cost, average return, and upside.",
    tooltip: "Sets ranked by their profit profile, including chance to beat cost, average return, and upside.",
    scoreLabel: "PROFIT SCORE",
    tierLabel: "PROFIT TIER",
    scoreField: "relative_profit_score",
    rankField: "profit_rank",
    tierField: "profit_tier",
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
    scoreField: "relative_safety_score",
    rankField: "safety_rank",
    tierField: "safety_tier",
    scoreFormat: "decimal",
    description: "Safety score emphasizes protection from downside and loss mitigation.",
  },
  desirability: {
    id: "desirability",
    label: "Desirability",
    title: "Most Desirable Sets",
    subtitle: "Sets ranked by collector appeal based on featured Pokemon and hit-card desirability.",
    tooltip: "Collector appeal based on featured Pokemon and hit-card desirability, independent of market price.",
    scoreLabel: "DESIRABILITY",
    tierLabel: "DESIRABILITY TIER",
    scoreField: "relative_desirability_score",
    rankField: "desirability_rank",
    tierField: "desirability_tier",
    scoreFormat: "decimal",
    description: "Collector appeal based on featured Pokemon and hit-card desirability, independent of market price.",
  },
  stability: {
    id: "stability",
    label: "Most Consistent",
    title: "Most Consistent Sets",
    subtitle: "Sets ranked by how steady their opening profile is across many simulated packs.",
    tooltip: "Sets ranked by how steady their opening profile is across many simulated packs.",
    scoreLabel: "STABILITY SCORE",
    tierLabel: "STABILITY TIER",
    scoreField: "relative_stability_score",
    rankField: "stability_rank",
    tierField: "stability_tier",
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
    label: "Best Average Return",
    title: "Best Average Return",
    subtitle: "Sets ranked by average pack value compared against pack cost.",
    tooltip: "Sets ranked by average pack value compared against pack cost.",
    scoreLabel: "AVG RETURN",
    tierLabel: "TIER",
    scoreField: "mean_value_to_cost_ratio",
    rankField: "mean_value_to_cost_rank",
    tierField: "mean_value_to_cost_tier",
    scoreFormat: "ratio",
    description: "Average return shows the mean value-to-cost ratio across all simulated packs.",
  },
  upside: {
    id: "upside",
    label: "Biggest Upside",
    title: "Biggest Upside",
    subtitle: "Sets ranked by blended ceiling quality using Big Hit Upside (P95) and God Pull Upside (P99).",
    tooltip: "Sets ranked by blended ceiling quality using Big Hit Upside (P95) and God Pull Upside (P99).",
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
    subtitle: "Ranks sets by rare monster-hit upside compared with pack cost.",
    tooltip: "Ranks sets by rare monster-hit upside compared with pack cost.",
    scoreLabel: "GOD PULL UPSIDE",
    tierLabel: "TIER",
    scoreField: "p99_value_to_cost_ratio",
    rankField: "p99_value_to_cost_rank",
    tierField: "p99_value_to_cost_tier",
    scoreFormat: "ratio",
    description: "God Pull Upside isolates P99 outcome vs pack cost to focus purely on rare monster-hit ceiling.",
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
  return getModeConfig(modeId).tierField || "pack_tier";
}

export function getScoreForMode(target, modeId) {
  const field = getScoreField(modeId);
  return toNumber(target?.[field]);
}

export function getRankForMode(target, modeId) {
  const field = getRankField(modeId);
  if (!field) {
    return null;
  }
  return toNumber(target?.[field]);
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
