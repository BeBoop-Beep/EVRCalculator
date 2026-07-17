// Pure selectors for Set Desirability and the Simulation Opening Experience.
//
// These read the backend's canonical contract and shape it for display. They
// never compute a score, renormalize a weight, rank a row, or fall back to a
// legacy field: a missing contract yields status "unavailable" and the section
// renders that state. Every score, rank and tier is backend-owned (see
// backend/db/services/universal_set_desirability_service.py,
// collector_appeal_service.py and explore_rip_statistics_service.py).
//
// TWO AVAILABILITIES, NOT ONE
// ---------------------------
// Set Desirability (the universal score) needs no simulation, no pull model and
// no CA7. The Simulation Opening Experience needs all three. They were gated
// together on CA7, so a set whose pack model could not be read rendered
// "Collector Appeal isn't available" and hid its Set Desirability too - a score
// the backend had already computed and sent. They are separated here because
// they answer different questions and fail for different reasons.

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function toArrayOf(value) {
  return Array.isArray(value) ? value : [];
}

function formatScore(value) {
  const parsed = toNumber(value);
  return parsed === null ? null : parsed.toFixed(1);
}

function formatRank(rank, cohortSize) {
  const parsedRank = toNumber(rank);
  if (parsedRank === null) return null;
  const parsedCohort = toNumber(cohortSize);
  return parsedCohort === null
    ? `#${Math.round(parsedRank)}`
    : `#${Math.round(parsedRank)} of ${Math.round(parsedCohort)}`;
}

function formatOdds(value) {
  const parsed = toNumber(value);
  return parsed === null ? null : `1 in ${Math.round(parsed).toLocaleString("en-US")}`;
}

function selectPath(path) {
  const safe = toObject(path);
  if (!safe.canonicalCardId && !safe.cardName) return null;
  return {
    canonicalCardId: safe.canonicalCardId ?? null,
    cardName: safe.cardName ?? null,
    cardNumber: safe.cardNumber ?? null,
    rarity: safe.rarity ?? null,
    imageUrl: safe.imageUrl ?? null,
    modeledProbability: toNumber(safe.modeledProbability),
    impliedOddsLabel: formatOdds(safe.impliedOdds),
  };
}

function formatPercent(value, digits = 1) {
  const parsed = toNumber(value);
  return parsed === null ? null : `${parsed.toFixed(digits)}%`;
}

function formatShare(value) {
  const parsed = toNumber(value);
  return parsed === null ? null : `${(parsed * 100).toFixed(1)}%`;
}

export const SET_DESIRABILITY_EXPLANATION =
  "Set Desirability measures the popularity and depth of the Pokémon subjects represented in this set. It does not use card prices or predict future value.";

/**
 * Set Desirability, from the backend `universalSetDesirability` contract.
 *
 * Availability depends ONLY on this contract. It deliberately does not consult
 * simulationCoverage, CA7 or Financial RIP: the universal score is computed
 * from the checklist and subject demand, so none of those can make it wrong or
 * absent, and letting them gate it is what hid an already-computed score.
 */
export function selectSetDesirabilityPresentation(universalSetDesirability) {
  const universal = toObject(universalSetDesirability);
  const components = toObject(universal.components);
  const coverage = toObject(universal.coverage);
  const score = toNumber(universal.score);
  const available = score !== null && coverage.status === "full";

  const componentRow = (key, label) => {
    const value = toNumber(components[key]);
    return {
      key,
      label,
      score: value,
      scoreLabel: value === null ? null : value.toFixed(1),
    };
  };

  return {
    status: available ? "available" : "unavailable",
    available,
    unavailableReasons: toArrayOf(coverage.reasons),
    coverageStatus: coverage.status ?? null,
    explanation: SET_DESIRABILITY_EXPLANATION,
    score,
    scoreLabel: formatScore(score),
    rank: toNumber(universal.rank),
    rankedSetCount: toNumber(universal.rankedSetCount),
    rankLabel: formatRank(universal.rank, universal.rankedSetCount),
    percentile: toNumber(universal.percentile),
    percentileLabel: formatPercent(universal.percentile),
    version: universal.version ?? null,
    components: [
      componentRow("chase_subject_strength", "Chase Subject Strength"),
      componentRow("chase_subject_depth", "Chase Subject Depth"),
      componentRow("favorite_hit_coverage", "Favorite Hit Coverage"),
    ],
    componentWeights: toObject(universal.componentWeights),
    weightsLabel: universal.weightsLabel ?? null,
    effectiveSubjectCount: toNumber(universal.effectiveSubjectCount),
    effectiveSubjectCountLabel:
      toNumber(universal.effectiveSubjectCount) === null
        ? null
        : toNumber(universal.effectiveSubjectCount).toFixed(2),
    distinctEligibleSubjectCount: toNumber(universal.distinctEligibleSubjectCount),
    top1ShareLabel: formatShare(universal.top1Share),
    top3ShareLabel: formatShare(universal.top3Share),
    topSubjects: toArrayOf(universal.topSubjects)
      .map((subject) => {
        const safe = toObject(subject);
        if (!safe.subjectName) return null;
        const demand = toNumber(safe.subjectDemand);
        return {
          subjectName: safe.subjectName,
          subjectDemand: demand,
          subjectDemandLabel: demand === null ? null : demand.toFixed(1),
          cardCount: toNumber(safe.cardCount),
          representativeCardName: safe.representativeCardName ?? null,
          bestRarityBucket: safe.bestRarityBucket ?? null,
        };
      })
      .filter(Boolean),
  };
}

/**
 * The Simulation Opening Experience (CA7, Chase Appeal, Dual-Path Depth).
 *
 * This one MAY depend on CA7: every metric in it is derived from the pull
 * model, so without one there is genuinely nothing to show. Its unavailability
 * must never hide Set Desirability - see `selectSetDesirabilityPresentation`.
 */
export function selectOpeningExperiencePresentation(openingExperience) {
  const opening = toObject(openingExperience);
  const collectorAppeal = toObject(opening.collectorAppeal);
  const dualPathDepth = toObject(opening.dualPathDepth);
  const chaseAppeal = toObject(opening.chaseAppeal);
  const cohort = toObject(opening.cohort);
  const coverage = toObject(opening.coverage);

  const available = opening.status === "available" && toNumber(collectorAppeal.score) !== null;

  const subjects = toArrayOf(opening.topSubjects)
    .map((subject) => {
      const safe = toObject(subject);
      const accessiblePath = selectPath(safe.accessiblePath);
      const elitePath = selectPath(safe.elitePath);
      if (!safe.subjectName || (!accessiblePath && !elitePath)) return null;
      return {
        subjectName: safe.subjectName,
        demandShare: toNumber(safe.demandShare),
        accessiblePath,
        elitePath,
      };
    })
    .filter(Boolean);

  return {
    status: available ? "available" : "unavailable",
    available,
    unavailableReasons: toArrayOf(coverage.reasons),
    cohortSize: toNumber(cohort.eligibleSetCount),
    collectorAppeal: {
      score: toNumber(collectorAppeal.score),
      scoreLabel: formatScore(collectorAppeal.score),
      rank: toNumber(collectorAppeal.rank),
      rankLabel: formatRank(collectorAppeal.rank, collectorAppeal.cohortSize ?? cohort.eligibleSetCount),
      tier: collectorAppeal.tier ?? null,
      interpretation: collectorAppeal.interpretation ?? null,
    },
    dualPathDepth: {
      // P is a structural coverage measure on its raw scale. displayPercent is
      // backend-provided formatting of the same number — never a rescale, and
      // deliberately no tier (100 is not normally attainable).
      displayPercent: toNumber(dualPathDepth.displayPercent),
      displayLabel:
        toNumber(dualPathDepth.displayPercent) === null
          ? null
          : `${toNumber(dualPathDepth.displayPercent).toFixed(1)}%`,
      rank: toNumber(dualPathDepth.rank),
      rankLabel: formatRank(dualPathDepth.rank, dualPathDepth.cohortSize ?? cohort.eligibleSetCount),
      subjectsWithMultiplePaths: toNumber(dualPathDepth.subjectsWithMultiplePaths),
      modeledSubjectCount: toNumber(dualPathDepth.modeledSubjectCount),
    },
    chaseAppeal: {
      score: toNumber(chaseAppeal.score),
      scoreLabel: formatScore(chaseAppeal.score),
      rank: toNumber(chaseAppeal.rank),
      rankLabel: formatRank(chaseAppeal.rank, chaseAppeal.cohortSize ?? cohort.eligibleSetCount),
      tier: chaseAppeal.tier ?? null,
    },
    topSubjects: subjects,
  };
}

function signed(value, digits = 1) {
  const parsed = toNumber(value);
  if (parsed === null) return null;
  const rendered = parsed.toFixed(digits);
  return parsed > 0 ? `+${rendered}` : rendered;
}

/**
 * The Overall RIP breakdown: Financial RIP, Set Desirability, the adjustment,
 * and Overall RIP.
 *
 * Deliberately NOT a four-way weighted blend. Overall RIP is Financial RIP plus
 * a bounded additive adjustment, so presenting Set Desirability as a fourth
 * weighted pillar (which is what the retired "Collector Appeal 10%" card did)
 * would describe arithmetic the backend does not perform.
 *
 * The adjustment is read from the backend payload, never derived as
 * `rip.score - ripCore.score`: the two are clamped independently, so at the
 * 0/100 bounds subtraction silently disagrees with the real adjustment.
 */
export function selectRipDesirabilityBreakdown(rip, ripCore, universalSetDesirability) {
  const safeRip = toObject(rip);
  const safeCore = toObject(ripCore);
  const universal = toObject(universalSetDesirability);
  const adjustmentPayload = toObject(safeRip.desirabilityAdjustment);

  const overallScore = toNumber(safeRip.score);
  const financialScore = toNumber(safeCore.score ?? toObject(safeRip.financialRip).score);
  const desirabilityScore = toNumber(universal.score ?? safeRip.universalSetDesirabilityScore);
  if (overallScore === null && financialScore === null && desirabilityScore === null) return null;

  const adjustment = toNumber(adjustmentPayload.adjustment);
  return {
    financialRip: {
      score: financialScore,
      scoreLabel: formatScore(financialScore),
      rankLabel: formatRank(safeCore.rank, safeCore.cohortSize),
      tier: safeCore.tier ?? null,
      weightsLabel: "Profit 60% · Safety 25% · Stability 15%",
    },
    setDesirability: {
      score: desirabilityScore,
      scoreLabel: formatScore(desirabilityScore),
      rankLabel: formatRank(universal.rank, universal.rankedSetCount),
    },
    desirabilityAdjustment: {
      value: adjustment,
      label: adjustment === null ? null : `${signed(adjustment)} pts`,
      cap: toNumber(adjustmentPayload.cap),
      capLabel:
        toNumber(adjustmentPayload.cap) === null
          ? null
          : `capped at ±${toNumber(adjustmentPayload.cap).toFixed(0)}`,
      clamped: adjustmentPayload.clamped === true,
      rawValue: toNumber(adjustmentPayload.rawAdjustment),
      formula: adjustmentPayload.formula ?? null,
    },
    overallRip: {
      score: overallScore,
      scoreLabel: formatScore(overallScore),
      rankLabel: formatRank(safeRip.rank, safeRip.cohortSize),
      tier: safeRip.tier ?? null,
    },
    unavailableReason: overallScore === null ? safeRip.statusReason ?? null : null,
  };
}
