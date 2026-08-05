// Collector Appeal V3, explained through its three parallel factors.
//
// WHAT THIS READS
// ---------------
// The canonical V7 contract's Collector Appeal block, and nothing else — see
// canonicalRipV7.mjs for the resolver and its precedence rules. This module
// previously read `publicRipContractV6` / `overallRipV6` / a hand-rebuilt shape
// off `openingExperience`, which published Collector Appeal **V2** (the bounded
// headroom formula `D + 0.50 * (0.60F + 0.40P) * (1 - D)`) under the current
// name. There is now no path here that reads V6, V5, V2, legacy CA7 or
// Universal/Roster Desirability. A missing canonical block renders unavailable.
//
// THREE PARALLEL FACTORS, NOT A PIPELINE
// --------------------------------------
//   Roster Desirability · Desirable Outcome Frequency · Dual-Path Depth
//
// They are explanatory factors of one score, presented side by side. The old
// surface drew them as a sequential chain (Set Desirability -> Collector Appeal
// -> RIP Score Contribution), which claimed Roster Desirability is a first
// stage feeding the other two. It is not: all three are inputs to a single
// weighted combination, and the arrows described arithmetic the backend does
// not perform.
//
// WHAT IS DELIBERATELY NOT PUBLISHED
// ----------------------------------
// Collector Appeal V3's internal D/H/P weights, any per-factor contribution,
// and any formula string. The arithmetic is a one-line weighted sum, so
// publishing the weights would be publishing the formula — and publishing a
// contribution would be the same thing by division. The backend withholds them
// from the contract (`weightsDisclosed: false`); this module must not
// reconstruct them. The Overall RIP composition weights are likewise not shown:
// there is no composition block here any more.
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
// Every score, probability and rank is lifted from the backend payload. The
// only arithmetic is presentational unit conversion.

import { resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";

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

const SUBJECT_SCOPE_NOTE =
  "Trainer and artist desirability are not yet modeled and are not counted.";

/**
 * The Collector Appeal breakdown: Roster Desirability, Desirable Outcome
 * Frequency, Dual-Path Depth — three parallel factors of one score.
 *
 * Trainer and artist desirability are NOT rendered as zero or as "not
 * desirable": they are not modeled yet, so they are omitted and the omission is
 * stated. Scoring an unmodeled subject type as zero would be a claim about
 * those cards that the model is not entitled to make.
 *
 * Each factor carries its OWN availability. One missing factor greys its own
 * card and never zeroes it, and never suppresses the other two.
 */
export function selectCollectorAppealBreakdown(...sources) {
  const resolved = resolveCanonicalRipV7(...sources);
  const appeal = toObject(resolved.collectorAppeal);
  const components = toObject(appeal.components);
  const roster = toObject(components.rosterDesirability);
  const frequency = toObject(components.desirableOutcomeFrequency);
  const dualPath = toObject(components.dualPathDepth);

  const score = toOptionalNumber(appeal.score);
  const rosterScore = toOptionalNumber(roster.score);
  const frequencyRaw = toOptionalNumber(frequency.rawValue);
  const dualPathRaw = toOptionalNumber(dualPath.rawValue);

  const rows = [
    {
      key: "rosterDesirability",
      title: "Roster Desirability",
      // D is published 0-100; the other two are 0-1 shares. Each row carries its
      // own formatted value so the surface never rescales one into the other.
      value: formatScore(rosterScore),
      available: rosterScore !== UNAVAILABLE,
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
      value: dualPathRaw === UNAVAILABLE ? "—" : formatPercentFromUnit(dualPathRaw),
      available: dualPathRaw !== UNAVAILABLE,
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

  const scope = toObject(appeal.subjectScope);
  return {
    available: score !== UNAVAILABLE,
    score,
    scoreLabel: formatScore(score),
    rank: toOptionalNumber(appeal.rank),
    rankedSetCount: toOptionalNumber(appeal.rankedSetCount),
    tier: appeal.tier ?? UNAVAILABLE,
    rows,
    statusReason: appeal.statusReason ?? UNAVAILABLE,
    // Stated rather than implied. An unmodeled subject type is absent, not zero.
    // The backend carries the same statement on the contract; its wording wins
    // when present so the note cannot drift from the model.
    subjectScope: {
      modeled: Array.isArray(scope.modeled) ? scope.modeled : ["Pokémon"],
      notYetModeled: Array.isArray(scope.notYetModeled) ? scope.notYetModeled : ["Trainer", "Artist"],
      note: scope.note || SUBJECT_SCOPE_NOTE,
    },
    note: FINANCIAL_VS_COLLECTOR_NOTE,
    sourceShape: resolved.shape,
  };
}
