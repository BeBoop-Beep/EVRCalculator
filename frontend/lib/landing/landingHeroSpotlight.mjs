// Which set the landing hero's Live Set Intelligence panel shows, and the small
// ranked strip beneath the hero.
//
// CANONICAL CONTRACT ONLY. Both selectors read the backend's versioned `rip`
// object through selectRipHeroScoreMode — the same reader the RIP Statistics
// hero uses — so the marketing surface can never show a different number than
// the product surface for the same set. The legacy cohort min-max fields
// (`pack_score`, `relative_pack_score`, `pack_rank`) are deliberately NOT read:
// a landing page is the worst place to publish a superseded blend under the
// name "RIP Score". A set without a canonical score is skipped, not patched.
//
// Dependency-free apart from the score reader so landingHeroSpotlight.test.mjs
// can run it directly under `node --test` / `tsx --test`, which cannot resolve
// the "@/" specifiers the Next bundler uses.

import { selectRipHeroScoreMode } from "../../components/explore/ripHeroScoreMode.mjs";

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
 * The published opening economics for one pack of this set: what a pack costs,
 * the modeled mean value the simulation returns, and the modeled probability an
 * opening lands above cost. These are the SAME three fields the Explore table
 * publishes (`pack_cost`, `mean_value`, `prob_profit`) — read, never derived.
 */
function readOpeningEconomics(target) {
  return {
    packCost: toOptionalNumber(target?.pack_cost) ?? toOptionalNumber(target?.packCost),
    meanValue: toOptionalNumber(target?.mean_value) ?? toOptionalNumber(target?.meanValue),
    probProfit: toOptionalNumber(target?.prob_profit) ?? toOptionalNumber(target?.probProfit),
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

/**
 * A target -> spotlight entry, or null when the canonical RIP Score is not
 * available for it.
 */
function toEntry(target) {
  const hero = selectRipHeroScoreMode({ target });
  if (!hero.available) {
    return null;
  }

  const economics = readOpeningEconomics(target);

  return {
    key: `${toOptionalString(target?.target_type) || "set"}:${toOptionalString(target?.target_id) || ""}`,
    targetType: toOptionalString(target?.target_type),
    targetId: toOptionalString(target?.target_id),
    name: toOptionalString(target?.name) || toOptionalString(target?.target_id) || "Unknown set",
    era: toOptionalString(target?.era),
    logoUrl: toOptionalString(target?.logo_image_url),
    symbolUrl: toOptionalString(target?.symbol_image_url),
    score: hero.score,
    scoreLabel: hero.label,
    tier: toOptionalString(hero.tier),
    rank: toOptionalNumber(hero.rank),
    cohortSize: toOptionalNumber(hero.cohortSize),
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
    probProfit: economics.probProfit,
    // The backend's own one-line read on this set. `leaderboard_label` is the
    // short form the Explore table shows; the canonical recommendation header
    // is the long form it shortens. Severity drives tone only.
    decisionLabel:
      toOptionalString(target?.leaderboard_label) ??
      toOptionalString(target?.canonical_recommendation_header),
    decisionSeverity: toOptionalString(target?.recommendation_severity),
    interpretationLabel: toOptionalString(hero.interpretation?.label),
    interpretationSummary: toOptionalString(hero.interpretation?.summary),
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
