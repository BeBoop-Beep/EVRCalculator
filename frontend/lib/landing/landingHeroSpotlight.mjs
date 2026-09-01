// Which set the landing hero's Live Set Intelligence panel shows, and the small
// ranked strip beneath the hero.
//
// PUBLIC SET RIP (setRipV1) IS THE HOMEPAGE'S RANKING AUTHORITY. The homepage
// is a public marketing surface: its #1/#2/#3 must be identical for anonymous,
// Base, Plus and Premium visitors, so it cannot be gated on Overall RIP (which
// is not published to anonymous/Base callers). setRipV1 IS published to every
// plan tier (see backend index_plan_access._project_public_set_leaderboard_target),
// so it is the only metric that can decide set-level homepage ranking without
// login state changing the answer. A set with no rankable setRipV1 is skipped —
// this file never substitutes Overall RIP, Financial RIP, or the legacy
// `pack_rank` field to invent a ranking setRipV1 doesn't have.
//
// Dependency-free (no score-reader import) so landingHeroSpotlight.test.mjs can
// run it directly under `node --test` / `tsx --test`, which cannot resolve the
// "@/" specifiers the Next bundler uses.

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toOptionalString(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

/**
 * The canonical checklist set value the Explore targets endpoint already
 * publishes. Null when the set has no priced checklist row — the panel drops
 * the Set Value line rather than showing a zero.
 */
function readSetValue(target) {
  return (
    toOptionalNumber(target?.checklistSetValue) ??
    toOptionalNumber(target?.checklist_set_value) ??
    toOptionalNumber(target?.currentChecklistSetValue) ??
    toOptionalNumber(target?.current_checklist_set_value)
  );
}

/**
 * The 7-day set value comparison the Explore Top Rankings ladder already
 * reads. Kept as three separate fields rather than a derived delta so the
 * caller can tell "no change" from "no comparable snapshot" — the landing
 * previews render those two states differently and neither may become a zero.
 */
function readPreviousSetValue7d(target) {
  return (
    toOptionalNumber(target?.previousChecklistSetValue7d) ??
    toOptionalNumber(target?.previous_checklist_set_value_7d)
  );
}

function readSetValueStatus7d(target) {
  return (
    toOptionalString(target?.setValueComparisonStatus7d) ??
    toOptionalString(target?.set_value_comparison_status_7d)
  );
}

/**
 * The published set-level desirability figures, read straight through.
 *
 * `universalSetDesirability` is the authoritative Set Desirability lens Explore
 * ships; `collector_appeal_score` is the published Collector Appeal score.
 * Neither is a substitute for the other, and neither substitutes for the
 * canonical RIP Score. `desirability_is_fallback` is carried alongside them because a
 * substituted desirability must not be treated as a measured one — see
 * readDesirability in landingSpotlights.mjs, which does the trusting.
 */
function readDesirabilityFields(target) {
  return {
    universalDesirabilityScore: toOptionalNumber(target?.universalSetDesirability?.score),
    universalDesirabilityRank: toOptionalNumber(target?.universalSetDesirability?.rank),
    collectorAppealScore:
      toOptionalNumber(target?.collector_appeal_score) ?? toOptionalNumber(target?.collectorAppealScore),
    desirabilityIsFallback:
      target?.desirability_is_fallback === true || target?.desirabilityIsFallback === true,
  };
}

/**
 * The published opening economics for one pack of this set: what a pack costs,
 * the modeled mean value the simulation returns, and the modeled probability an
 * opening lands above cost. These are the SAME three fields the Explore table
 * publishes (`pack_cost`, `mean_value`, `prob_profit`) — read, never derived.
 */
function readOpeningEconomics(target) {
  return {
    packCost: toOptionalNumber(target?.pack_cost) ?? toOptionalNumber(target?.packCost),
    meanValue: toOptionalNumber(target?.mean_value) ?? toOptionalNumber(target?.meanValue),
    medianValue: toOptionalNumber(target?.median_value) ?? toOptionalNumber(target?.medianValue),
    probProfit: toOptionalNumber(target?.prob_profit) ?? toOptionalNumber(target?.probProfit),
    expectedLossPerPack:
      toOptionalNumber(target?.expected_loss_per_pack) ?? toOptionalNumber(target?.expectedLossPerPack),
  };
}

function buildRipLink(target) {
  const targetType = toOptionalString(target?.target_type);
  const targetId = toOptionalString(target?.target_id);
  if (!targetType || !targetId) {
    return "/Explore/rip-statistics";
  }
  return `/Explore/rip-statistics?target_type=${encodeURIComponent(targetType)}&target_id=${encodeURIComponent(targetId)}`;
}

function toOptionalPositiveInt(value) {
  const parsed = toOptionalNumber(value);
  return parsed !== null && Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

/**
 * The public Set RIP V1 block: score, rank, tier, cohortSize. Read straight
 * through — never derived, never backfilled from Overall RIP. A set is
 * "rankable" only when the backend actually published a positive integer
 * rank; an unrankable/missing block returns nulls, and the caller drops the
 * entry rather than inventing a rank from another metric.
 */
function readSetRipV1(target) {
  const block = target?.setRipV1;
  if (!block || typeof block !== "object") {
    return { available: false, score: null, rank: null, tier: null, cohortSize: null };
  }
  const rank = toOptionalPositiveInt(block.rank);
  const rankable = block.rankable !== false && rank !== null;
  return {
    available: rankable,
    score: toOptionalNumber(block.score),
    rank,
    tier: toOptionalString(block.tier),
    cohortSize: toOptionalNumber(block.cohortSize),
  };
}

/**
 * A target -> spotlight entry, or null when the public Set RIP V1 rank is not
 * available for it.
 */
function toEntry(target) {
  const setRip = readSetRipV1(target);
  if (!setRip.available) {
    return null;
  }

  const economics = readOpeningEconomics(target);

  return {
    key: `${toOptionalString(target?.target_type) || "set"}:${toOptionalString(target?.target_id) || ""}`,
    targetType: toOptionalString(target?.target_type),
    targetId: toOptionalString(target?.target_id),
    canonicalKey:
      toOptionalString(target?.canonical_key) ?? toOptionalString(target?.canonicalKey) ??
      toOptionalString(target?.slug),
    name: toOptionalString(target?.name) || toOptionalString(target?.target_id) || "Unknown set",
    era: toOptionalString(target?.era),
    heroImageUrl: toOptionalString(target?.hero_image_url) ?? toOptionalString(target?.heroImageUrl),
    logoUrl: toOptionalString(target?.logo_image_url),
    symbolUrl: toOptionalString(target?.symbol_image_url),
    // THE public Set RIP V1 score — the same set-level ranking authority the
    // Rankings "sets" lens uses. Never Overall RIP, never a legacy pack_rank.
    score: setRip.score,
    scoreLabel: "Set RIP",
    tier: setRip.tier,
    rank: setRip.rank,
    cohortSize: setRip.cohortSize,
    setValue: readSetValue(target),
    setValueAsOf:
      toOptionalString(target?.currentChecklistSetValueDate) ??
      toOptionalString(target?.current_checklist_set_value_date) ??
      toOptionalString(target?.checklistSetValueAsOf) ??
      toOptionalString(target?.checklist_set_value_as_of),
    previousSetValue7d: readPreviousSetValue7d(target),
    setValueStatus7d: readSetValueStatus7d(target),
    packCost: economics.packCost,
    meanValue: economics.meanValue,
    medianValue: economics.medianValue,
    probProfit: economics.probProfit,
    expectedLossPerPack: economics.expectedLossPerPack,
    // NO INTERPRETATION COPY, and no Financial RIP internals read here. This
    // entry's only ranking authority is setRipV1 (see readSetRipV1 above) —
    // `hasCanonicalOverallRipV7` and the old p05/p95/p99/max distribution
    // fields (sourced from Financial RIP's paid internals) do not belong on
    // the public homepage set leaderboard and are not read.
    ...readDesirabilityFields(target),
    href: buildRipLink(target),
  };
}

/**
 * Best rank first; a missing rank sorts behind every ranked set. Score then
 * name break ties so the spotlight is stable between requests.
 */
function byRankThenScore(left, right) {
  if (left.rank !== null && right.rank !== null && left.rank !== right.rank) {
    return left.rank - right.rank;
  }
  if (left.rank !== null && right.rank === null) return -1;
  if (left.rank === null && right.rank !== null) return 1;

  const leftScore = left.score ?? -Infinity;
  const rightScore = right.score ?? -Infinity;
  if (leftScore !== rightScore) {
    return rightScore - leftScore;
  }
  return left.name.localeCompare(right.name);
}

export function selectLandingHeroEntries(targets) {
  const list = Array.isArray(targets) ? targets : [];
  return list.map(toEntry).filter(Boolean).sort(byRankThenScore);
}

/**
 * The single set the hero panel features: the top-ranked set in the public
 * cohort. Null when no set has a canonical RIP Score, which the panel renders
 * as an unavailable state rather than substituting a number.
 */
export function selectLandingHeroSpotlight(targets) {
  return selectLandingHeroEntries(targets)[0] || null;
}

/**
 * The ranked strip under the hero. Reads the SAME already-fetched targets as
 * the spotlight — no second request — and excludes the spotlight so the strip
 * continues the ranking instead of repeating its first row.
 */
export function selectLandingRankedStrip(targets, limit = 4) {
  const entries = selectLandingHeroEntries(targets);
  const size = Number.isFinite(limit) && limit > 0 ? Math.floor(limit) : 4;
  return entries.slice(1, 1 + size);
}
