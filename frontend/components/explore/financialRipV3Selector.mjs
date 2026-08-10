// Financial RIP V3 — the six-component breakdown selector.
//
// "FINANCIAL RIP" MEANS V3, EVERYWHERE
// ------------------------------------
// There is no other current public financial model. The legacy three-pillar
// Profit/Safety/Stability contract (`ripCore`, read by
// `ripScoreBreakdownSelector.mjs`) is Financial RIP **V2** and is no longer
// presented on any public surface — not as a comparison, not behind a toggle,
// not as a fallback.
//
// NO FALLBACK, EVER
// -----------------
// V3 reads V3 fields only. There is deliberately no fallback to the
// similarly-named V2 fields: `ripCore.components.profit.score` and
// `financialRipV3.components.true_win_frequency.score` are different models,
// and rendering one under the other's label would be a silent mis-statement
// that no reader could detect. Missing V3 data renders as a precise unavailable
// state instead.
//
// NO SCORING IN JAVASCRIPT
// ------------------------
// Every score, rank, tier, ratio and conditional mean below is lifted from the
// backend payload. This file formats; it never computes a financial number.
// The only arithmetic here is presentational unit conversion (a 0-1 ratio to a
// percentage string), which is formatting, not scoring. `score` remains the
// fixed-anchor model output for internal/audit consumers; `publicScore` is the
// backend cohort-relative score and is the only value intended for `/100` UI.
//
// NO VISIBLE WEIGHTS
// ------------------
// The six cards carry no weighting percentage. The weights are real and are
// published in the contract's audit block for verification, but showing "25%"
// on a card invites the reader to re-derive the score by hand, and the six
// weights are not the interesting thing about any of them.

import { resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";

const UNAVAILABLE = null;

/**
 * The canonical Financial RIP block for a set, from the one shared resolver.
 *
 * Prefers `publicRipContractV7.financialRip` because that block travels with
 * the Overall RIP and Collector Appeal it was blended with, so a surface taking
 * all three cannot mix bundles. Falls back only to the top-level
 * `financialRipV3` — the SAME model in the shape the ranked target rows carry.
 * The two differ only in component key casing and in `rankedSetCount` vs
 * `cohortSize`, both of which the selectors below already read either way.
 *
 * `ripCore` is never consulted. It is Financial RIP V2.
 */
export function resolveCanonicalFinancialRip(...sources) {
  return resolveCanonicalRipV7(...sources).financialRip;
}

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return UNAVAILABLE;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : UNAVAILABLE;
}

function toObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function readScoreLayers(block = {}) {
  const safe = toObject(block);
  const absoluteScore = toOptionalNumber(safe.absoluteScore ?? safe.score);
  const relativeScore = toOptionalNumber(safe.relativeScore);
  return {
    absoluteScore,
    relativeScore,
    publicScore: relativeScore,
    publicAvailable: relativeScore !== UNAVAILABLE,
  };
}

// --- Formatters -------------------------------------------------------------
// Every one of these returns an explicit em dash for missing data. Zero is a
// real measurement and formats as "0"; absent data must never render as 0, or a
// set with no simulation looks like a set that returned nothing.

export function formatDollars(value, { decimals = 2 } = {}) {
  const parsed = toOptionalNumber(value);
  if (parsed === UNAVAILABLE) return "—";
  return `$${parsed.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

export function formatPercent(value, { decimals = 1 } = {}) {
  const parsed = toOptionalNumber(value);
  if (parsed === UNAVAILABLE) return "—";
  return `${(parsed * 100).toFixed(decimals)}%`;
}

export function formatRatio(value, { decimals = 2 } = {}) {
  const parsed = toOptionalNumber(value);
  if (parsed === UNAVAILABLE) return "—";
  return `${parsed.toFixed(decimals)}x`;
}

export function formatScore(value) {
  const parsed = toOptionalNumber(value);
  if (parsed === UNAVAILABLE) return "—";
  return parsed.toFixed(1);
}

// "roughly 1 in 14 packs". Only emitted when the backend supplied a positive
// probability; it is never derived here from something that might be zero.
export function formatOneInN(oneInN) {
  const parsed = toOptionalNumber(oneInN);
  if (parsed === UNAVAILABLE || parsed <= 0) return UNAVAILABLE;
  return `about 1 in ${Math.round(parsed).toLocaleString()} packs`;
}

// --- Card definitions -------------------------------------------------------
// Order is the product spec's order and is asserted by the contract tests.

const V3_CARDS = [
  {
    key: "trueWinFrequency",
    snakeKey: "true_win_frequency",
    title: "Chance to Win",
    // Deliberately "recovers or beats", not "profits": a pack landing exactly
    // on cost recovers it, and the component counts that as a win.
    interpretation: "How often a pack comes back worth at least what it cost.",
    metrics: (raw) => [
      {
        label: "Recovers or beats pack cost",
        value: formatPercent(raw.trueWinProbability),
      },
      {
        label: "Frequency",
        value: formatOneInN(raw.impliedOddsOneInN) || "—",
      },
      { label: "Pack price used", value: formatDollars(raw.packCost) },
    ],
  },
  {
    key: "typicalRetention",
    snakeKey: "typical_retention",
    title: "Typical Opening",
    // "Typical"/"median" throughout. P50 is not a floor and the copy must never
    // let a reader take it as one.
    interpretation: "What the median simulated pack came back worth — half were above, half below.",
    metrics: (raw) => [
      { label: "Median pack value", value: formatDollars(raw.typicalPackValue) },
      {
        label: "Share of cost retained",
        value: formatPercent(raw.typicalRetentionRatio),
      },
      { label: "Pack price used", value: formatDollars(raw.packCost) },
    ],
  },
  {
    key: "lossResilience",
    snakeKey: "loss_resilience",
    title: "Loss Resilience",
    // A loss is a loss. This card describes how soft the losses are; it must
    // never phrase a loss as a win.
    interpretation: "When a pack loses, how much of the cost it still hands back.",
    metrics: (raw) => [
      {
        label: "Average return when losing",
        value: formatDollars(raw.averageLosingReturnValue),
      },
      {
        label: "Cost retained when losing",
        value: formatPercent(raw.averageRetentionGivenLoss),
      },
      {
        label: "Near-miss share of losses",
        value: formatPercent(raw.softLossShareGivenLoss),
      },
      {
        label: "Chance of losing over half",
        value: formatPercent(raw.hardLossProbability),
      },
    ],
  },
  {
    key: "realisticUpside",
    snakeKey: "realistic_upside",
    title: "Strong Upside",
    interpretation:
      "The good-but-not-miraculous outcome: the top 5% of packs, with the top 1% excluded.",
    metrics: (raw) => [
      // "begins at", never "average". P95 is a THRESHOLD.
      {
        label: "Top 5% begins at",
        value: formatDollars(raw.p95ThresholdValue),
      },
      {
        label: "Threshold vs cost",
        value: formatRatio(raw.p95ThresholdRatio),
      },
      // A distinct number with distinct wording, so the threshold and the
      // conditional mean can never be read as the same measurement.
      {
        label: "Average return, 95th–99th percentile",
        value: formatDollars(raw.realisticTailMeanValue),
      },
      {
        label: "That average vs cost",
        value: formatRatio(raw.realisticTailMeanRatio),
      },
    ],
  },
  {
    key: "jackpotUpside",
    snakeKey: "jackpot_upside",
    title: "Jackpot Upside",
    interpretation: "The exceptional 1% of packs — rare by definition, and capped in the score.",
    metrics: (raw) => [
      { label: "Top 1% begins at", value: formatDollars(raw.p99ThresholdValue) },
      { label: "Threshold vs cost", value: formatRatio(raw.p99ThresholdRatio) },
      {
        label: "Average top 1% return",
        value: formatDollars(raw.jackpotTailMeanValue),
      },
      {
        label: "Share of all value in the top 1%",
        value: formatPercent(raw.jackpotValueShare),
      },
    ],
  },
  {
    key: "baseEconomicEfficiency",
    snakeKey: "base_economic_efficiency",
    title: "Base Economics",
    interpretation:
      "Average return with the jackpots removed — how much of the headline average an ordinary opening actually sees.",
    metrics: (raw) => [
      { label: "Total return to player", value: formatPercent(raw.totalRtpRatio) },
      {
        label: "Excluding the top 1%",
        value: formatPercent(raw.baseRtpExcludingTop1Pct),
      },
      {
        label: "Carried by the top 1%",
        value: formatPercent(raw.jackpotValueShare),
      },
    ],
  },
];

export const FINANCIAL_RIP_V3_CARD_ORDER = V3_CARDS.map((card) => card.title);

// --- Selector ---------------------------------------------------------------

/**
 * Build the six V3 breakdown rows from the canonical `financialRipV3` object.
 *
 * `financialRipV3` is the backend object served on the rankings target and the
 * set-page snapshot. It is NEVER substituted with `ripCore`.
 */
export function selectFinancialRipV3Breakdown(financialRipV3 = {}, options = {}) {
  const safe = toObject(financialRipV3);
  const components = toObject(safe.components);
  const requestTimeout =
    options?.requestTimeout === true || options?.payload?.meta?.requestTimeout === true;

  const hasContract = Object.keys(components).length > 0;
  const status = safe.status ?? (hasContract ? null : "unavailable");
  const parentScores = readScoreLayers(safe);
  const isReady = status === "ready" && parentScores.absoluteScore !== UNAVAILABLE;
  const missingFields = [];
  const missingPublicScoreFields = [];

  const rows = V3_CARDS.map((card) => {
    // The backend keys components in snake_case on the runtime object and in
    // camelCase in the compact public contract. Both are accepted so the same
    // component is read whichever surface supplied it — this is a casing
    // difference in ONE object, not a fallback to a different model.
    const component = toObject(components[card.snakeKey] ?? components[card.key]);
    const raw = toObject(component.raw);
    const scores = readScoreLayers(component);
    const score = scores.absoluteScore;
    const rank = toOptionalNumber(component.rank);

    if (score === UNAVAILABLE) missingFields.push(`${card.snakeKey}.score`);
    if (scores.relativeScore === UNAVAILABLE) missingPublicScoreFields.push(`${card.snakeKey}.relativeScore`);
    if (rank === UNAVAILABLE) missingFields.push(`${card.snakeKey}.rank`);

    return {
      key: card.key,
      title: card.title,
      score,
      scoreLabel: formatScore(score),
      absoluteScore: scores.absoluteScore,
      relativeScore: scores.relativeScore,
      // Strict public score: no absolute fallback under a `/100` label.
      publicScore: scores.publicScore,
      publicScoreLabel: formatScore(scores.publicScore),
      publicAvailable: scores.publicAvailable,
      rankValue: rank,
      rankTier: component.tier ?? UNAVAILABLE,
      // `rankedSetCount` in the packaged contract, `cohortSize` on the runtime
      // object — one backend denominator under the two names it travels with.
      cohortSize: toOptionalNumber(component.rankedSetCount ?? component.cohortSize),
      interpretation: card.interpretation,
      metrics: card.metrics(raw),
      available: score !== UNAVAILABLE,
      // Weight is intentionally absent from the row. It is not rendered, so it
      // is not selected — a field the UI does not read is a field that can only
      // go stale.
      rankDiagnostic:
        rank === UNAVAILABLE
          ? requestTimeout
            ? "Rank loading: set page snapshot request timed out; retrying."
            : hasContract
            ? "Rank unavailable: this Financial RIP V3 component has no cohort rank."
            : "Rank unavailable: Financial RIP V3 is not in this payload."
          : UNAVAILABLE,
    };
  });

  return {
    mode: "v3",
    rows,
    score: parentScores.absoluteScore,
    scoreLabel: formatScore(parentScores.absoluteScore),
    absoluteScore: parentScores.absoluteScore,
    relativeScore: parentScores.relativeScore,
    // Strict public score: no absolute fallback under a `/100` label.
    publicScore: parentScores.publicScore,
    publicScoreLabel: formatScore(parentScores.publicScore),
    publicAvailable: parentScores.publicAvailable,
    rank: toOptionalNumber(safe.rank),
    rankedSetCount: toOptionalNumber(safe.rankedSetCount ?? safe.cohortSize),
    tier: safe.tier ?? UNAVAILABLE,
    version: safe.scoreVersion ?? safe.version ?? UNAVAILABLE,
    normalizationVersion: safe.normalizationVersion ?? UNAVAILABLE,
    sourceUsed: "financialRipV3.components",
    fallbackUsed: false,
    diagnostics: {
      source: "financialRipV3.components",
      status: requestTimeout ? "loading" : isReady ? "ready" : "unavailable",
      requestTimeout,
      statusReason: safe.statusReason ?? UNAVAILABLE,
      statusDetail: safe.statusDetail ?? UNAVAILABLE,
      missingFields: requestTimeout ? [] : missingFields,
      missingPublicScoreFields: requestTimeout ? [] : missingPublicScoreFields,
      fallbackUsed: false,
    },
  };
}

/**
 * The unweighted Depth and Robustness diagnostic.
 *
 * Returned SEPARATELY from the six rows on purpose: merging it into `rows`
 * would put it in the same list, with the same treatment, as six weighted
 * components, and it is not one. It explains a profile; it does not score it.
 */
export function selectDepthAndRobustness(financialRipV3 = {}) {
  const block = toObject(toObject(financialRipV3).depthAndRobustness);
  const available = block.status === "ready";
  return {
    available,
    isWeighted: false,
    statusReason: block.statusReason ?? UNAVAILABLE,
    concentrationLabel: block.concentrationLabel ?? UNAVAILABLE,
    rows: [
      {
        key: "chaseDepth",
        label: "Chase Depth",
        value:
          toOptionalNumber(block.effectiveChaseCount) === UNAVAILABLE
            ? "—"
            : `${Number(block.effectiveChaseCount).toFixed(1)} effective chases`,
      },
      {
        key: "valueConcentration",
        label: "Value Concentration",
        value:
          toOptionalNumber(block.top1EvShare) === UNAVAILABLE
            ? "—"
            : `${formatPercent(block.top1EvShare)} in the top card`,
      },
      {
        key: "jackpotDependence",
        label: "Jackpot Dependence",
        value: formatPercent(block.jackpotValueShare),
      },
      {
        key: "effectiveChases",
        label: "Number of Effective Chases",
        value:
          toOptionalNumber(block.effectiveChaseCount) === UNAVAILABLE
            ? "—"
            : Number(block.effectiveChaseCount).toFixed(1),
      },
    ],
    detail: {
      top1EvShare: toOptionalNumber(block.top1EvShare),
      top2EvShare: toOptionalNumber(block.top2EvShare),
      top3EvShare: toOptionalNumber(block.top3EvShare),
      top5EvShare: toOptionalNumber(block.top5EvShare),
      hhiEvConcentration: toOptionalNumber(block.hhiEvConcentration),
      cardsTracked: toOptionalNumber(block.cardsTracked),
      totalCardEv: toOptionalNumber(block.totalCardEv),
      nonJackpotValueShare: toOptionalNumber(block.nonJackpotValueShare),
    },
  };
}

/**
 * The V3 additions to the detailed simulation metrics table.
 *
 * The existing P05/P25/P50/P75/P95/P99/mean/std-dev rows and the V2 metrics are
 * unchanged and still rendered by their existing code. These are ADDITIONAL
 * rows: the conditional tail averages and the loss profile, which V2 never had.
 * P05 in particular stays in the table — it is a real statistic and it drives
 * the distribution charts; it simply carries no V3 weight.
 */
export function selectFinancialRipV3DetailedMetrics(financialRipV3 = {}) {
  const safe = toObject(financialRipV3);
  const components = toObject(safe.components);
  const disclosures = toObject(safe.distributionDisclosures);

  const raw = (key) =>
    toObject(toObject(components[key] ?? components[toCamel(key)]).raw);

  const realistic = raw("realistic_upside");
  const jackpot = raw("jackpot_upside");
  const loss = raw("loss_resilience");
  const base = raw("base_economic_efficiency");

  return [
    {
      key: "realisticTailMean",
      label: "Average return, 95th–99th percentile",
      value: formatDollars(realistic.realisticTailMeanValue),
    },
    {
      key: "jackpotTailMean",
      label: "Average return, top 1%",
      value: formatDollars(jackpot.jackpotTailMeanValue),
    },
    {
      key: "averageLosingReturn",
      label: "Average return when losing",
      value: formatDollars(loss.averageLosingReturnValue),
    },
    {
      key: "hardLossProbability",
      label: "Chance of recovering under half of cost",
      value: formatPercent(loss.hardLossProbability),
    },
    {
      key: "softLossShare",
      label: "Near-miss share of losing packs",
      value: formatPercent(loss.softLossShareGivenLoss),
    },
    {
      key: "totalRtp",
      label: "Total return to player",
      value: formatPercent(base.totalRtpRatio),
    },
    {
      key: "baseRtp",
      label: "Return to player, excluding top 1%",
      value: formatPercent(base.baseRtpExcludingTop1Pct),
    },
    {
      key: "jackpotValueShare",
      label: "Share of all value in the top 1%",
      value: formatPercent(base.jackpotValueShare),
    },
    {
      // Still shown, still labelled honestly, and explicitly NOT a V3 input.
      key: "p05Value",
      label: "5th percentile pack value",
      value: formatDollars(disclosures.p05Value),
    },
  ];
}

function toCamel(snake) {
  return String(snake).replace(/_([a-z])/g, (_match, char) => char.toUpperCase());
}
