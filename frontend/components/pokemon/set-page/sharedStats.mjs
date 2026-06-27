export function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

export function getFirstNumericMetric(source, keys = []) {
  for (const key of keys) {
    const value = toOptionalNumber(source?.[key]);
    if (value !== null) {
      return { key, value };
    }
  }
  return { key: null, value: null };
}

export function calculatePearsonCorrelation(points) {
  const rows = (Array.isArray(points) ? points : []).filter(
    (point) => toOptionalNumber(point?.x) !== null && toOptionalNumber(point?.y) !== null
  );
  const n = rows.length;
  if (n < 3) return null;

  const meanX = rows.reduce((sum, point) => sum + point.x, 0) / n;
  const meanY = rows.reduce((sum, point) => sum + point.y, 0) / n;
  let numerator = 0;
  let sumXSquared = 0;
  let sumYSquared = 0;
  rows.forEach((point) => {
    const dx = point.x - meanX;
    const dy = point.y - meanY;
    numerator += dx * dy;
    sumXSquared += dx * dx;
    sumYSquared += dy * dy;
  });
  const denominator = Math.sqrt(sumXSquared * sumYSquared);
  return denominator > 0 ? numerator / denominator : null;
}

function rankValues(values) {
  const sorted = values
    .map((value, index) => ({ value, index }))
    .sort((left, right) => left.value - right.value);
  const ranks = Array(values.length).fill(0);
  let index = 0;
  while (index < sorted.length) {
    let end = index;
    while (end + 1 < sorted.length && sorted[end + 1].value === sorted[index].value) {
      end += 1;
    }
    const rank = (index + end + 2) / 2;
    for (let cursor = index; cursor <= end; cursor += 1) {
      ranks[sorted[cursor].index] = rank;
    }
    index = end + 1;
  }
  return ranks;
}

export function calculateSpearmanCorrelation(points) {
  const rows = (Array.isArray(points) ? points : []).filter(
    (point) => toOptionalNumber(point?.x) !== null && toOptionalNumber(point?.y) !== null
  );
  if (rows.length < 3) return null;
  const xRanks = rankValues(rows.map((point) => point.x));
  const yRanks = rankValues(rows.map((point) => point.y));
  return calculatePearsonCorrelation(xRanks.map((x, index) => ({ x, y: yRanks[index] })));
}
