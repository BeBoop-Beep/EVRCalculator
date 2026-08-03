// Which set each homepage section features, and why.
//
// The homepage used to run on two positional picks — entries[0] for the hero
// and entries[1] for Set Intelligence — which meant the second section was just
// "the runner-up to rip". These selectors give each role its own question:
//
//   OPENING SPOTLIGHT      which set opens best right now  -> published rank #1
//   SET INTELLIGENCE       which set is worth understanding -> published desirability
//
// Both read ALREADY-PUBLISHED fields. Nothing here re-ranks a cohort, recomputes
// a score, or invents a tie-break the backend did not already imply; the
// ordering below is only a presentation choice between published values.
//
// Dependency-free so landingSpotlights.test.mjs can run it under `tsx --test`,
// which cannot resolve the "@/" specifiers the Next bundler uses.

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toList(value) {
  return Array.isArray(value) ? value : [];
}

/**
 * The published set-level desirability for one entry.
 *
 * PRIMARY is `universalSetDesirability.score` — the authoritative Set
 * Desirability lens Explore already ships ("the popularity and depth of the
 * Pokemon subjects a set contains, independent of price"), scored across every
 * set rather than only the simulated cohort.
 *
 * SECONDARY is Collector Appeal (CA7). It is still published and still carries
 * 10% of Overall RIP, but exploreRankingConfig documents it as the retired
 * lens because it needs a modelled pull structure, so it is the backup rather
 * than the lead.
 *
 * A set the backend marked as a desirability FALLBACK is not trusted for this
 * choice at all — a substituted value is not a measurement, and featuring a set
 * on the strength of one would be dressing up a guess.
 */
export function readDesirability(entry) {
  if (entry?.desirabilityIsFallback === true) {
    return { score: null, source: null };
  }

  const universal = toFiniteNumber(entry?.universalDesirabilityScore);
  if (universal !== null) {
    return { score: universal, source: "universalSetDesirability" };
  }

  const collectorAppeal = toFiniteNumber(entry?.collectorAppealScore);
  if (collectorAppeal !== null) {
    return { score: collectorAppeal, source: "collectorAppeal" };
  }

  return { score: null, source: null };
}

/**
 * Everything a set must carry before any homepage section may feature it. A
 * record missing these is skipped, never patched — the homepage would rather
 * show one section fewer than show a half-populated set.
 */
function isRenderable(entry) {
  return Boolean(
    entry &&
      entry.key &&
      entry.name &&
      toFiniteNumber(entry.score) !== null &&
      (entry.logoUrl || entry.symbolUrl)
  );
}

/**
 * ROLE 1 — the set that opens best right now.
 *
 * Reads the backend's own opening rank; it does not sort a cohort to find
 * first place. Rank 1 is required, so when the published ranking is absent or
 * malformed the hero falls to its empty state rather than promoting whatever
 * happened to sort first.
 */
export function selectOpeningSpotlight(entries) {
  return toList(entries).find((entry) => isRenderable(entry) && toFiniteNumber(entry.rank) === 1) || null;
}

/**
 * The set-level data the large Set Intelligence section needs before it can be
 * built around a set: a value to trend, an opening comparison to draw, and a
 * published read to lead with.
 */
function hasSetIntelligenceData(entry) {
  return Boolean(
    isRenderable(entry) &&
      toFiniteNumber(entry.setValue) !== null &&
      toFiniteNumber(entry.packCost) !== null &&
      toFiniteNumber(entry.meanValue) !== null &&
      (entry.decisionLabel || entry.interpretationLabel)
  );
}

/**
 * Deterministic ordering, so the same published payload always produces the
 * same homepage. Highest desirability first, then the documented tie-breaks:
 * newest market date, higher set value, then stable key order.
 */
function compareCandidates(left, right) {
  const leftScore = readDesirability(left).score;
  const rightScore = readDesirability(right).score;
  if (leftScore !== rightScore) return (rightScore ?? -Infinity) - (leftScore ?? -Infinity);

  const leftDate = String(left.setValueAsOf || "");
  const rightDate = String(right.setValueAsOf || "");
  if (leftDate !== rightDate) return rightDate.localeCompare(leftDate);

  const leftValue = toFiniteNumber(left.setValue) ?? -Infinity;
  const rightValue = toFiniteNumber(right.setValue) ?? -Infinity;
  if (leftValue !== rightValue) return rightValue - leftValue;

  return String(left.key).localeCompare(String(right.key));
}

/**
 * ROLE 2 — an ORDERED CANDIDATE LIST for the Set Intelligence spotlight, best
 * first. A list rather than a single set because the last requirement (enough
 * chase-card art) can only be checked after fetching it; the caller walks this
 * list and takes the first candidate whose imagery holds up.
 *
 * The fallback order is the one the brief sets out, and each tier is exhausted
 * before the next begins:
 *   1. highest published desirability, excluding the opening spotlight
 *   2. highest eligible set value, excluding the opening spotlight
 *   3. best remaining opening rank, excluding the opening spotlight
 * Nothing eligible at any tier yields an empty list, and the section renders
 * its empty state — a hardcoded set is never substituted.
 */
export function rankSetIntelligenceCandidates(entries, { excludeKey = null } = {}) {
  const eligible = toList(entries).filter(
    (entry) => hasSetIntelligenceData(entry) && entry.key !== excludeKey
  );

  const withDesirability = eligible.filter((entry) => readDesirability(entry).score !== null);
  const withoutDesirability = eligible.filter((entry) => readDesirability(entry).score === null);

  const byValue = [...withoutDesirability].sort((left, right) => {
    const leftValue = toFiniteNumber(left.setValue) ?? -Infinity;
    const rightValue = toFiniteNumber(right.setValue) ?? -Infinity;
    if (leftValue !== rightValue) return rightValue - leftValue;
    return String(left.key).localeCompare(String(right.key));
  });

  const byOpeningRank = [...eligible].sort((left, right) => {
    const leftRank = toFiniteNumber(left.rank) ?? Infinity;
    const rightRank = toFiniteNumber(right.rank) ?? Infinity;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return String(left.key).localeCompare(String(right.key));
  });

  const ordered = [...[...withDesirability].sort(compareCandidates), ...byValue, ...byOpeningRank];

  const seen = new Set();
  return ordered.filter((entry) => {
    if (seen.has(entry.key)) return false;
    seen.add(entry.key);
    return true;
  });
}
