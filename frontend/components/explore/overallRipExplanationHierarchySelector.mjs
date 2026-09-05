// Overall RIP explanation hierarchy — ONE shared, version-aware selector.
//
// WHY THIS EXISTS
// ----------------
// Two Overall RIP models exist in this codebase: Overall RIP V10 (90%
// Financial RIP V4 + 10% Collector Appeal V5, read through `canonicalRipV7.mjs`
// — retained as explicit historical/rollback lineage) and Overall RIP V12
// (86% Financial RIP V4 + 4% Chase Accessibility Score + 10% Collector Appeal
// V5, published on the `publicRipContractV11` / `overallRipV12` shape).
// AS OF THE 2026-09-03 CUTOVER, V12 IS CANONICAL
// (`backend.desirability.scoring_config.CANONICAL_OVERALL_RIP_VERSION`). This
// module does not read that backend constant directly and never changes which
// contract shape a caller supplies — it ONLY decides which EXPLANATION to
// render for whichever shape actually arrives, so it needed no code change at
// cutover time: a generic/current payload now naturally carries V12 data (via
// the additive `publicRipContractV11`/`overallRipV12` block), and this
// selector renders the presentation-safe V12 hierarchy for it exactly as it
// always would have.
//
// CRITICAL DISCLOSURE RULE (UI-1 standardization pass)
// ------------------------------------------------------
// This selector never renders scoring-weight percentages (no "86%", "4%",
// "10%", "90%", "95.56%", "4.44%") in any headline/copy field. Weight
// fractions remain available on the returned `weights` /
// `internalFinancialShare` / `internalAccessibilityShare` fields for
// non-UI/internal consumers (audit payloads, historical tooling) but no
// render surface may turn them into visible text. See
// docs/research/OVERALL_RIP_V12_UI_STANDARDIZATION.md.
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

// The approved copy (Prompt closure, locked). Any surface rendering the Overall
// RIP explanation must source these strings from here rather than re-authoring
// them, so a future edit cannot drift one render site from another.
export const OVERALL_RIP_PUBLIC_QUESTION = "How good is this to open overall?";
export const MARKET_BASED_PUBLIC_QUESTION =
  "What do the market and modeled opening outcomes say about this opening?";
export const MARKET_BASED_LABEL = "Market-Based Opening Quality";
export const MARKET_BASED_EXPLANATORY_NOTE =
  "Explanatory grouping only — not an independent third pillar and never persisted as its own score.";

// PRESENTATION-SAFE headline. Never renders a scoring-weight percentage — see
// the CRITICAL DISCLOSURE RULE in the Overall RIP V12 UI standardization doc.
// `internalFinancialShare` / `internalAccessibilityShare` / `marketBasedWeight`
// / `collectorWeight` remain on the returned object for non-UI/internal
// consumers (audit payloads, historical comparison tooling) but no render
// surface may turn them into visible copy.
const MARKET_BASED_HEADLINE =
  "Market-Based Opening Quality combines Financial RIP with Chase Accessibility.";

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
    // Internal/diagnostic only — never rendered as public copy. Kept for
    // historical/audit consumers that need the derived split.
    marketBasedWeight,
    collectorWeight: collector,
    internalFinancialShare: financial / marketBasedWeight,
    internalAccessibilityShare: accessibility / marketBasedWeight,
    // Presentation-safe: no percentages, no weight disclosure.
    headline: MARKET_BASED_HEADLINE,
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

  // PRESENTATION-SAFE headline — never a weight-percentage sentence. See the
  // CRITICAL DISCLOSURE RULE: no "86% Financial RIP + 4% Chase Accessibility
  // + 10% Collector Appeal" style copy on normal user-facing surfaces.
  const headline =
    weights.financial !== null && weights.chaseAccessibility !== null && weights.collectorAppeal !== null
      ? "Overall RIP combines Market-Based Opening Quality with Collector Appeal."
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
    // PRESENTATION-SAFE: neutral wording, no weight-percentage disclosure
    // (V10's 90/10 split stays internal, same disclosure rule as V12).
    headline: "Overall RIP combines Financial RIP with Collector Appeal.",
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
