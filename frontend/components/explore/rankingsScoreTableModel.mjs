const numeric = (value) => Number.isFinite(Number(value)) ? Number(value) : null;

export function insertBenchmarkReference(rows = [], referenceScore = 5) {
  const reference = { kind: "reference", id: "pokemon-overall-average", score: referenceScore };
  const items = rows.map((row) => ({ kind: "entity", ...row }));
  const index = items.findIndex((row) => {
    const score = numeric(row?.metric?.score);
    return score !== null && score < referenceScore;
  });
  if (index < 0) return [...items, reference];
  return [...items.slice(0, index), reference, ...items.slice(index)];
}

export function canonicalMetricRows(rows = [], metricKey = "overall", query = "", eraFilter = null) {
  const needle = String(query || "").trim().toLocaleLowerCase();
  const era = String(eraFilter || "").trim().toLocaleLowerCase();
  return rows
    .filter((row) => !era || String(row?.era?.eraName || "").toLocaleLowerCase() === era)
    .filter((row) => !needle || String(row?.name || "").toLocaleLowerCase().includes(needle))
    .map((row) => ({ id: String(row.entityId), row, metric: row?.[metricKey] || {} }))
    .sort((left, right) => {
      const leftRank = numeric(left.metric?.rank), rightRank = numeric(right.metric?.rank);
      if (leftRank !== null && rightRank !== null && leftRank !== rightRank) return leftRank - rightRank;
      if (leftRank !== null) return -1;
      if (rightRank !== null) return 1;
      return String(left.row?.name || "").localeCompare(String(right.row?.name || ""));
    });
}
