// Desirability agreement view: pure selection helpers for the Desirability
// Evidence section's diverging confirm/conflict chart. Everything here only
// *displays* what the backend desirability validation payload already computed
// (see backend/desirability/set_validation.py) — per-signal alignment scores
// (0–100, where 100 means the signal's market rank matches the desirability
// rank exactly and 0 means it sits at the opposite end of the field), the
// named strongest/conflicting signals, ranks, and total_ranked_sets. No new
// agreement math is derived on the frontend; the diverging geometry below is
// an affine display transform of the engine's own 0–100 scale around its
// midpoint, and the engine score is always surfaced verbatim next to the bar.

function toFiniteNumber(value) {
  const parsed = typeof value === "string" ? Number(value) : value;
  return typeof parsed === "number" && Number.isFinite(parsed) ? parsed : null;
}

function readNumber(source, keys) {
  for (const key of keys) {
    const parsed = toFiniteNumber(source?.[key]);
    if (parsed !== null) {
      return parsed;
    }
  }
  return null;
}

function readRank(source, keys) {
  const parsed = readNumber(source, keys);
  return parsed === null ? null : Math.round(parsed);
}

function normalizeSignalName(value) {
  return String(value || "").trim().replace(/\s+/g, " ").toLowerCase() || null;
}

// One entry per market signal the backend scores against the desirability
// rank (the ALIGNMENT_WEIGHTS set). `signalName` mirrors the backend's
// _signal_name output ("Expected Value", "Top Chase Value", ...) so
// strongest/conflict matching stays a plain string comparison against what the
// payload names. `alignmentKeys` point at desirability_alignment_details —
// the engine's per-signal agreement magnitude. Signals the engine does not
// score (RIP Core, Card Appeal) have no honest bar length and are not listed.
export const DESIRABILITY_AGREEMENT_SIGNALS = [
  {
    key: "set_value",
    label: "Set value",
    signalName: "Set Value",
    rankKeys: ["set_value_rank", "setValueRank"],
    alignmentKeys: ["set_value_alignment", "setValueAlignment"],
  },
  {
    key: "top_chase_value",
    label: "Top chase",
    signalName: "Top Chase Value",
    rankKeys: ["top_chase_value_rank", "topChaseValueRank"],
    alignmentKeys: ["top_chase_value_alignment", "topChaseValueAlignment"],
  },
  {
    key: "top_10_card_value",
    label: "Top 10 value",
    signalName: "Top 10 Card Value",
    rankKeys: ["top_10_card_value_rank", "top10CardValueRank"],
    alignmentKeys: ["top_10_card_value_alignment", "top10CardValueAlignment"],
  },
  {
    key: "avg_hit_value",
    label: "Avg hit",
    signalName: "Avg Hit Value",
    rankKeys: ["avg_hit_value_rank", "avgHitValueRank"],
    alignmentKeys: ["avg_hit_value_alignment", "avgHitValueAlignment"],
  },
  {
    key: "p95_value",
    label: "P95",
    signalName: "P95 Value",
    rankKeys: ["p95_rank", "p95Rank"],
    alignmentKeys: ["p95_value_alignment", "p95ValueAlignment"],
  },
  {
    key: "expected_value",
    label: "EV",
    signalName: "Expected Value",
    rankKeys: ["expected_value_rank", "expectedValueRank"],
    alignmentKeys: ["expected_value_alignment", "expectedValueAlignment"],
  },
];

const VERDICT_LABEL_BY_BAND = {
  strong: "Market confirmed",
  moderate: "Partly confirmed",
  weak: "Weakly confirmed",
};

function displayLabelForSignalName(name) {
  const normalized = normalizeSignalName(name);
  if (!normalized) {
    return null;
  }
  const match = DESIRABILITY_AGREEMENT_SIGNALS.find(
    (signal) => normalizeSignalName(signal.signalName) === normalized
  );
  return match ? match.label : String(name).trim();
}

// Plain-language verdict for the section lead. The verdict *determination*
// (band, strongest, conflict, summary sentence) is entirely the backend's;
// this only picks display labels for it.
export function selectDesirabilityVerdict(validation) {
  if (!validation || typeof validation !== "object") {
    return null;
  }
  const band =
    normalizeSignalName(validation.desirability_alignment_band ?? validation.desirabilityAlignmentBand) || null;
  const strongestRaw = validation.strongest_supporting_signal ?? validation.strongestSupportingSignal ?? null;
  const conflictRaw = validation.biggest_conflicting_signal ?? validation.biggestConflictingSignal ?? null;
  const summary = validation.desirability_alignment_summary ?? validation.desirabilityAlignmentSummary ?? null;
  const alignmentScore = readNumber(validation, ["desirability_alignment_score", "desirabilityAlignmentScore"]);
  const strongestLabel = displayLabelForSignalName(strongestRaw);
  const conflictLabel = displayLabelForSignalName(conflictRaw);
  if (!band && !strongestLabel && !conflictLabel && !summary) {
    return null;
  }
  return {
    band,
    label: (band && VERDICT_LABEL_BY_BAND[band]) || "Market check",
    strongestLabel,
    // A single scored signal makes the backend name the same signal both
    // "strongest" and "conflict" — treat that as confirming, not an outlier.
    conflictLabel: conflictLabel && conflictLabel !== strongestLabel ? conflictLabel : null,
    summary: typeof summary === "string" && summary.trim() ? summary.trim() : null,
    alignmentScore,
  };
}

// Selects the plottable agreement rows: every market signal the engine scored
// (a signal without an engine alignment magnitude gets no bar — lengths are
// never fabricated from ranks or anything else). State naming mirrors the
// payload's strongest/conflicting signals; ranks ride along as supporting
// labels only.
export function selectDesirabilityAgreement(validation) {
  if (!validation || typeof validation !== "object") {
    return null;
  }
  const details =
    (typeof validation.desirability_alignment_details === "object" && validation.desirability_alignment_details) ||
    (typeof validation.desirabilityAlignmentDetails === "object" && validation.desirabilityAlignmentDetails) ||
    {};
  const strongestName = normalizeSignalName(
    validation.strongest_supporting_signal ?? validation.strongestSupportingSignal
  );
  const conflictName = normalizeSignalName(
    validation.biggest_conflicting_signal ?? validation.biggestConflictingSignal
  );

  const signals = [];
  for (const signal of DESIRABILITY_AGREEMENT_SIGNALS) {
    const alignmentScore = readNumber(details, signal.alignmentKeys);
    if (alignmentScore === null) {
      continue;
    }
    const normalizedName = normalizeSignalName(signal.signalName);
    const isStrongest = Boolean(normalizedName && strongestName && normalizedName === strongestName);
    const isConflict = Boolean(normalizedName && conflictName && normalizedName === conflictName);
    signals.push({
      key: signal.key,
      label: signal.label,
      rank: readRank(validation, signal.rankKeys),
      alignmentScore,
      state: isStrongest ? "confirms" : isConflict ? "conflicts" : "neutral",
    });
  }
  if (signals.length === 0) {
    return null;
  }

  // Strongest agreement first, so the confirming cluster leads the read.
  signals.sort((a, b) => b.alignmentScore - a.alignmentScore);

  return {
    anchorRank: readRank(validation, ["desirability_rank", "desirabilityRank"]),
    fieldSize: readRank(validation, ["total_ranked_sets", "totalRankedSets"]),
    signals,
    strongest: signals.find((signal) => signal.state === "confirms") || null,
    conflict: signals.find((signal) => signal.state === "conflicts") || null,
  };
}

// Display-only geometry for the diverging bars. The engine's alignment scale
// is 0–100 with 100 = full agreement and 0 = full disagreement; its midpoint
// (50) is the neutral center line, scores above it extend right (confirms)
// and scores below it extend left (conflicts). `extentPercent` is the bar
// length as a percentage of ONE half-axis: |score − 50| × 2. This is a pure
// rescale of the engine's number — no agreement value is computed here, and
// the untouched engine score is kept on every row for the end label.
export function buildDivergingAgreementModel(agreement) {
  if (!agreement || !Array.isArray(agreement.signals) || agreement.signals.length === 0) {
    return null;
  }
  const rows = agreement.signals.map((signal) => ({
    ...signal,
    side: signal.alignmentScore >= 50 ? "confirms" : "conflicts",
    extentPercent: Math.min(100, Math.abs(signal.alignmentScore - 50) * 2),
  }));
  return {
    anchorRank: agreement.anchorRank,
    fieldSize: agreement.fieldSize,
    rows,
    strongest: agreement.strongest,
    conflict: agreement.conflict,
  };
}

// Accessible-text equivalents shared by the aria-label and the sr-only list.
export function describeAgreementSignal(row, fieldSize) {
  const stateText =
    row.state === "confirms"
      ? " (strongest confirming signal)"
      : row.state === "conflicts"
      ? " (biggest conflicting signal)"
      : "";
  const sideText = row.side === "confirms" ? "confirms the desirability read" : "conflicts with the desirability read";
  const rankText =
    row.rank === null || row.rank === undefined
      ? ""
      : fieldSize
      ? `, rank #${row.rank} of ${fieldSize}`
      : `, rank #${row.rank}`;
  return `${row.label}: agreement ${Math.round(row.alignmentScore)} of 100, ${sideText}${rankText}${stateText}`;
}

export function buildAgreementAriaLabel(model) {
  if (!model || !Array.isArray(model.rows) || model.rows.length === 0) {
    return "";
  }
  const anchorText =
    model.anchorRank !== null && model.anchorRank !== undefined
      ? model.fieldSize
        ? ` against this set's desirability rank #${model.anchorRank} of ${model.fieldSize}`
        : ` against this set's desirability rank #${model.anchorRank}`
      : "";
  const signalText = model.rows.map((row) => describeAgreementSignal(row, model.fieldSize)).join("; ");
  return `Market signal agreement${anchorText}. Bars right of center confirm the desirability read, bars left of center conflict with it. ${signalText}.`;
}
