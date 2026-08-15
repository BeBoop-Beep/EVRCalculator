// Collector Appeal V4, explained through its two parallel factors.
//
// WHAT THIS READS
// ---------------
// The canonical V8 contract's Collector Appeal V4 block, and nothing else — see
// canonicalRipV7.mjs for the resolver and its precedence rules. This module
// previously read `publicRipContractV6` / `overallRipV6` / a hand-rebuilt shape
// off `openingExperience`, which published Collector Appeal **V2** (the bounded
// headroom formula `D + 0.50 * (0.60F + 0.40P) * (1 - D)`) under the current
// name. There is now no path here that reads V6, V5, V2, legacy CA7 or
// Universal/Roster Desirability. A missing canonical block renders unavailable.
//
// TWO PARALLEL FACTORS, NOT A PIPELINE
// ------------------------------------
//   Roster Desirability · Desirable Outcome Frequency
//
// They are explanatory factors of one score, presented side by side. The old
// surface drew them as a sequential chain (Set Desirability -> Collector Appeal
// -> RIP Score Contribution), which claimed Roster Desirability is a first
// stage feeding the other. It is not: both are inputs to a single combination,
// and the arrows described arithmetic the backend does not perform.
//
// WHY DUAL-PATH DEPTH IS NO LONGER A ROW
// --------------------------------------
// Collector Appeal V4 does not consume it. The ablation held every other
// assumption identical and found P changed 3 of 231 pairwise orderings, leaving
// Spearman(with P, without P) = 0.9966 for a universal set-level score.
//
// It is NOT deleted from the product: the backend still computes and publishes
// it, under `collectorAppeal.diagnostics.dualPathDepth`, and it remains a
// candidate input for future Personal Fit models. It is simply not a factor of
// THIS score, and a factor row is a claim that it fed the number. A surface that
// wants to show it must read it from `diagnostics` and label it as a diagnostic
// — never add it back to `rows`.
//
// WHAT IS DELIBERATELY NOT PUBLISHED
// ----------------------------------
// Collector Appeal V4's modifier ceiling, its downside damping, its H anchors,
// the computed modifier, and any formula string. Two points of the curve
// determine the line, so publishing the ceiling beside the anchors would be
// publishing the formula. The backend withholds them from the contract
// (`weightsDisclosed: false`); this module must not reconstruct them. The
// Overall RIP composition weights are likewise not shown: there is no
// composition block here any more.
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
//
// ONE PUBLIC SCORE
// ----------------
// `publicScore` is the backend cohort-relative 0-100 score and is the only
// value a normal surface may render. `modelScore` is the fixed-anchor formula
// output, kept for audit/Research and named so it cannot be mistaken for a
// public number. This selector no longer returns a generic `score`: it used to
// alias the ABSOLUTE value while the canonical resolver's `score` aliased the
// RELATIVE one, which is why one set could show Collector Appeal twice, at two
// different numbers, on one page.

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

function readScoreLayers(block = {}) {
  const safe = toObject(block);
  const modelScore = toOptionalNumber(safe.absoluteScore ?? safe.score);
  const relativeScore = toOptionalNumber(safe.relativeScore);
  return {
    // INTERNAL. Fixed-anchor model output; never rendered on a normal surface.
    modelScore,
    relativeScore,
    // THE public value.
    publicScore: relativeScore,
    publicAvailable: relativeScore !== UNAVAILABLE,
  };
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
 * Roster Desirability and Desirable Outcome Frequency — two scored factors.
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

  const scores = readScoreLayers(appeal);
  const rosterScore = toOptionalNumber(roster.score);
  const frequencyRaw = toOptionalNumber(frequency.rawValue);
  const rosterRelative = toOptionalNumber(roster.relativeScore);
  const frequencyRelative = toOptionalNumber(frequency.relativeScore);

  const rows = [
    {
      key: "rosterDesirability",
      title: "Roster Desirability",
      // D is published 0-100; the other two are 0-1 shares. Each row carries its
      // own formatted value so the surface never rescales one into the other.
      value: formatScore(rosterScore),
      available: rosterScore !== UNAVAILABLE,
      // Backend-owned cohort-relative standing. The raw desirability
      // measurement is not interchangeable with quality versus other sets.
      relativeScore: rosterRelative,
      railPercent: rosterRelative,
      rank: toOptionalNumber(roster.rank),
      cohortSize: toOptionalNumber(roster.rankedSetCount ?? roster.cohortSize),
      tier: roster.tier ?? UNAVAILABLE,
      interpretation:
        "How desirable the Pokémon roster is before pull difficulty is considered.",
      metrics: [],
    },
    {
      key: "desirableOutcomeFrequency",
      title: "Desirable Outcome Frequency",
      value: frequencyRaw === UNAVAILABLE ? "—" : formatPercentFromUnit(frequencyRaw),
      available: frequencyRaw !== UNAVAILABLE,
      // Backend-owned cohort-relative standing, not the raw probability.
      relativeScore: frequencyRelative,
      railPercent: frequencyRelative,
      rank: toOptionalNumber(frequency.rank),
      cohortSize: toOptionalNumber(frequency.rankedSetCount ?? frequency.cohortSize),
      tier: frequency.tier ?? UNAVAILABLE,
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
  ];

  const scope = toObject(appeal.subjectScope);
  return {
    // Availability is decided by the PUBLIC score. A block carrying only the
    // fixed-anchor model score is not renderable on a normal surface, so it must
    // not report itself available — that is what let an absolute value take a
    // public slot.
    available: scores.publicAvailable,
    relativeScore: scores.relativeScore,
    // INTERNAL. Kept for audit/Research; never rendered under a public label.
    modelScore: scores.modelScore,
    // Strict public score: no absolute fallback under a `/100` label.
    publicScore: scores.publicScore,
    publicScoreLabel: formatScore(scores.publicScore),
    publicAvailable: scores.publicAvailable,
    rank: toOptionalNumber(appeal.rank),
    rankedSetCount: toOptionalNumber(appeal.rankedSetCount ?? appeal.cohortSize),
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
