// Desirability agreement view: pure selection helpers for the Desirability
// Evidence section's ranked signal list. Everything here only *displays* what
// the backend desirability validation payload already computed (see
// backend/desirability/set_validation.py) — per-signal alignment scores
// (0–100, where 100 means the signal's market rank matches the desirability
// rank exactly and 0 means it sits at the opposite end of the field), the
// named strongest/conflicting signals, ranks, and total_ranked_sets.
//
// The engine score is UNSIGNED closeness on a 0–100 scale: it has no
// confirm/conflict sign and no natural center, so it is rendered as a ranked
// list (strongest agreement first) with the engine score surfaced verbatim —
// never as bars diverging around an invented midpoint and never as
// equal-weight bars that dress a weak score up as a positive amount of
// agreement. Confirm/conflict coloring comes ONLY from the engine's own named
// strongest_supporting_signal / biggest_conflicting_signal callouts. No new
// agreement math is derived on the frontend.
//
// Copy consuming these helpers must stay contemporaneous ("tracks", "agrees
// with", "explains") — future-tense claims are parked until the lagged
// forward-return study runs; see docs/research/desirability-price-driver-study.md.

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
// score (RIP Core, Card Appeal) have no honest row to render and are not
// listed.
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

// "Market Association" phrasing only: these describe how strongly desirability
// is *associated* with market outcomes in the current sample. They are
// descriptive context — never proof, never a claim about future prices, and
// never an input to the score — so no band is ever labeled "confirmed".
const VERDICT_LABEL_BY_BAND = {
  strong: "Strong market association",
  moderate: "Moderate market association",
  weak: "Weak market association",
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
    label: (band && VERDICT_LABEL_BY_BAND[band]) || "Market association",
    strongestLabel,
    // A single scored signal makes the backend name the same signal both
    // "strongest" and "conflict" — treat that as confirming, not an outlier.
    conflictLabel: conflictLabel && conflictLabel !== strongestLabel ? conflictLabel : null,
    summary: typeof summary === "string" && summary.trim() ? summary.trim() : null,
    alignmentScore,
  };
}

// Selects the listable agreement rows: every market signal the engine scored
// (a signal without an engine alignment magnitude gets no row — scores are
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

// Display-only model for the ranked signal list. Rows arrive from
// selectDesirabilityAgreement already sorted strongest agreement first; this
// keeps them in that order and passes every engine value through untouched —
// no sides, no bar extents, no derived center. The engine's unsigned 0–100
// score cannot honestly diverge around a midpoint, so nothing here invents
// one.
export function buildRankedAgreementModel(agreement) {
  if (!agreement || !Array.isArray(agreement.signals) || agreement.signals.length === 0) {
    return null;
  }
  return {
    anchorRank: agreement.anchorRank,
    fieldSize: agreement.fieldSize,
    rows: agreement.signals.map((signal) => ({ ...signal })),
    strongest: agreement.strongest,
    conflict: agreement.conflict,
  };
}

// Accessible-text equivalent of one ranked-list row. State naming mirrors the
// engine's callouts only; a row without one is described by its score alone.
export function describeAgreementSignal(row, fieldSize) {
  const stateText =
    row.state === "confirms"
      ? " — the engine's strongest supporting signal"
      : row.state === "conflicts"
      ? " — the engine's biggest conflicting signal"
      : "";
  const rankText =
    row.rank === null || row.rank === undefined
      ? ""
      : fieldSize
      ? `, market rank #${row.rank} of ${fieldSize}`
      : `, market rank #${row.rank}`;
  return `${row.label}: agreement ${Math.round(row.alignmentScore)} of 100${rankText}${stateText}`;
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
  return `Market signal agreement${anchorText}, listed strongest agreement first on the engine's 0 to 100 scale. ${signalText}.`;
}
