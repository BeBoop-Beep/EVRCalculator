// The RIP hero selector: which score/rank/tier the big number shows.
//
// CANONICAL CONTRACT ONLY. The hero reads the backend's versioned `rip` and
// `ripCore` objects — actual weighted scores, ranks and tiers computed against
// the backend-authorized public cohort. It deliberately does NOT fall back to
// the legacy fields (`pack_score`, `relative_pack_score`, `pack_rank`,
// `relative_rip_core_score`): those are a cohort min-max presentation of a
// superseded blend, and silently serving one when the canonical object is
// missing would put a number on screen that is not the RIP Score while
// labeling it as one. A missing contract renders as unavailable instead —
// see ripHeroScoreMode.test.mjs, which fails if a legacy read reappears.

export const RIP_SCORE_MODE = "rip-score";
export const RIP_CORE_MODE = "rip-core";

export const RIP_SCORE_HELPER =
  "Complete opening profile — financial performance plus Collector Appeal.";
export const RIP_CORE_HELPER =
  "Financial opening profile only — Profit, Safety and Stability, without Collector Appeal.";

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function firstContract(sources, keys) {
  for (const source of sources) {
    if (!source || typeof source !== "object") continue;
    for (const key of keys) {
      const candidate = source[key];
      if (candidate && typeof candidate === "object") return candidate;
    }
  }
  return null;
}

function interpretationOf(contract, sources, snakePrefix, camelPrefix) {
  const embedded = toObject(contract?.interpretation);
  const fromFields = (suffix, camelSuffix) => {
    for (const source of sources) {
      if (!source || typeof source !== "object") continue;
      const value = source[`${snakePrefix}_${suffix}`] ?? source[`${camelPrefix}${camelSuffix}`];
      if (value !== null && value !== undefined) return value;
    }
    return null;
  };
  return {
    label: embedded.label ?? fromFields("interpretation_label", "InterpretationLabel"),
    summary: embedded.summary ?? fromFields("interpretation_summary", "InterpretationSummary"),
    severity: embedded.severity ?? fromFields("interpretation_severity", "InterpretationSeverity"),
  };
}

export function hasCanonicalRipContract(...sources) {
  const rip = firstContract(sources, ["rip"]);
  return toNumber(rip?.score) !== null;
}

export function hasRipCorePresentationContract(...sources) {
  const core = firstContract(sources, ["ripCore", "rip_core"]);
  return toNumber(core?.score) !== null;
}

export function selectRipHeroScoreMode({ mode = RIP_SCORE_MODE, summary = {}, target = {}, payload = {} } = {}) {
  // Source order: the set-page snapshot payload (set detail), then the
  // rankings target (Explore), then the merged summary. All three carry the
  // SAME backend objects — one bundle powers both surfaces — so order only
  // matters when a stale cache and a fresh one briefly coexist.
  const sources = [payload, target, summary];
  const rip = toObject(firstContract(sources, ["rip"]));
  const ripCore = toObject(firstContract(sources, ["ripCore", "rip_core"]));
  const coreAvailable = toNumber(ripCore.score) !== null;
  const resolvedMode = mode === RIP_CORE_MODE && coreAvailable ? RIP_CORE_MODE : RIP_SCORE_MODE;

  if (resolvedMode === RIP_CORE_MODE) {
    // `score` is the PUBLIC cohort-relative 0-100 score (the production scoring
    // language). The raw 60/25/15 formula output is the model/absolute score,
    // surfaced separately and never promoted to the primary number. When the
    // relative score is missing we render unavailable rather than silently
    // showing the absolute in its place.
    const coreRelative = toNumber(ripCore.relativeScore);
    return {
      mode: RIP_CORE_MODE,
      label: "RIP Core",
      helper: RIP_CORE_HELPER,
      score: coreRelative,
      relativeScore: coreRelative,
      absoluteScore: toNumber(ripCore.score),
      rank: toNumber(ripCore.rank),
      tier: ripCore.tier ?? null,
      cohortSize: toNumber(ripCore.cohortSize),
      available: coreRelative !== null,
      status: ripCore.status ?? null,
      interpretation: interpretationOf(ripCore, sources, "rip_core", "ripCore"),
      coreAvailable,
    };
  }

  // `score` is the PUBLIC cohort-relative 0-100 Overall RIP; the raw 90/10 blend
  // is the model/absolute score. Availability is keyed on the relative score so
  // a stale payload carrying only the absolute renders unavailable rather than
  // silently promoting the model score to the public number.
  const relative = toNumber(rip.relativeScore);
  return {
    mode: RIP_SCORE_MODE,
    label: "RIP Score",
    helper: RIP_SCORE_HELPER,
    score: relative,
    relativeScore: relative,
    absoluteScore: toNumber(rip.score),
    rank: toNumber(rip.rank),
    tier: rip.tier ?? null,
    cohortSize: toNumber(rip.cohortSize),
    available: relative !== null,
    // When the canonical RIP is unavailable the backend says why
    // (e.g. incomplete_missing_desirability); the UI renders that state
    // rather than substituting a legacy score.
    status: rip.status ?? null,
    interpretation: interpretationOf(rip, sources, "rip_score", "ripScore"),
    coreAvailable,
  };
}
