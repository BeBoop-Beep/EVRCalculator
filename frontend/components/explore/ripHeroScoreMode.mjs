// The RIP hero selector: which score/rank/tier the big number shows.
//
// CANONICAL V7 ONLY. The hero reads Overall RIP V7 through the one shared
// resolver in canonicalRipV7.mjs — the current model, 0.90 * Financial RIP V3 +
// 0.10 * Collector Appeal V3 — and nothing else.
//
// WHAT THIS USED TO DO, AND WHY IT WAS WRONG
// ------------------------------------------
// It read the backend's `rip` object. `rip` is **Overall RIP v4**
// (`compute_overall_rip(pillars, ca7_score)` = 90% RIP Core + 10% legacy CA7),
// so every surface calling this selector — the set hero, the Insights headline,
// the landing spotlight — published a superseded blend under the name "RIP
// Score". It also carried a "RIP Core" mode, a second public presentation of
// the retired Financial RIP V2 model. Both are gone: `rip`, `ripCore`, V6, V5,
// the legacy `pack_score`/`relative_pack_score`/`pack_rank` fields and the
// interpretation-engine verdict fields are not read here in any code path, not
// even as a fallback. A missing canonical contract renders as unavailable.
//
// NO INTERPRETATION
// -----------------
// This selector no longer returns an interpretation label/summary/severity.
// Those came from the retired Profit/Safety/Stability interpretation engine and
// described a model the site no longer publishes. The backend still emits them
// for compatibility; no current public surface consumes them.

import { readCanonicalBlock, resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";

export const RIP_SCORE_LABEL = "RIP Score";

// Neutral and factual. It names the two canonical inputs without stating a
// weight, an arithmetic relationship, or a judgement about the set.
export const RIP_SCORE_HELPER = "Financial RIP + Collector Appeal";

export function hasCanonicalRipContract(...sources) {
  return readCanonicalBlock(resolveCanonicalRipV7(...sources).overall).available;
}

export function selectRipHeroScoreMode({ canonical = null, summary = {}, target = {}, payload = {} } = {}) {
  // `canonical` is the caller's already-resolved bundle. The set page resolves
  // once and passes it here so the hero cannot settle on a different source
  // than the Overview summary, Financial RIP or Collector Appeal did. Callers
  // without a bundle (Explore rows, the landing spotlight) still pass raw
  // sources and get the same resolution in the same order: the set-page
  // snapshot payload, then the rankings target, then the merged summary. All
  // three carry the SAME backend objects, so order only matters when a stale
  // cache and a fresh one briefly coexist.
  const resolved = canonical
    ? resolveCanonicalRipV7(canonical)
    : resolveCanonicalRipV7(payload, target, summary);
  const overall = readCanonicalBlock(resolved.overall);

  return {
    label: RIP_SCORE_LABEL,
    helper: RIP_SCORE_HELPER,
    // THE public RIP Score: the canonical cohort-relative 0-100 value. The raw
    // 90/10 blend is `modelScore` and is never rendered on a normal surface —
    // a payload carrying only that renders unavailable rather than putting a
    // differently-scaled number under the public label.
    publicScore: overall.publicScore,
    relativeScore: overall.relativeScore,
    // INTERNAL. Audit/Research only.
    modelScore: overall.modelScore,
    rank: overall.rank,
    tier: overall.tier,
    cohortSize: overall.cohortSize,
    available: overall.available,
    // When the canonical RIP is unavailable the backend says why; the UI
    // renders that state rather than substituting a legacy score.
    status: overall.status,
    statusReason: overall.statusReason,
    // Which canonical shape answered — "publicRipContractV7", "topLevelV7", or
    // null. Diagnostic only; both shapes are the same model.
    sourceShape: resolved.shape,
  };
}
