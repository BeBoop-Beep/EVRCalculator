export const RIP_SCORE_MODE = "rip-score";
export const RIP_CORE_MODE = "rip-core";

export const RIP_SCORE_HELPER =
  "Measures the complete opening experience — financial performance plus collector desirability.";
export const RIP_CORE_HELPER =
  "Measures the financial opening profile only — profit, safety, and stability, without collector desirability.";

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function firstValue(sources, keys) {
  for (const source of sources) {
    if (!source || typeof source !== "object") continue;
    for (const key of keys) {
      if (source[key] !== null && source[key] !== undefined) return source[key];
    }
  }
  return null;
}

function firstNumber(sources, keys) {
  return toNumber(firstValue(sources, keys));
}

export function hasRipCorePresentationContract(...sources) {
  return firstNumber(sources, ["relative_rip_core_score", "relativeRipCoreScore"]) !== null;
}

export function selectRipHeroScoreMode({ mode = RIP_SCORE_MODE, summary = {}, target = {} } = {}) {
  const sources = [summary, target];
  const coreAvailable = hasRipCorePresentationContract(...sources);
  const resolvedMode = mode === RIP_CORE_MODE && coreAvailable ? RIP_CORE_MODE : RIP_SCORE_MODE;

  if (resolvedMode === RIP_CORE_MODE) {
    const interpretation = firstValue(sources, ["rip_core_interpretation", "ripCoreInterpretation"]);
    return {
      mode: RIP_CORE_MODE,
      label: "RIP Core",
      helper: RIP_CORE_HELPER,
      score: firstNumber(sources, ["relative_rip_core_score", "relativeRipCoreScore"]),
      rank: firstNumber(sources, ["rip_core_rank", "ripCoreRank", "rip_rank_without_desirability", "ripRankWithoutDesirability"]),
      tier: firstValue(sources, ["rip_core_tier", "ripCoreTier"]),
      interpretation: {
        label:
          (interpretation && interpretation.label) ||
          firstValue(sources, ["rip_core_interpretation_label", "ripCoreInterpretationLabel"]),
        summary:
          (interpretation && interpretation.summary) ||
          firstValue(sources, ["rip_core_interpretation_summary", "ripCoreInterpretationSummary"]),
        severity:
          (interpretation && interpretation.severity) ||
          firstValue(sources, ["rip_core_interpretation_severity", "ripCoreInterpretationSeverity"]),
      },
      coreAvailable,
    };
  }

  const interpretation = firstValue(sources, [
    "rip_score_interpretation",
    "ripScoreInterpretation",
    "pack_score_interpretation",
    "packScoreInterpretation",
  ]);
  return {
    mode: RIP_SCORE_MODE,
    label: "RIP Score",
    helper: RIP_SCORE_HELPER,
    score: firstNumber(sources, ["relative_pack_score", "relativePackScore", "pack_score", "packScore"]),
    rank: firstNumber(sources, ["rip_rank_with_desirability", "ripRankWithDesirability", "pack_rank", "packRank"]),
    tier: firstValue(sources, ["pack_tier", "packTier"]),
    interpretation: {
      label:
        (interpretation && interpretation.label) ||
        firstValue(sources, ["rip_score_interpretation_label", "ripScoreInterpretationLabel", "pack_score_interpretation_label", "packScoreInterpretationLabel"]),
      summary:
        (interpretation && interpretation.summary) ||
        firstValue(sources, ["rip_score_interpretation_summary", "ripScoreInterpretationSummary", "pack_score_interpretation_summary", "packScoreInterpretationSummary"]),
      severity:
        (interpretation && interpretation.severity) ||
        firstValue(sources, ["rip_score_interpretation_severity", "ripScoreInterpretationSeverity", "pack_score_interpretation_severity", "packScoreInterpretationSeverity"]),
    },
    coreAvailable,
  };
}
