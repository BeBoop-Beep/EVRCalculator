// Chase Accessibility — ONE shared, presentation-safe public contract (Phase 3
// of the Overall RIP V12 UI standardization pass).
//
// WHY THIS EXISTS
// ----------------
// `backend/desirability/public_rip_contract_v11.py`'s `_chase_accessibility_block`
// already projects the PUBLIC RAW Chase Accessibility metric onto the
// `publicRipContractV11.chaseAccessibility` shape: `value` (A_raw, a decimal
// fraction), `percent` (A_raw * 100), `status`, `statusReason`, `version`,
// plus the diagnostic-only `chaseDepth` / `mappedHcMass`, and the two locked
// copy strings. This module does not duplicate that projection — it is a
// thin, frontend-side READ of that exact shape, normalized into one stable
// object every render surface can consume without re-deriving field names.
//
// SET-LEVEL, NOT PRODUCT-LEVEL
// ------------------------------
// This selector is for Chase Accessibility Score — the set-level, scored
// Overall RIP V12 ingredient, part of Market-Based Opening Quality, identical
// for every product from the same set/run. It must NEVER be used to render
// Product Chase Intelligence / Chase Access at Budget (`O_budget`), which is
// product-specific, budget-specific, Premium-gated, and entirely separate
// from Overall RIP. See `ProductChaseIntelligenceSection.jsx` for that
// surface; it has its own selector/props and does not import this module.
//
// SCORED VS. DIAGNOSTIC (Phase 8/D)
// ------------------------------------
// `rawAccessibility` / `displayAccessibility` are the one thing Overall RIP
// V12 actually scores (via the saturating transform, computed on the
// backend only — see `chase_accessibility_overall_score.py` — and NEVER
// recomputed here). `chaseDepth` and `valueConcentration` are explanatory
// diagnostics ONLY: they are not additional Overall RIP scoring inputs, and
// this module's returned shape/labels make that distinction explicit rather
// than leaving it implicit.
//
// RANK/TIER — NOT FABRICATED (Phase 8)
// ---------------------------------------
// No backend service in this codebase currently emits a Chase-Accessibility-
// specific `rank`, `cohortSize`, or `tier` (confirmed by inspection of
// `chase_accessibility_service.py` and `public_rip_contract_v11.py` during
// the Phase 2 backend field audit — neither computes or stores one). Per the
// task's Phase 8 instruction, this module NEVER derives a rank/tier locally
// from loaded sets. `rank` / `cohortSize` / `tier` are always `null` until a
// canonical backend ranking contract for Chase Accessibility exists. A future
// UI pass may show the raw metric + diagnostics without a fake cohort rank —
// this module already supports that (`available` distinguishes "have a raw
// metric" from "have a rank").
//
// NO FRONTEND SCORING
// --------------------
// This module never recomputes A_raw, the saturating transform, Chase Depth,
// or the mapped HC mass. Every value is read verbatim from the supplied
// contract source.

function toObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

// Locked public copy — sourced verbatim from
// `backend/desirability/public_rip_contract_v11.py` (never re-authored here).
export const CHASE_ACCESSIBILITY_LABEL = "Chase Accessibility";
export const CHASE_ACCESSIBILITY_PUBLIC_QUESTION =
  "How reachable are this set's most important collectible values from a pack?";
export const CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP =
  "How accessible the set's most important collectible value is from one pack.";

/**
 * Resolve the presentation-safe Chase Accessibility public contract from
 * whichever source objects are supplied. Accepts either a raw
 * `publicRipContractV11` object, or any ambient object carrying a
 * `chaseAccessibility` block in the same shape (mirrors the shadow-safety
 * precedence rule `overallRipExplanationHierarchySelector.mjs` already uses).
 *
 * Returned shape (Phase 3 contract):
 *   available, status, statusReason, label, publicQuestion, technicalTooltip,
 *   rawAccessibility, displayAccessibility,
 *   rank, cohortSize, tier,                 // always null — not backed yet
 *   chaseDepth, chaseDepthAvailable,        // diagnostic only
 *   valueConcentration, topCardConcentration, // diagnostic only, not yet backed
 *   mappedHcMass, mappedHcMassAvailable,    // diagnostic only
 *   version
 *
 * No field on this object is ever a scoring weight or a scoring-arithmetic
 * constant — see the CRITICAL DISCLOSURE RULE in
 * docs/research/OVERALL_RIP_V12_UI_STANDARDIZATION.md.
 */
export function selectChaseAccessibilityPresentation(...sources) {
  let block = null;
  for (const source of sources) {
    const safe = toObject(source);
    const v11 = toObject(safe.publicRipContractV11);
    if (Object.keys(v11).length > 0 && Object.keys(toObject(v11.chaseAccessibility)).length > 0) {
      block = v11.chaseAccessibility;
      break;
    }
    if (Object.keys(toObject(safe.chaseAccessibility)).length > 0) {
      block = safe.chaseAccessibility;
      break;
    }
  }
  block = toObject(block);

  const rawAccessibility = toNumber(block.value);
  const displayAccessibility = toNumber(block.percent);
  const status = block.status ?? null;
  const available = status === "ready" && (rawAccessibility !== null || displayAccessibility !== null);

  const chaseDepth = toNumber(block.chaseDepth);
  const mappedHcMass = toNumber(block.mappedHcMass);

  return {
    available,
    status,
    statusReason: block.statusReason ?? null,
    label: CHASE_ACCESSIBILITY_LABEL,
    publicQuestion: block.publicQuestion || CHASE_ACCESSIBILITY_PUBLIC_QUESTION,
    technicalTooltip: block.technicalTooltip || CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP,
    version: block.version ?? null,

    // Primary — the scored metric.
    rawAccessibility,
    displayAccessibility,

    // Rank/tier — NEVER fabricated. Always null until a canonical backend
    // Chase Accessibility ranking contract exists (Phase 8).
    rank: null,
    cohortSize: null,
    tier: null,

    // Diagnostics — explanatory only, NOT additional Overall RIP scoring
    // inputs. `chaseDepth` and `mappedHcMass` are real, backend-provided
    // fields; `valueConcentration` / `topCardConcentration` are not yet
    // projected by any backend service found in this pass (see the Phase 2
    // field matrix) and are always null placeholders for a future backend
    // addition rather than a frontend derivation.
    chaseDepth,
    chaseDepthAvailable: chaseDepth !== null,
    mappedHcMass,
    mappedHcMassAvailable: mappedHcMass !== null,
    valueConcentration: null,
    topCardConcentration: null,
  };
}
