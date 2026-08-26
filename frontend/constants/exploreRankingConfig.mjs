/**
 * Configuration for Explore page ranking mode dropdown.
 *
 * The two CANONICAL product modes read the current models:
 *   - `overall` ("RIP SCORE")   -> `overallRipV8` — the canonical Overall RIP.
 *   - `financial` ("FINANCIAL RIP") -> `financialRipV3` — the canonical
 *     Financial RIP.
 * Both previously read superseded objects under those exact public names:
 * `overall` read `rip` (Overall RIP **v4** = 90% RIP Core + 10% legacy CA7) and
 * `financial` read `ripCore` (Financial RIP **V2**, the 60/25/15
 * Profit/Safety/Stability blend). Neither may be read under a canonical label
 * again, and there is no fallback to them: a target without a V7/V3 score sorts
 * as unscored rather than borrowing a legacy number.
 *
 * The remaining modes are named RANKING LENSES, not presentations of the
 * canonical models. `profit`/`safety`/`stability` are the legacy V2 pillar
 * lenses and stay labelled as their own metrics — they are NOT presented as the
 * components of Financial RIP, which has its own six V3 components on the set
 * page. The desirability lens reads `universalSetDesirability`, the
 * authoritative simulation-independent score (all-set rank of 135).
 *
 * Fields are dot-paths resolved by getFieldValue. The legacy relative/pack
 * score fields are a cohort min-max presentation over the old 33-set population
 * and must not power public ranking again.
 *
 * EVERY MODE DECLARES WHAT KIND OF NUMBER ITS COLUMN HOLDS
 * --------------------------------------------------------
 * `scoreKind` is required on every mode and is the thing that stops one generic
 * "score" column from silently changing meaning between modes:
 *
 *   "publicScore" — the canonical leader-anchored 0-100 public score of a
 *                   canonical RIP-family metric. Rendered as `NN.N` with a
 *                   `/100` suffix. Only RIP Score and Financial RIP use this.
 *   "index"       — some other backend 0-100 index that is NOT one of the three
 *                   canonical public metrics. Rendered as `NN.N`, no `/100`.
 *   "ratio"       — a value-to-cost multiple. Rendered as `N.Nx`.
 *
 * Previously every mode published an `absoluteScoreField` and an optional
 * `relativeScoreField`, and the table rendered the relative one when it existed
 * and silently fell back to the absolute one when it did not — in the same
 * visual slot, with the same formatting. A reader could not tell that the
 * "score" in the Financial column and the "score" in the Profit column were
 * measured on different scales. `scoreKind` makes that impossible: the renderer
 * formats and labels by kind, and a `publicScore` mode has exactly one field.
 *
 * `publicScoreField` on a `publicScore` mode is the ONLY score field it has.
 * The fixed-anchor model score is deliberately not exposed here: it is not a
 * public number, and a config that offers it invites a surface to render it.
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

export const SCORE_KIND_PUBLIC = "publicScore";
export const SCORE_KIND_INDEX = "index";
export const SCORE_KIND_RATIO = "ratio";

export const EXPLORE_RANKING_MODES = {
  overall: {
    id: "overall",
    label: "Best Overall",
    title: "Best Sets to Rip Right Now",
    subtitle: "Sets ranked by the strongest overall opening profile.",
    tooltip: "Sets ranked by the strongest overall opening profile.",
    scoreLabel: "OVERALL RIP",
    tierLabel: "TIER",
    scoreKind: SCORE_KIND_PUBLIC,
    // The ONE canonical public RIP Score field. There is deliberately no
    // absolute/model field here: it is not a public number.
    publicScoreField: "overallRipV10.leaderNormalizedScore",
    rankField: "overallRipV10.rank",
    rankedSetCountField: "overallRipV10.cohortSize",
    tierField: "overallRipV10.tier",
    description: "Overall RIP combines financial opening performance with collector appeal.",
  },
  financial: {
    id: "financial",
    label: "Financial RIP",
    title: "Strongest Financial Opening",
    subtitle: "Sets ranked by the monetary side of opening alone, without collector appeal.",
    tooltip: "Financial RIP measures monetary pack outcomes against pack cost. It excludes collector appeal.",
    scoreLabel: "FINANCIAL RIP",
    tierLabel: "TIER",
    scoreKind: SCORE_KIND_PUBLIC,
    publicScoreField: "financialRipV4.leaderNormalizedScore",
    rankField: "financialRipV4.rank",
    rankedSetCountField: "financialRipV4.cohortSize",
    tierField: "financialRipV4.tier",
    description: "Financial RIP is the financial-only opening quality, built from the simulated pack-value distribution and the pack price.",
  },
  // RETIRED: `profit`, `safety`, `stability`.
  //
  // All three read `rip.financialRip.components.*` — the pillars of Financial
  // RIP **V2**, the retired 60/25/15 model. Keeping them as public ranking
  // lenses meant the site could not stop publishing a superseded financial
  // model, and it made "score" mean a V2 pillar in one column and a canonical
  // V3 public score in another. They are removed rather than reimplemented:
  // Financial RIP V3 has its own six components, presented on the set page,
  // and replacing three lenses with six new modes is a separate product pass.
  //
  // Nothing about V2 scoring changed. `rip` / `ripCore` are still computed and
  // still published for audit and rollback; they simply no longer power a
  // public ranking.
  desirability: {
    id: "desirability",
    label: "Set Desirability",
    title: "Most Desirable Sets",
    subtitle: "Sets ranked by the popularity and depth of the Pokémon subjects they contain, independent of price.",
    tooltip: "Set Desirability measures the popularity and depth of the Pokémon subjects represented in a set. It does not use card prices or predict future value. It is a separate metric from Collector Appeal and is ranked against every scored set, not against the opening cohort.",
    scoreLabel: "SET DESIRABILITY",
    tierLabel: "TIER",
    // A 0-100 index in its own right, NOT one of the three canonical public
    // RIP metrics — so it does not take the `/100` public-score treatment, and
    // its rank is quoted against its OWN all-set denominator rather than the
    // opening cohort's.
    scoreKind: SCORE_KIND_INDEX,
    scoreField: "universalSetDesirability.score",
    rankField: "universalSetDesirability.rank",
    rankedSetCountField: "universalSetDesirability.rankedSetCount",
    tierField: null,
    description: "Set Desirability measures how popular and deep a set's Pokémon roster is, independent of price. It is not Collector Appeal.",
  },
  experience: {
    id: "experience",
    label: "Opening Experience",
    title: "Best Opening Experience",
    subtitle: "Sets ranked by how often the pack feels good to open, not just the highest ceiling.",
    tooltip: "Sets ranked by how often the pack feels good to open, not just the highest ceiling.",
    scoreLabel: "EXPERIENCE",
    tierLabel: "TIER",
    scoreKind: SCORE_KIND_INDEX,
    scoreField: "relative_experience_score",
    rankField: "experience_rank",
    tierField: "experience_tier",
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
    scoreKind: SCORE_KIND_INDEX,
    scoreField: "relative_chase_potential_score",
    rankField: "chase_potential_rank",
    tierField: "chase_potential_tier",
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
    scoreKind: SCORE_KIND_RATIO,
    scoreField: "mean_value_to_cost_ratio",
    rankField: "mean_value_to_cost_rank",
    tierField: "mean_value_to_cost_tier",
    description: "Expected Value vs Cost shows the mean value-to-cost ratio across all simulated packs.",
  },
  upside: {
    id: "upside",
    label: "Biggest Upside",
    title: "Biggest Upside",
    subtitle: "Sets ranked by blended ceiling quality using both the P95 and the top-1% thresholds.",
    tooltip: "Sets ranked by blended ceiling quality using both the P95 and the top-1% thresholds. This is a blend and is separate from Strong Upside and from Jackpot Upside, each of which is a single threshold value.",
    scoreLabel: "BIGGEST UPSIDE",
    tierLabel: "TIER",
    scoreKind: SCORE_KIND_INDEX,
    scoreField: "relative_biggest_upside_score",
    rankField: "biggest_upside_rank",
    tierField: "biggest_upside_tier",
    description: "Biggest Upside blends the P95 and top-1% value-to-cost ratios so broad high-end strength matters more than a single extreme spike.",
  },
  jackpotUpside: {
    id: "jackpotUpside",
    label: "Jackpot Upside",
    title: "Jackpot Upside",
    subtitle: "Ranks sets by the top-1% simulated outcome compared with pack cost.",
    tooltip: "Ranks sets by the top-1% (99th percentile) simulated outcome compared with pack cost. This represents rare tail upside, not a likely pack result.",
    // Was "GOD PULL UPSIDE", which is a third name for a metric the locked
    // vocabulary calls Jackpot Upside. The mode id moved with it.
    scoreLabel: "JACKPOT UPSIDE",
    tierLabel: "TIER",
    scoreKind: SCORE_KIND_RATIO,
    scoreField: "p99_value_to_cost_ratio",
    rankField: "p99_value_to_cost_rank",
    tierField: "p99_value_to_cost_tier",
    description: "Jackpot Upside ranks the top-1% threshold relative to pack cost to focus on rare tail upside.",
  },
};

export function getModeConfig(modeId) {
  return EXPLORE_RANKING_MODES[modeId] || EXPLORE_RANKING_MODES.overall;
}

export function getScoreKind(modeId) {
  return getModeConfig(modeId).scoreKind || SCORE_KIND_INDEX;
}

export function isPublicScoreMode(modeId) {
  return getScoreKind(modeId) === SCORE_KIND_PUBLIC;
}

/**
 * The one score field for a mode, whatever kind it is.
 *
 * A `publicScore` mode reads `publicScoreField`; every other mode reads
 * `scoreField`. There is exactly one field per mode either way, so no caller
 * can pick between an absolute and a relative reading of the same column.
 */
export function getScoreField(modeId) {
  const config = getModeConfig(modeId);
  return config.publicScoreField || config.scoreField || null;
}

export function getRankField(modeId) {
  return getModeConfig(modeId).rankField;
}

export function getTierField(modeId) {
  return getModeConfig(modeId).tierField || "overallRipV10.tier";
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

export function getRankedSetCountField(modeId) {
  return getModeConfig(modeId).rankedSetCountField || null;
}

export function getRankedSetCountForMode(target, modeId) {
  const field = getRankedSetCountField(modeId);
  if (!field) {
    return null;
  }
  return toNumber(getFieldValue(target, field));
}

export function getTierForMode(target, modeId) {
  const value = getFieldValue(target, getTierField(modeId));
  return value === null || value === undefined ? null : String(value);
}

/**
 * Format a mode's score BY ITS DECLARED KIND, never by a caller's guess.
 *
 * A ratio prints as `1.4x`; a public score and a plain index both print to one
 * decimal. The `/100` suffix is NOT added here — it is a separate element in the
 * cell so it can be styled and so only a `publicScore` mode ever receives one.
 */
export function formatPublicRipScore(value) {
  const display = publicRipDisplayScore(value);
  return display === null ? "—" : display.toFixed(1);
}

export function publicRipDisplayScore(value) {
  const num = toNumber(value);
  return num === null ? null : Math.floor(num + 0.5) / 10;
}

export function formatModeScore(value, scoreKind = SCORE_KIND_INDEX) {
  const num = toNumber(value);
  if (num === null) {
    return "—";
  }

  if (scoreKind === SCORE_KIND_RATIO) {
    return `${num.toFixed(1)}x`;
  }

  if (scoreKind === SCORE_KIND_PUBLIC) {
    return formatPublicRipScore(num);
  }

  return num.toFixed(1);
}

export function formatScoreForMode(target, modeId) {
  return formatModeScore(getScoreForMode(target, modeId), getScoreKind(modeId));
}
