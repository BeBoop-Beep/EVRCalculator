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
//
// ONE PUBLIC SCORE, ONE NAME
// --------------------------
// `readCanonicalBlock` returns `publicScore` (the backend cohort-relative 0-100
// value) and `modelScore` (the fixed-anchor formula output). It deliberately
// does NOT return a generic `score`: that key used to mean the relative value
// here and the absolute value in the Financial RIP / Collector Appeal
// selectors, which is the structural defect behind one set showing two
// different Collector Appeal numbers on one page.

// Marks an object as the OUTPUT of resolveCanonicalRipV7 rather than one of its
// raw inputs. A resolved bundle is accepted anywhere a source is, and resolving
// it again returns it unchanged — see the idempotence note on the resolver.
const CANONICAL_BUNDLE = Symbol.for("evr.canonicalRipV7.bundle");

export function isCanonicalRipBundle(value) {
  return Boolean(value && typeof value === "object" && value[CANONICAL_BUNDLE] === true);
}

function bundle(shape, overall, financialRip, collectorAppeal) {
  return {
    [CANONICAL_BUNDLE]: true,
    shape,
    overall,
    financialRip,
    collectorAppeal,
  };
}

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
 *
 * IDEMPOTENCE — WHY A BUNDLE IS A VALID SOURCE
 * --------------------------------------------
 * The set page resolves ONCE and hands the result down, so the hero, the
 * Overview summary, the Insights headline, Financial RIP and Collector Appeal
 * all read the same bundle and cannot land on different sources. Selectors
 * still call this function, so passing them the already-resolved bundle must
 * return that same bundle rather than searching it for a raw `publicRipContractV7`
 * key it does not have (which would resolve to "unavailable" and blank every
 * downstream surface). A bundle short-circuits, and it wins over any later
 * source, because it IS the decision those sources were consulted to make.
 */
export function resolveCanonicalRipV7(...sources) {
  for (const source of sources) {
    if (isCanonicalRipBundle(source)) return source;
  }

  for (const source of sources) {
    const safeSource = toObject(source);
    const contract = toObject(safeSource.publicRipContractV7);
    if (hasContent(contract)) {
      return bundle(
        "publicRipContractV7",
        toObject(contract.overallRip),
        { ...toObject(contract.financialRip), audit: toObject(contract.audit) },
        toObject(contract.collectorAppeal)
      );
    }
  }

  for (const source of sources) {
    const safeSource = toObject(source);
    const overall = toObject(safeSource.overallRipV7);
    const financial = toObject(safeSource.financialRipV3);
    if (hasContent(overall) || hasContent(financial)) {
      // Not derivable from any top-level object. See the module note: an
      // absent Collector Appeal renders unavailable rather than being rebuilt
      // from the service payload or borrowed from V6/V2/CA7.
      return bundle("topLevelV7", overall, financial, {});
    }
  }

  return bundle(null, {}, {}, {});
}

/**
 * Read one canonical block into the PUBLIC view of that metric.
 *
 * ONE PUBLIC NUMBER, NAMED FOR WHAT IT IS
 * ---------------------------------------
 * `publicScore` is the cohort-relative 0-100 score and is the ONLY value a
 * normal product surface may render for RIP Score, Financial RIP or Collector
 * Appeal. It is deliberately not called `score`.
 *
 * A generic `.score` used to be returned here, aliased to `relativeScore`, while
 * `financialRipV3Selector` and `collectorAppealBreakdownSelector` returned a
 * `.score` aliased to the ABSOLUTE fixed-anchor value. One property name, two
 * scales, decided by which module a component happened to import — that is how
 * the same set rendered Collector Appeal as 53.2 in one section and 95.9 in
 * another. There is no `score` key on this object any more, so the ambiguity is
 * not expressible.
 *
 * `modelScore` is the fixed-anchor formula output. It is retained because it is
 * the real model number and audit, Research and regression work need it — but
 * it is named so that no reader mistakes it for a public one, and it is never
 * promoted into `publicScore`. A payload holding only the absolute renders
 * unavailable rather than silently showing a differently-scaled number under a
 * public label.
 */
export function readCanonicalBlock(block) {
  const safeBlock = toObject(block);
  const relative = toNumber(safeBlock.relativeScore);
  return {
    available: relative !== null,
    // THE public value. Cohort-relative 0-100, backend-computed.
    publicScore: relative,
    relativeScore: relative,
    // INTERNAL. Fixed-anchor model output; never rendered on a normal surface.
    modelScore: toNumber(safeBlock.absoluteScore ?? safeBlock.score),
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
 * The one sentence that explains the public 0-100 scale wherever it is shown.
 *
 * Stated in product language, not as a formula: the normalization equation
 * belongs in Research, not in a metric tooltip. Exported from the canonical
 * reader so every surface quotes the same wording.
 */
export const PUBLIC_SCORE_SCALE_NOTE =
  "Scores are standardized against currently ranked sets; 100 represents the strongest set in the current comparison group.";

/**
 * True when the canonical Overall RIP V7 headline can be rendered for a target.
 * Used to skip a target entirely (landing spotlight) rather than patch it.
 */
export function hasCanonicalOverallRipV7(...sources) {
  return readCanonicalBlock(resolveCanonicalRipV7(...sources).overall).available;
}
