// Collector Appeal (D / F / P) and the canonical Overall RIP composition.
//
// WHAT THIS READS
// ---------------
// The canonical v6 objects only:
//
//   overallRipV6      -> 0.80 * Financial RIP V3 + 0.20 * Collector Appeal
//   collectorAppeal   -> D + 0.50 * (0.60F + 0.40P) * (1 - D)
//
// It accepts either the shaped `publicRipContractV6` block or the raw
// `overallRipV6` + `openingExperience` objects, because the Explore target and
// the set-page snapshot carry the same numbers in those two shapes. That is a
// SHAPE fallback within one model, not a fallback to a different model: there is
// deliberately no path here that reads legacy CA7, Overall RIP V5/v4, or
// Universal Set Desirability when the canonical values are missing.
//
// THE VOCABULARY RULE
// -------------------
// Desirable Outcome Frequency is NOT a financial statistic and must never be
// labelled as one. Forbidden labels, enforced by the contract tests:
//
//   "Hit Rate" (unqualified), "Win Frequency", "Profit Frequency",
//   "Chance to Beat Cost", or anything implying profit / break-even / cost
//   recovery.
//
// Its financial sibling is a different number:
//
//   True Win Frequency          = P(pack value >= pack cost)      [Financial RIP]
//   Desirable Outcome Frequency = P(pack has a desirable card)    [Collector Appeal]
//
// A desirable outcome may still be worth less than the pack price, and the copy
// says so wherever the number appears.
//
// NO SCORING IN JAVASCRIPT
// ------------------------
// Every score, weight, contribution, probability and rank is lifted from the
// backend payload. The only arithmetic is presentational unit conversion.

const UNAVAILABLE = null;

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return UNAVAILABLE;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : UNAVAILABLE;
}

function toObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

export function formatPercentFromUnit(value, { decimals = 1 } = {}) {
  const parsed = toOptionalNumber(value);
  if (parsed === UNAVAILABLE) return "—";
  return `${(parsed * 100).toFixed(decimals)}%`;
}

export function formatWeightPercent(value) {
  const parsed = toOptionalNumber(value);
  if (parsed === UNAVAILABLE) return "—";
  return `${Math.round(parsed * 100)}%`;
}

export function formatScore(value, { decimals = 1 } = {}) {
  const parsed = toOptionalNumber(value);
  if (parsed === UNAVAILABLE) return "—";
  return parsed.toFixed(decimals);
}

export function formatApproximateOdds(oneInN) {
  const parsed = toOptionalNumber(oneInN);
  if (parsed === UNAVAILABLE || parsed <= 0) return UNAVAILABLE;
  // "approximately", never a guarantee: these are modeled odds over a
  // distribution, not an entitlement to a card every N packs.
  return `approximately 1 in ${Math.round(parsed).toLocaleString()} packs`;
}

// The one sentence that keeps the two constructs apart wherever they appear
// together.
export const FINANCIAL_VS_COLLECTOR_NOTE =
  "Financial RIP measures monetary pack outcomes. Collector Appeal measures how desirable the modeled cards are and how often the pack can deliver them.";

export const DESIRABLE_OUTCOME_DISCLAIMER =
  "A desirable outcome can still be worth less than the pack price.";

/**
 * Resolve the canonical v6 blocks from whichever shape the caller has.
 */
function resolveSources({ publicRipContractV6, overallRipV6, openingExperience }) {
  const contract = toObject(publicRipContractV6);
  if (Object.keys(contract).length > 0) {
    return {
      overall: toObject(contract.overallRip),
      appeal: toObject(contract.collectorAppeal),
      appealComponents: toObject(toObject(contract.collectorAppeal).components),
      fromContract: true,
    };
  }
  const opening = toObject(openingExperience);
  const appeal = toObject(opening.collectorAppeal);
  return {
    overall: toObject(overallRipV6),
    appeal,
    appealComponents: {
      rosterDesirability: {
        score: toObject(opening.rosterDesirability).score,
        rawValue: toObject(appeal.inputs).rosterDesirability,
      },
      desirableOutcomeFrequency: toObject(opening.desirableOutcomeFrequency),
      dualPathDepth: toObject(opening.dualPathDepth),
    },
    fromContract: false,
  };
}

/**
 * The canonical Overall RIP composition: 80% Financial RIP V3 + 20% Collector Appeal.
 *
 * Both source scores and both contributions are returned so a reader can check
 * the arithmetic, which is the point of showing a composition at all.
 */
export function selectOverallRipComposition(sources = {}) {
  const { overall } = resolveSources(sources);
  const components = toObject(overall.components);
  const financial = toObject(components.financialRipV3);
  const appeal = toObject(components.collectorAppeal);

  const score = toOptionalNumber(overall.score);
  const rows = [
    {
      key: "financialRipV3",
      title: "Financial RIP",
      score: toOptionalNumber(financial.score),
      weight: toOptionalNumber(financial.weight),
      contribution: toOptionalNumber(financial.contribution),
      interpretation: "Monetary outcomes: what the pack is worth against what it costs.",
    },
    {
      key: "collectorAppeal",
      title: "Collector Appeal",
      score: toOptionalNumber(appeal.score),
      weight: toOptionalNumber(appeal.weight),
      contribution: toOptionalNumber(appeal.contribution),
      interpretation: "How desirable the modeled cards are, and how often the pack delivers one.",
    },
  ];

  return {
    available: score !== UNAVAILABLE,
    score,
    scoreLabel: formatScore(score),
    rank: toOptionalNumber(overall.rank),
    rankedSetCount: toOptionalNumber(overall.rankedSetCount ?? overall.cohortSize),
    tier: overall.tier ?? UNAVAILABLE,
    version: overall.version ?? UNAVAILABLE,
    rows,
    statusReason: overall.statusReason ?? UNAVAILABLE,
    missingInputs: Array.isArray(overall.missingInputs) ? overall.missingInputs : [],
    note: FINANCIAL_VS_COLLECTOR_NOTE,
  };
}

/**
 * The Collector Appeal breakdown: Roster Desirability, Desirable Outcome
 * Frequency, Dual-Path Depth.
 *
 * Trainer and artist desirability are NOT rendered as zero or as "not
 * desirable": they are not modeled yet, so they are omitted and the omission is
 * stated. Scoring an unmodeled subject type as zero would be a claim about
 * those cards that the model is not entitled to make.
 */
export function selectCollectorAppealBreakdown(sources = {}) {
  const { appeal, appealComponents } = resolveSources(sources);
  const roster = toObject(appealComponents.rosterDesirability);
  const frequency = toObject(appealComponents.desirableOutcomeFrequency);
  const dualPath = toObject(appealComponents.dualPathDepth);

  const score = toOptionalNumber(appeal.score);
  const frequencyRaw = toOptionalNumber(frequency.rawValue);

  const rows = [
    {
      key: "rosterDesirability",
      title: "Roster Desirability",
      // D is published 0-100; the other two are 0-1 shares. Each row carries its
      // own formatted value so the surface never rescales one into the other.
      value: formatScore(toOptionalNumber(roster.score)),
      available: toOptionalNumber(roster.score) !== UNAVAILABLE,
      interpretation:
        "How desirable the Pokémon roster is before pull difficulty is considered.",
      metrics: [],
    },
    {
      key: "desirableOutcomeFrequency",
      title: "Desirable Outcome Frequency",
      value: frequencyRaw === UNAVAILABLE ? "—" : formatPercentFromUnit(frequencyRaw),
      available: frequencyRaw !== UNAVAILABLE,
      interpretation:
        "How often the modeled pack can deliver at least one card tied to a currently desirable Pokémon.",
      disclaimer: DESIRABLE_OUTCOME_DISCLAIMER,
      isFinancialMetric: false,
      metrics: [
        {
          label: "Modeled probability",
          value: frequencyRaw === UNAVAILABLE ? "—" : formatPercentFromUnit(frequencyRaw, { decimals: 2 }),
        },
        {
          label: "Approximate odds",
          value: formatApproximateOdds(frequency.impliedOddsOneInN) || "—",
        },
        {
          label: "Eligible desirable cards",
          value:
            toOptionalNumber(frequency.eligibleCardCount) === UNAVAILABLE
              ? "—"
              : String(Math.round(Number(frequency.eligibleCardCount))),
        },
        {
          label: "Eligible desirable subjects",
          value:
            toOptionalNumber(frequency.eligibleSubjectCount) === UNAVAILABLE
              ? "—"
              : String(Math.round(Number(frequency.eligibleSubjectCount))),
        },
        {
          label: "Coverage",
          value:
            toOptionalNumber(frequency.coveredDemandShare) === UNAVAILABLE
              ? "—"
              : `${formatPercentFromUnit(frequency.coveredDemandShare, { decimals: 0 })} of desirable demand modeled`,
        },
      ],
      statusReason: frequency.statusReason ?? UNAVAILABLE,
    },
    {
      key: "dualPathDepth",
      title: "Dual-Path Depth",
      value:
        toOptionalNumber(dualPath.rawValue) === UNAVAILABLE
          ? "—"
          : formatPercentFromUnit(dualPath.rawValue),
      available: toOptionalNumber(dualPath.rawValue) !== UNAVAILABLE,
      interpretation:
        "Whether desirable Pokémon offer both an attainable printing and a true elite chase.",
      metrics: [
        {
          label: "Subjects with both paths",
          value:
            toOptionalNumber(dualPath.subjectsWithMultiplePaths) === UNAVAILABLE
              ? "—"
              : String(Math.round(Number(dualPath.subjectsWithMultiplePaths))),
        },
      ],
    },
  ];

  return {
    available: score !== UNAVAILABLE,
    score,
    scoreLabel: formatScore(score),
    rank: toOptionalNumber(appeal.rank),
    rankedSetCount: toOptionalNumber(appeal.rankedSetCount ?? appeal.cohortSize),
    tier: appeal.tier ?? UNAVAILABLE,
    version: appeal.version ?? UNAVAILABLE,
    rows,
    statusReason: appeal.statusReason ?? UNAVAILABLE,
    // Stated rather than implied. An unmodeled subject type is absent, not zero.
    subjectScope: {
      modeled: ["Pokémon"],
      notYetModeled: ["Trainer", "Artist"],
      note: "Trainer and artist desirability are not yet modeled and are not counted.",
    },
    sourceUsed: "collectorAppeal.components",
    fallbackUsed: false,
  };
}
