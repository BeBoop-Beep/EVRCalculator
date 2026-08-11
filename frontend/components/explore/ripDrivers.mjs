// HELPS / HURTS / RESULT composition for the set-level RIP page.
//
// The two published drivers of the canonical Overall RIP — Financial RIP V3
// ("Financial Quality") and Collector Appeal V3 — are compared against EACH
// OTHER on their cohort standing to decide which one is comparatively lifting
// the set and which one is holding it back. Nothing here is hardcoded per
// metric: whichever driver ranks materially better is the one that HELPS, so
// Financial is not always Helps and Collector is not always Helps.
//
// MATERIALITY
// -----------
// A one-rank difference is not a causal divide. Two drivers are treated as
// materially different only when their rank gap clears
// `max(2, ceil(cohortSize * 0.1))` — i.e. roughly a decile of the cohort, with
// a floor so tiny cohorts still need more than a hair's separation. Below that
// the block reports a BALANCED profile (stronger / secondary driver) instead of
// manufacturing a helps/hurts narrative.
//
// Bars visualise COHORT STANDING, not the absolute score, because the number
// printed beside them ("#3 of 22") is the same quantity. A driver ranked first
// fills the track; last fills a sliver.

const FINANCIAL = { key: "financial", label: "Financial Quality", icon: "shield", role: "financial" };
const COLLECTOR = { key: "collector", label: "Collector Appeal", icon: "star", role: "collector" };

export function materialRankGap(cohortSize) {
  const cohort = Number(cohortSize);
  if (!Number.isFinite(cohort) || cohort <= 0) return 3;
  return Math.max(2, Math.ceil(cohort * 0.1));
}

function standing(block) {
  const rank = rankOf(block);
  const cohort = Number(block?.cohortSize);
  if (!Number.isFinite(rank) || !Number.isFinite(cohort) || cohort <= 0) return null;
  return Math.max(4, Math.min(100, ((cohort - rank + 1) / cohort) * 100));
}

function driver(descriptor, block, standingLabel) {
  return {
    ...descriptor,
    standingLabel,
    score: block?.absoluteScore ?? null,
    rank: block?.rank ?? null,
    cohortSize: block?.cohortSize ?? null,
    barPercent: standing(block),
  };
}

/**
 * @returns {{mode: "contrast"|"balanced"|"unavailable", drivers: object[], takeaway: string}}
 */
// `Number(null)` is 0, which would read as a first-place rank, so an absent
// rank must be rejected before it is ever coerced.
function rankOf(block) {
  const rank = block?.rank;
  if (rank === null || rank === undefined || rank === "") return NaN;
  return Number(rank);
}

export function buildRipDrivers({ financial = {}, collector = {}, overall = {} } = {}) {
  const financialRank = rankOf(financial);
  const collectorRank = rankOf(collector);

  if (!Number.isFinite(financialRank) || !Number.isFinite(collectorRank)) {
    return {
      mode: "unavailable",
      drivers: [driver(FINANCIAL, financial, "Driver"), driver(COLLECTOR, collector, "Driver")],
      takeaway: "The canonical model inputs are unavailable, so no comparative driver is stated.",
    };
  }

  const cohortSize = Number(collector?.cohortSize) || Number(financial?.cohortSize) || null;
  const threshold = materialRankGap(cohortSize);
  const gap = collectorRank - financialRank; // negative → collector ranks better

  const collectorLeads = gap < 0;
  const [strong, weak] = collectorLeads ? [COLLECTOR, FINANCIAL] : [FINANCIAL, COLLECTOR];
  const [strongBlock, weakBlock] = collectorLeads ? [collector, financial] : [financial, collector];

  if (Math.abs(gap) >= threshold) {
    return {
      mode: "contrast",
      drivers: [driver(strong, strongBlock, "Helps"), driver(weak, weakBlock, "Hurts")],
      takeaway: collectorLeads
        ? "Collector appeal meaningfully lifts this set despite weaker opening economics."
        : "Stronger opening economics carry this set despite weaker collector appeal.",
    };
  }

  const overallRank = rankOf(overall);
  const overallCohort = Number(overall?.cohortSize);
  const bothStrong =
    Number.isFinite(overallRank) &&
    Number.isFinite(overallCohort) &&
    overallCohort > 0 &&
    overallRank <= Math.max(3, Math.ceil(overallCohort * 0.25));

  return {
    mode: "balanced",
    drivers: [driver(strong, strongBlock, "Stronger driver"), driver(weak, weakBlock, "Secondary driver")],
    takeaway: bothStrong
      ? "Both financial quality and collector appeal support this set's high relative rank."
      : "This set has a balanced profile, with no single dominant driver behind its rank.",
  };
}
