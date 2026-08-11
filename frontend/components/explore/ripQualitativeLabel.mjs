// Qualitative interpretation of the canonical Overall RIP standing.
//
// WHY THIS EXISTS
// ---------------
// "#9 Modern Set to Rip Right Now" is precise but does not tell a casual reader
// whether #9 of 22 is good, average or poor. This module answers that question
// WITHOUT introducing a second classification model: the descriptor is a pure
// relabelling of the canonical S/A/B/C/D/F tier that the RIP model already
// publishes (see constants/rankConfig.mjs). There is no editorial judgement and
// no per-set special casing here.
//
// TIER SOURCE PRECEDENCE
//   1. `tier` as published on the canonical Overall RIP block.
//   2. If (and only if) the backend published no tier, the tier is recovered
//      from rank/cohort through `topPercentToTier` — the SAME cut points the
//      tier system itself uses. This is a shape fallback within one model, not
//      a different model.
// When neither is available the label is null and the page renders the headline
// alone rather than guessing.

import { RANK_CONFIG, topPercentToTier } from "../../constants/rankConfig.mjs";

const TIER_LABELS = {
  S: "TOP-TIER RIP",
  A: "STRONG RIP",
  B: "SOLID RIP",
  C: "MID-TIER RIP",
  D: "WEAK RIP",
  F: "WEAK RIP",
};

export function getRipQualitativeLabel({ tier = null, rank = null, cohortSize = null } = {}) {
  const published = String(tier || "").toUpperCase();
  let resolved = TIER_LABELS[published] ? published : null;

  if (!resolved && Number.isFinite(Number(rank)) && Number(cohortSize) > 0) {
    resolved = topPercentToTier((Number(rank) / Number(cohortSize)) * 100);
  }

  if (!resolved || !TIER_LABELS[resolved]) return null;
  return {
    tier: resolved,
    label: TIER_LABELS[resolved],
    color: RANK_CONFIG[resolved]?.color || null,
  };
}
