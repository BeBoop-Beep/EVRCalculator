// Which set the landing hero's Live Set Intelligence panel shows, and the small
// ranked strip beneath the hero.
//
// Current public Set Benchmark Overall is the Homepage ranking authority.
// Canonical rank determines order; rounded score never breaks rank ties and
// legacy Set RIP fields are not accepted as fallbacks.
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
 * The current public Set Benchmark Overall headline. Read straight through —
 * never derived or backfilled from legacy Set RIP. A set is usable only when
 * the backend publishes an available score and positive canonical rank.
 */
function readBenchmarkOverall(target) {
  const block = target?.benchmarkOverall;
  if (!block || typeof block !== "object") {
    return { available: false, score: null, rank: null, cohortSize: null, position: null };
  }
  const rank = toOptionalPositiveInt(block.rank);
  const score = block.status === "available" ? toOptionalNumber(block.score) : null;
  const rankable = rank !== null && score !== null;
  return {
    available: rankable,
    score,
    rank,
    cohortSize: toOptionalNumber(block.cohortSize),
    position: score > 5 ? "Above Pokémon benchmark" : score < 5 ? "Below Pokémon benchmark" : "At Pokémon benchmark",
    sourceMarketDate: toOptionalString(block.sourceMarketDate),
  };
}

/**
 * A target -> spotlight entry, or null when current Benchmark Overall is not
 * available for it.
 */
function toEntry(target) {
  const benchmark = readBenchmarkOverall(target);
  if (!benchmark.available) {
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
    // Current public Set Benchmark Overall. Never legacy Set RIP or pack_rank.
    score: benchmark.score,
    scoreLabel: "RIP Score",
    benchmarkPosition: benchmark.position,
    benchmarkSourceMarketDate: benchmark.sourceMarketDate,
    rank: benchmark.rank,
    cohortSize: benchmark.cohortSize,
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
    // No Financial RIP internals or legacy distribution fields belong on the
    // public Homepage leaderboard; Benchmark Overall is its only authority.
    ...readDesirabilityFields(target),
    href: buildRipLink(target),
  };
}

/**
 * Canonical rank first; name only stabilizes malformed duplicate-rank rows.
 * Display score never participates in ordering.
 */
function byCanonicalRank(left, right) {
  if (left.rank !== null && right.rank !== null && left.rank !== right.rank) {
    return left.rank - right.rank;
  }
  if (left.rank !== null && right.rank === null) return -1;
  if (left.rank === null && right.rank !== null) return 1;

  return left.name.localeCompare(right.name);
}

export function selectLandingHeroEntries(targets) {
  const list = Array.isArray(targets) ? targets : [];
  return list.map(toEntry).filter(Boolean).sort(byCanonicalRank);
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
