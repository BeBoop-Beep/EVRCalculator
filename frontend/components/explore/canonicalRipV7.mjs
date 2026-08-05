// The ONE canonical reader for the current public RIP model.
//
// WHY THIS EXISTS
// ---------------
// Before this module, every public surface picked its own object: the set hero
// and the landing spotlight read `rip` (Overall RIP **v4** = 90% RIP Core + 10%
// legacy CA7), the Explore leaderboard's "RIP SCORE" column read `rip.score`,
// its "Financial RIP" column read `ripCore` (Financial RIP **V2**), and the
// Collector Appeal breakdown read the v6 contract. Four surfaces, four models,
// one product name. This module is the single place that answers "what is the
// current RIP model for this target", so a caller cannot quietly pick a
// different one.
//
// SOURCE PRECEDENCE — ONE MODEL, TWO SHAPES
// -----------------------------------------
//   1. `publicRipContractV7`  — preferred. It packages the canonical Overall
//      RIP, Financial RIP and Collector Appeal blocks together, so a consumer
//      that takes all three cannot mix a score from one bundle with a rank from
//      another.
//   2. `overallRipV7` / `financialRipV3` — the SAME models at top level, on the
//      target rows that carry them without the packaged contract. This is a
//      SHAPE fallback within one model, never a model fallback.
//
// There is deliberately no third step. `rip`, `ripCore`, `overallRipV6`,
// `overallRipV5`, Financial RIP V2, Collector Appeal V2, legacy CA7 and
// Universal/Roster Desirability are all DIFFERENT MODELS, and serving one of
// them under a canonical label is the exact defect this module removes. When
// neither canonical shape is present the result is `available: false` and the
// surface renders unavailable — a stale snapshot must show as a stale snapshot,
// not as an old score wearing the current name.
//
// Collector Appeal V3 is available ONLY from the packaged contract. The backend
// publishes no equivalent top-level V3 block: `openingExperience.collectorAppeal`
// is the service payload, not the public contract shape, and reading it here
// would be inventing a second projection of the model in JavaScript.
//
// NOTHING IS COMPUTED HERE
// ------------------------
// Every score, rank, tier and denominator is lifted verbatim. The only
// transformation is reading one of two field names for the same backend value
// (`rankedSetCount` on the contract, `cohortSize` at top level) — a rename the
// backend already performs on itself, not arithmetic.

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function hasContent(value) {
  return Object.keys(toObject(value)).length > 0;
}

/**
 * The first canonical bundle among the given sources.
 *
 * Sources are searched in caller order (typically set-page payload -> Explore
 * target -> merged summary). All three carry the SAME backend objects — one
 * bundle powers every surface — so order only matters while a stale cache and a
 * fresh one briefly coexist.
 */
export function resolveCanonicalRipV7(...sources) {
  for (const source of sources) {
    const safeSource = toObject(source);
    const contract = toObject(safeSource.publicRipContractV7);
    if (hasContent(contract)) {
      return {
        shape: "publicRipContractV7",
        overall: toObject(contract.overallRip),
        financialRip: toObject(contract.financialRip),
        collectorAppeal: toObject(contract.collectorAppeal),
      };
    }
  }

  for (const source of sources) {
    const safeSource = toObject(source);
    const overall = toObject(safeSource.overallRipV7);
    const financial = toObject(safeSource.financialRipV3);
    if (hasContent(overall) || hasContent(financial)) {
      return {
        shape: "topLevelV7",
        overall,
        financialRip: financial,
        // Not derivable from any top-level object. See the module note: an
        // absent Collector Appeal renders unavailable rather than being rebuilt
        // from the service payload or borrowed from V6/V2/CA7.
        collectorAppeal: {},
      };
    }
  }

  return { shape: null, overall: {}, financialRip: {}, collectorAppeal: {} };
}

/**
 * Read one canonical block's public score/rank/tier/cohort quartet.
 *
 * The PUBLIC number is the cohort-relative 0-100 score, which is the production
 * scoring language across the site. The absolute formula output is carried
 * alongside as a diagnostic and is never promoted into `score`: a payload
 * holding only the absolute renders unavailable rather than silently showing a
 * differently-scaled number under the same label.
 */
export function readCanonicalBlock(block) {
  const safeBlock = toObject(block);
  const relative = toNumber(safeBlock.relativeScore);
  return {
    available: relative !== null,
    score: relative,
    relativeScore: relative,
    absoluteScore: toNumber(safeBlock.absoluteScore ?? safeBlock.score),
    rank: toNumber(safeBlock.rank),
    tier: safeBlock.tier ?? null,
    // `rankedSetCount` on the packaged contract, `cohortSize` at top level —
    // the same backend denominator under the two names the backend itself uses.
    cohortSize: toNumber(safeBlock.rankedSetCount ?? safeBlock.cohortSize),
    // When a canonical score is missing the backend says why. That reason is
    // what a surface renders, instead of substituting a legacy score.
    status: safeBlock.status ?? null,
    statusReason: safeBlock.statusReason ?? null,
  };
}

/**
 * True when the canonical Overall RIP V7 headline can be rendered for a target.
 * Used to skip a target entirely (landing spotlight) rather than patch it.
 */
export function hasCanonicalOverallRipV7(...sources) {
  return readCanonicalBlock(resolveCanonicalRipV7(...sources).overall).available;
}
