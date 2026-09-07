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

/**
 * `chaseAccessibilityValue` reads the nested SET-level authority block
 * (`row.chaseAccessibility.value`) rather than a flat field — mirrors
 * `ProductFamilyRankingsClient.jsx`'s `sortFieldValue` for the same reason:
 * every product sharing a set_id carries the byte-identical backend block
 * (backend/db/services/chase_accessibility_set_ranking.py).
 */
function readSortField(row, key) {
  if (key === "chaseAccessibilityValue") return numeric(row?.chaseAccessibility?.value);
  return numeric(row?.[key]);
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
      const a = readSortField(left, effectiveKey);
      const b = readSortField(right, effectiveKey);
      if (a === null) return b === null ? 0 : 1;
      if (b === null) return -1;
      // Numeric ties intentionally return 0: modern JavaScript's stable sort
      // preserves the backend's authoritative rank order as the tiebreaker.
      return factor * (a - b);
    });
}
