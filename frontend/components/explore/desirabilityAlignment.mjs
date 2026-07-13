// Desirability alignment ladder: pure selection + layout helpers for the
// Desirability Evidence section's rank-comparison strip. Everything here only
// *displays* what the backend desirability validation payload already computed
// (see backend/desirability/set_validation.py) — ranks, total_ranked_sets, the
// named strongest/conflicting signals, and per-signal alignment scores. No new
// agreement math is derived on the frontend.

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

// One entry per market signal the ladder can plot. `signalName` mirrors the
// backend's _signal_name output ("Expected Value", "Top Chase Value", ...) so
// strongest/conflict matching stays a plain string comparison against what the
// payload names. `alignmentKeys` point at desirability_alignment_details.
export const DESIRABILITY_LADDER_SIGNALS = [
  {
    key: "rip_core",
    label: "RIP Core",
    signalName: null,
    rankKeys: ["rip_core_rank_without_desirability", "ripCoreRankWithoutDesirability"],
    alignmentKeys: [],
  },
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
  {
    key: "card_appeal",
    label: "Card appeal",
    signalName: "Card Appeal",
    rankKeys: ["card_appeal_rank", "cardAppealRank"],
    alignmentKeys: [],
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
  const match = DESIRABILITY_LADDER_SIGNALS.find(
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

// Selects the plottable ladder: the desirability anchor rank, the field size,
// and every market signal with a usable rank. State coloring is driven solely
// by the payload's named strongest/conflicting signals — every other signal is
// neutral (the payload's per-signal alignment scores ride along for
// tooltips/screen readers only).
export function selectDesirabilityAlignmentLadder(validation) {
  if (!validation || typeof validation !== "object") {
    return null;
  }
  const anchorRank = readRank(validation, ["desirability_rank", "desirabilityRank"]);
  if (anchorRank === null) {
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
  for (const signal of DESIRABILITY_LADDER_SIGNALS) {
    const rank = readRank(validation, signal.rankKeys);
    if (rank === null) {
      continue;
    }
    const normalizedName = normalizeSignalName(signal.signalName);
    const isStrongest = Boolean(normalizedName && strongestName && normalizedName === strongestName);
    const isConflict = Boolean(normalizedName && conflictName && normalizedName === conflictName);
    signals.push({
      key: signal.key,
      label: signal.label,
      rank,
      state: isStrongest ? "confirms" : isConflict ? "conflicts" : "neutral",
      alignmentScore: readNumber(details, signal.alignmentKeys),
    });
  }
  if (signals.length === 0) {
    return null;
  }

  const observedMaxRank = Math.max(anchorRank, ...signals.map((signal) => signal.rank));
  const declaredFieldSize = readRank(validation, ["total_ranked_sets", "totalRankedSets"]);
  // Ranks can exceed a stale declared field size; the axis must always contain
  // every plotted rank.
  const fieldSize = Math.max(declaredFieldSize ?? observedMaxRank, observedMaxRank);
  if (fieldSize < 2) {
    return null;
  }

  return {
    anchorRank,
    fieldSize,
    signals,
    strongest: signals.find((signal) => signal.state === "confirms") || null,
    conflict: signals.find((signal) => signal.state === "conflicts") || null,
  };
}

const LADDER_LANE_HEIGHT = 15;
const LADDER_LABEL_FONT_SIZE = 10.5;
// Rough glyph width for the 10.5px UI font; only used to reserve horizontal
// room per label so lanes never collide.
const LADDER_LABEL_CHAR_WIDTH = 6.1;
const LADDER_LABEL_GAP = 6;
const LADDER_PLOT_PADDING = 16;
const LADDER_HEADER_HEIGHT = 18;

export function estimateLadderLabelWidth(text) {
  return String(text || "").length * LADDER_LABEL_CHAR_WIDTH + 4;
}

function assignLanes(entries, width) {
  // entries sorted by x. Greedy first-fit per side: place each label in the
  // lowest lane whose previous label leaves enough horizontal room.
  const laneEnds = [];
  for (const entry of entries) {
    const halfWidth = entry.labelWidth / 2;
    const labelX = Math.min(Math.max(entry.x, halfWidth), Math.max(width - halfWidth, halfWidth));
    const start = labelX - halfWidth;
    let lane = 0;
    while (lane < laneEnds.length && start < laneEnds[lane] + LADDER_LABEL_GAP) {
      lane += 1;
    }
    laneEnds[lane] = labelX + halfWidth;
    entry.lane = lane;
    entry.labelX = labelX;
  }
  return laneEnds.length;
}

// Pure geometry for the ladder SVG at a concrete pixel width: dot positions,
// staggered label lanes (above/below the axis, extra lanes only when labels
// would otherwise overlap), overlapping-rank dot offsets, and total height.
export function buildLadderLayout(ladder, width) {
  const plotWidth = Math.max(0, width - LADDER_PLOT_PADDING * 2);
  if (!ladder || plotWidth <= 0) {
    return null;
  }
  const { anchorRank, fieldSize, signals } = ladder;
  const xForRank = (rank) =>
    LADDER_PLOT_PADDING + ((Math.min(Math.max(rank, 1), fieldSize) - 1) / (fieldSize - 1)) * plotWidth;

  const points = signals
    .map((signal) => ({
      ...signal,
      x: xForRank(signal.rank),
      labelText: `${signal.label} #${signal.rank}`,
    }))
    .sort((a, b) => a.x - b.x || a.rank - b.rank);
  points.forEach((point) => {
    point.labelWidth = estimateLadderLabelWidth(point.labelText);
  });

  // Alternate label sides along the axis so neighbours separate vertically
  // first; the lane pass below only adds lanes when a side still collides.
  const above = [];
  const below = [];
  points.forEach((point, index) => {
    point.side = index % 2 === 0 ? "above" : "below";
    (point.side === "above" ? above : below).push(point);
  });
  const lanesAbove = Math.max(1, assignLanes(above, width));
  const lanesBelow = Math.max(1, assignLanes(below, width));

  const baselineY = LADDER_HEADER_HEIGHT + 8 + lanesAbove * LADDER_LANE_HEIGHT + 12;
  const belowLabelsBottom = baselineY + 16 + lanesBelow * LADDER_LANE_HEIGHT;
  const height = belowLabelsBottom + 16;

  // Coincident ranks: fan the dots vertically so each stays visible/hittable.
  const byRank = new Map();
  for (const point of points) {
    const group = byRank.get(point.rank) || [];
    group.push(point);
    byRank.set(point.rank, group);
  }
  for (const group of byRank.values()) {
    group.forEach((point, index) => {
      point.dotY = baselineY + (index - (group.length - 1) / 2) * 9;
    });
  }

  for (const point of points) {
    point.labelY =
      point.side === "above"
        ? baselineY - 18 - point.lane * LADDER_LANE_HEIGHT
        : baselineY + 26 + point.lane * LADDER_LANE_HEIGHT;
  }

  return {
    width,
    height,
    baselineY,
    plotLeft: LADDER_PLOT_PADDING,
    plotRight: LADDER_PLOT_PADDING + plotWidth,
    anchorX: xForRank(anchorRank),
    labelFontSize: LADDER_LABEL_FONT_SIZE,
    headerY: LADDER_HEADER_HEIGHT - 5,
    endLabelY: height - 4,
    points,
  };
}

// Accessible-text equivalents shared by the aria-label and the sr-only list.
export function describeLadderSignal(signal, fieldSize) {
  const stateText =
    signal.state === "confirms"
      ? " (strongest confirming signal)"
      : signal.state === "conflicts"
      ? " (biggest conflicting signal)"
      : "";
  const alignmentText =
    signal.alignmentScore === null || signal.alignmentScore === undefined
      ? ""
      : `, alignment ${Math.round(signal.alignmentScore)} of 100`;
  return `${signal.label} rank #${signal.rank} of ${fieldSize}${alignmentText}${stateText}`;
}

export function buildLadderAriaLabel(ladder) {
  if (!ladder) {
    return "";
  }
  const signalText = ladder.signals.map((signal) => describeLadderSignal(signal, ladder.fieldSize)).join("; ");
  return `Market signal ranks compared against the desirability anchor at rank #${ladder.anchorRank} of ${ladder.fieldSize}. ${signalText}.`;
}
