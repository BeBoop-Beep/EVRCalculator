const CONTRACT = "opening_outcome_profile_v1";
const METHOD = "opening_outcome_profile_research_v1";
const finite = (value) => value !== null && value !== "" && Number.isFinite(Number(value)) ? Number(value) : null;

export function selectOpeningOutcomeProfileV1(value, calculationRunId) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  if (value.contractVersion !== CONTRACT || value.researchMethodVersion !== METHOD) return null;
  if (!calculationRunId || String(value.calculationRunId || "") !== String(calculationRunId)) return null;
  const buckets = Array.isArray(value.buckets) ? value.buckets.map((row) => ({
    key: String(row?.key || ""), label: String(row?.label || ""),
    floorRatio: finite(row?.floorRatio), ceilingRatio: row?.ceilingRatio === null ? null : finite(row?.ceilingRatio),
    probability: finite(row?.probability), occurrenceCount: finite(row?.occurrenceCount),
    interpretation: String(row?.interpretation || ""),
  })).filter((row) => row.key && row.label && row.floorRatio !== null && row.probability !== null && row.probability >= 0 && row.probability <= 1) : [];
  if (!buckets.length || Math.abs(buckets.reduce((sum, row) => sum + row.probability, 0) - 1) > 1e-6) return null;
  const cumulativeProbabilities = Array.isArray(value.cumulativeProbabilities) ? value.cumulativeProbabilities.map((row) => ({
    key: String(row?.key || ""), label: String(row?.label || ""), probability: finite(row?.probability),
    thresholdRatio: finite(row?.thresholdRatio), direction: String(row?.direction || ""),
  })).filter((row) => row.key && row.probability !== null) : [];
  return { ...value, buckets, cumulativeProbabilities };
}

export function formatOutcomePercent(value) {
  const number = finite(value);
  return number === null ? "Unavailable" : new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(number);
}

export function buildOutcomeProfileViewModel(profile) {
  if (!profile?.buckets?.length) return null;
  const sum = (predicate) => profile.buckets.filter(predicate).reduce((total, row) => total + row.probability, 0);
  const groups = [
    { key: "under-half", label: "Under half back", probability: sum((row) => row.ceilingRatio !== null && row.ceilingRatio <= .5) },
    { key: "half-to-cost", label: "Half to pack cost", probability: sum((row) => row.floorRatio >= .5 && row.ceilingRatio !== null && row.ceilingRatio <= 1) },
    { key: "one-to-two", label: "Pack cost to 2Ã—", probability: sum((row) => row.floorRatio >= 1 && row.ceilingRatio !== null && row.ceilingRatio <= 2) },
    { key: "two-plus", label: "2Ã— or more", probability: sum((row) => row.floorRatio >= 2) },
  ];
  if (Math.abs(groups.reduce((total, row) => total + row.probability, 0) - 1) > 1e-6) return null;
  const cumulative = Object.fromEntries((profile.cumulativeProbabilities || []).map((row) => [row.key, row.probability]));
  return { groups, details: profile.buckets, cumulative };
}
