export function optionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function readPublicSetRip(target) {
  const block = target?.setRipV1 || {};
  const scoreAuthority = Object.prototype.hasOwnProperty.call(block, "publicScore")
    ? block.publicScore
    : block.score;
  return {
    publicScore: optionalNumber(scoreAuthority),
    rank: optionalNumber(block.rank),
    tier: block.tier || null,
    cohortSize: optionalNumber(block.cohortSize),
  };
}
