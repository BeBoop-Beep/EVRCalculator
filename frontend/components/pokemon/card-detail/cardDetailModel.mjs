export const PROBABILITY_MILESTONES = Object.freeze([0.5, 0.75, 0.9, 0.95]);

export function validPullProbability(value) {
  const probability = Number(value);
  return Number.isFinite(probability) && probability > 0 && probability <= 1
    ? probability
    : null;
}

export function cumulativePullProbability(probability, packs) {
  const p = validPullProbability(probability);
  const n = Number(packs);
  if (p === null || !Number.isFinite(n) || n < 0) return null;
  if (p === 1) return n === 0 ? 0 : 1;
  return 1 - Math.pow(1 - p, n);
}

export function packsForMilestone(
  probability,
  target,
  practicalLimit = 1_000_000,
) {
  const p = validPullProbability(probability);
  const q = Number(target);
  if (p === null || !Number.isFinite(q) || q <= 0 || q >= 1) return null;
  if (p === 1) return 1;
  const packs = Math.ceil(Math.log1p(-q) / Math.log1p(-p));
  return Number.isSafeInteger(packs) && packs > 0 && packs <= practicalLimit
    ? packs
    : null;
}

export function probabilityMilestones(probability, published = {}) {
  return PROBABILITY_MILESTONES.map((target) => {
    const key = `packsFor${Math.round(target * 100)}PercentChance`;
    const authoritative = Number(published?.[key]);
    const packs =
      Number.isSafeInteger(authoritative) && authoritative > 0
        ? authoritative
        : packsForMilestone(probability, target);
    return { target, label: `${Math.round(target * 100)}%`, packs };
  });
}

export function milestoneXPosition(packs, maxPacks, left = 54, width = 626) {
  const value = Number(packs);
  const max = Number(maxPacks);
  if (!Number.isFinite(value) || value < 0 || !Number.isFinite(max) || max <= 0)
    return null;
  return left + (Math.min(value, max) / max) * width;
}

export function packsAtPlotX(plotX, maxPacks, left = 54, width = 626) {
  const coordinate = Number(plotX);
  const max = Number(maxPacks);
  if (
    !Number.isFinite(coordinate) ||
    !Number.isFinite(max) ||
    max <= 0 ||
    width <= 0
  )
    return null;
  const ratio =
    (Math.max(left, Math.min(left + width, coordinate)) - left) / width;
  return Math.round(ratio * max);
}

export function scorePercent(value) {
  const score = Number(value);
  return Number.isFinite(score) && score >= 0 && score <= 100 ? score : null;
}

export function buildCardParentSetHref(set) {
  const slug = String(set?.slug || "").trim();
  return slug
    ? `/TCGs/Pokemon/Sets/${encodeURIComponent(slug)}`
    : "/TCGs/Pokemon/Sets";
}
