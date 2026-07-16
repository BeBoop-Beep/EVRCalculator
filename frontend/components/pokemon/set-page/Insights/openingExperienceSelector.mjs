// Pure selectors for the Opening Experience section and the Collector Appeal
// impact strip.
//
// These read the backend's canonical contract and shape it for display. They
// never compute a score, renormalize a weight, rank a row, or fall back to a
// legacy field: a missing contract yields status "unavailable" and the section
// renders that state. CA7, Chase Appeal, Dual-Path Depth and every rank/tier
// are backend-owned (see backend/db/services/collector_appeal_service.py and
// explore_rip_statistics_service.py).

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

export function selectOpeningExperiencePresentation(openingExperience) {
  const opening = toObject(openingExperience);
  const collectorAppeal = toObject(opening.collectorAppeal);
  const rosterDesirability = toObject(opening.rosterDesirability);
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
    rosterDesirability: {
      score: toNumber(rosterDesirability.score),
      scoreLabel: formatScore(rosterDesirability.score),
      rank: toNumber(rosterDesirability.rank),
      rankLabel: formatRank(rosterDesirability.rank, rosterDesirability.cohortSize ?? cohort.eligibleSetCount),
      tier: rosterDesirability.tier ?? null,
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

export function selectCollectorAppealImpact(rip, ripCore) {
  const safeRip = toObject(rip);
  const safeCore = toObject(ripCore);
  const component = toObject(toObject(safeRip.components).desirability);

  const finalScore = toNumber(safeRip.score);
  const coreScore = toNumber(safeCore.score);
  if (finalScore === null && coreScore === null) return null;

  const finalRank = toNumber(safeRip.rank);
  const coreRank = toNumber(safeCore.rank);
  const rankEffect = finalRank !== null && coreRank !== null ? coreRank - finalRank : null;

  return {
    ripCore: {
      scoreLabel: formatScore(coreScore),
      rankLabel: formatRank(coreRank, safeCore.cohortSize),
    },
    collectorAppeal: {
      scoreLabel: formatScore(component.score),
      rankLabel: formatRank(component.rank, component.cohortSize),
    },
    weightLabel:
      toNumber(component.weight) === null ? null : `${Math.round(toNumber(component.weight) * 100)}%`,
    // The DIRECT weighted contribution from the backend component payload —
    // NOT `rip.score - ripCore.score`, which misstates it because RIP Core's
    // financial weights are renormalized.
    contributionLabel:
      toNumber(component.contribution) === null
        ? null
        : `${toNumber(component.contribution).toFixed(1)} pts`,
    finalRip: {
      scoreLabel: formatScore(finalScore),
      rankLabel: formatRank(finalRank, safeRip.cohortSize),
    },
    rankEffect,
    rankEffectLabel:
      rankEffect === null
        ? null
        : rankEffect > 0
        ? `+${rankEffect} vs RIP Core`
        : rankEffect < 0
        ? `${rankEffect} vs RIP Core`
        : "No rank change vs RIP Core",
  };
}
