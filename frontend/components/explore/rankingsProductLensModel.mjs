export function normalizeOverallProductResult(value) {
  if (!value || value.available !== true || !Array.isArray(value.rows)) {
    return { available: false, reason: value?.reason || "publication_unavailable", rows: [], availableBudgets: [] };
  }
  return value;
}

function numeric(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function sortProductRankingRows(rows, query, sortKey, direction, overall) {
  const needle = String(query || "").trim().toLowerCase();
  const factor = direction === "asc" ? 1 : -1;
  const effectiveKey = overall && sortKey === "marketPrice" ? "unitPrice" : sortKey;
  return (Array.isArray(rows) ? rows : [])
    .filter((row) => !needle || [row?.productName, row?.setName]
      .some((value) => String(value || "").toLowerCase().includes(needle)))
    .slice()
    .sort((left, right) => {
      if (effectiveKey === "alphabetical") {
        return factor * (
          String(left?.productName || "").localeCompare(String(right?.productName || ""), "en", { sensitivity: "base" }) ||
          String(left?.setName || "").localeCompare(String(right?.setName || ""), "en", { sensitivity: "base" }) ||
          String(left?.sealedProductId || "").localeCompare(String(right?.sealedProductId || ""))
        );
      }
      const a = numeric(left?.[effectiveKey]);
      const b = numeric(right?.[effectiveKey]);
      if (a === null) return b === null ? 0 : 1;
      if (b === null) return -1;
      return factor * (a - b);
    });
}
