// Overall RIP explanation hierarchy — ONE shared, version-aware selector.
//
// WHY THIS EXISTS
// ----------------
// Two Overall RIP models now exist in this codebase: the CANONICAL Overall RIP
// V10 (90% Financial RIP V4 + 10% Collector Appeal V5, read through
// `canonicalRipV7.mjs`) and the SHADOW Overall RIP V12 (86% Financial RIP V4 +
// 4% Chase Accessibility Score + 10% Collector Appeal V5, published only on the
// SHADOW `publicRipContractV11` / `overallRipV12` shape). Neither the canonical
// selector (`resolveCanonicalRipV7`) nor the ranking order changes here — V10
// stays canonical. This module ONLY decides which EXPLANATION to render for
// whichever contract shape a caller actually supplies.
//
// A SURFACE MUST NEVER EXPLAIN ONE VERSION'S DATA WITH THE OTHER'S WEIGHTS
// --------------------------------------------------------------------------
// The version rendered is determined by which contract shape was actually
// supplied (the presence of a `publicRipContractV11` / top-level
// `overallRipV12` + `overallRipV12Composition` block), never by a hardcoded
// assumption or a caller-supplied flag. A V10-only payload NEVER renders
// 86/4/10, and a V12 payload is only rendered as V12 when its own composition
// block is present to source the weights from.
//
// NO FRONTEND SCORING
// --------------------
// This selector never recomputes the Overall RIP V12 blend or the Accessibility
// saturating transform in JavaScript. Every V12 weight is lifted verbatim from the
// backend's `overallRipV12Composition.weights` /
// `overallRipV12Composition.effectiveWeights`. The only arithmetic performed
// here is the Market-Based explanatory grouping's OWN internal share
// (Financial's share and Accessibility's share of the combined Market-Based
// weight), and that division is DERIVED from the supplied weights so it can
// never silently drift from them — the same rule the backend's own
// `OVERALL_RIP_V12_FINANCIAL_SHARE_OF_MARKET_BASED` constant already applies.
//
// V10's 90%/10% split is not read from a data field at all: the public V10
// contract deliberately withholds a numeric weight vector from normal render
// surfaces (see `financialRipV3Selector.mjs`'s "CANONICAL WEIGHTS — INTERNAL,
// NEVER PUBLISHED" note), and V10's split is fixed, singular and asserted at
// backend import time (`scoring_config._audit_overall_rip_weights`). Stating it
// as approved copy is the same pattern `ProductRipSection.jsx` already uses for
// the identical sentence.
//
// MARKET-BASED IS EXPLANATORY ONLY
// ---------------------------------
// The "Market-Based Opening Quality" grouping (Financial + Accessibility) is
// NEVER a third persisted pillar and is NEVER shown for V10 data, where
// Accessibility is not an Overall RIP input at all.

import { resolveCanonicalRipV7, readCanonicalBlock } from "./canonicalRipV7.mjs";

function toObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function hasContent(value) {
  return Object.keys(toObject(value)).length > 0;
}

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatWeightPercent(weight) {
  const parsed = toNumber(weight);
  if (parsed === null) return "—";
  // Weights are decimal fractions (0.86, 0.04, 0.10, …). Rendered to whole
  // percent for the headline sentence; the exact fraction remains available on
  // the returned `weights` object for any surface that needs more precision.
  return `${Math.round(parsed * 100)}%`;
}

// The approved copy (Prompt closure, locked). Any surface rendering the Overall
// RIP explanation must source these strings from here rather than re-authoring
// them, so a future edit cannot drift one render site from another.
export const OVERALL_RIP_PUBLIC_QUESTION = "How good is this to open overall?";
export const MARKET_BASED_PUBLIC_QUESTION =
  "What do the market and modeled opening outcomes say about this opening?";
export const MARKET_BASED_LABEL = "Market-Based Opening Quality";
export const MARKET_BASED_EXPLANATORY_NOTE =
  "Explanatory grouping only — not an independent third pillar and never persisted as its own score.";

function buildMarketBasedGrouping(weights) {
  const financial = toNumber(weights.financial);
  const accessibility = toNumber(weights.chaseAccessibility);
  const collector = toNumber(weights.collectorAppeal);
  if (financial === null || accessibility === null || collector === null) return null;
  const marketBasedWeight = financial + accessibility;
  if (marketBasedWeight <= 0) return null;
  return {
    label: MARKET_BASED_LABEL,
    publicQuestion: MARKET_BASED_PUBLIC_QUESTION,
    explanatoryOnly: true,
    note: MARKET_BASED_EXPLANATORY_NOTE,
    // The 90%/10% outer split, DERIVED (not hand-typed) from the supplied
    // weights.
    marketBasedWeight,
    collectorWeight: collector,
    // The 95.5556%/4.4444% internal split within Market-Based, likewise
    // derived by division rather than restated as a literal.
    internalFinancialShare: financial / marketBasedWeight,
    internalAccessibilityShare: accessibility / marketBasedWeight,
    headline: `${Math.round(marketBasedWeight * 100)}% Market-Based + ${Math.round(
      collector * 100
    )}% Collector Appeal`,
    internalHeadline: `${(100 * (financial / marketBasedWeight)).toFixed(
      2
    )}% Financial RIP V4 + ${(100 * (accessibility / marketBasedWeight)).toFixed(
      2
    )}% Chase Accessibility Score`,
  };
}

function buildV12Explanation(source) {
  const overallV12 = toObject(source.overallRipV12);
  const composition = toObject(source.overallRipV12Composition);
  const weightsRaw = toObject(composition.weights);
  const effectiveWeightsRaw = toObject(composition.effectiveWeights);

  const weights = {
    financial: toNumber(weightsRaw.financial_rip),
    chaseAccessibility: toNumber(weightsRaw.chase_accessibility),
    collectorAppeal: toNumber(weightsRaw.collector_appeal),
  };

  const status = overallV12.status ?? null;
  const score = toNumber(overallV12.score);
  const available = status === "ready" && score !== null;

  const headline =
    weights.financial !== null && weights.chaseAccessibility !== null && weights.collectorAppeal !== null
      ? `${formatWeightPercent(weights.financial)} Financial RIP V4 + ${formatWeightPercent(
          weights.chaseAccessibility
        )} Chase Accessibility Score + ${formatWeightPercent(weights.collectorAppeal)} Collector Appeal V5`
      : null;

  return {
    version: "v12",
    // SHADOW, never canonical — mirrors the backend contract's own flag.
    canonical: false,
    contractVersion: composition.version || overallV12.version || null,
    available,
    score,
    status,
    statusReason: overallV12.statusReason ?? null,
    missingInputs: Array.isArray(overallV12.missingInputs) ? overallV12.missingInputs : [],
    weights,
    effectiveWeights: {
      chaseAccessibility: toNumber(effectiveWeightsRaw.chase_accessibility),
    },
    publicQuestion: OVERALL_RIP_PUBLIC_QUESTION,
    headline,
    // The Market-Based explanatory grouping. Only present when the raw weights
    // resolved cleanly; a partial/unavailable composition never fabricates a
    // grouping from guessed numbers.
    marketBased: buildMarketBasedGrouping(weights),
    components: toObject(overallV12.components),
  };
}

function buildV10Explanation(canonicalOverallBlock) {
  const available = canonicalOverallBlock.available;
  return {
    version: "v10",
    canonical: true,
    contractVersion: null,
    available,
    score: canonicalOverallBlock.publicScore,
    status: canonicalOverallBlock.status,
    statusReason: canonicalOverallBlock.statusReason,
    missingInputs: [],
    // V10's split is fixed, singular, and not sourced from a numeric contract
    // field on normal surfaces — see the module docstring.
    weights: { financial: 0.9, chaseAccessibility: null, collectorAppeal: 0.1 },
    effectiveWeights: { chaseAccessibility: null },
    publicQuestion: OVERALL_RIP_PUBLIC_QUESTION,
    headline: "90% Financial RIP V4 + 10% Collector Appeal V5",
    // NEVER shown for V10: Chase Accessibility is not an Overall RIP V10 input,
    // so there is no Market-Based grouping to derive.
    marketBased: null,
    components: null,
  };
}

/**
 * Resolve the version-aware Overall RIP explanation for whichever contract
 * shape the given sources actually carry.
 *
 * Precedence: the explicit SHADOW `publicRipContractV11` opt-in key is
 * preferred WHEN PRESENT, because a caller that explicitly fetched the V11
 * contract asked to see the V12 explanation. A generic/current-resolver
 * caller that has NOT fetched the V11 contract — the common case, everywhere
 * V10 remains canonical — renders the V10 explanation even if the underlying
 * target row also carries ambient top-level `overallRipV12` fields (see the
 * shadow-safety note inline below). This function never promotes V12 over V10
 * on its own initiative; it renders whichever shape it was actually handed.
 */
export function selectOverallRipExplanationHierarchy(...sources) {
  // ONLY the explicit `publicRipContractV11` opt-in key selects the V12
  // explanation. A plain target/ambient object that happens to also carry
  // top-level `overallRipV12` / `overallRipV12Composition` fields (the shape
  // `explore_rip_statistics_service.py` enriches onto every target row,
  // additively, well before any contract is attached) is NOT treated as an
  // opt-in on its own — the same shadow-safety rule the backend contract
  // layer already enforces: V12 is additive and a consumer must explicitly
  // ask for the V11 contract to see it. This is what keeps a
  // generic/current-resolver caller rendering V10 even once V12 data is
  // ambiently present everywhere, until a real canonical cutover.
  for (const source of sources) {
    const safe = toObject(source);
    const v11 = toObject(safe.publicRipContractV11);
    if (hasContent(v11) && hasContent(v11.overallRipV12) && hasContent(v11.overallRipV12Composition)) {
      return buildV12Explanation(v11);
    }
  }

  const canonical = resolveCanonicalRipV7(...sources);
  const overallBlock = readCanonicalBlock(canonical.overall);
  return buildV10Explanation(overallBlock);
}
