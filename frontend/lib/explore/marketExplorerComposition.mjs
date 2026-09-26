// ---------------------------------------------------------------------------
// Composition capability — driven by PUBLISHED metadata, never by "parent".
//
// V2 directory rows publish composition_kind (index | composition |
// index_and_composition | none), availability and constituent_count. A market is
// inspectable only when it publishes a composition and that composition is
// available. `index_and_composition` (the Raw parent) states explicitly that the
// INDEX is chained over Set-level constituents while the DISPLAYED composition is
// the physical card leaves.
//
// Series that carry no composition metadata (legacy V1 parents: Raw, Total
// Sealed from the global snapshot) fall back to the legacy rule: a parent is
// inspectable only if it already carries a published roster.
// ---------------------------------------------------------------------------

const COMPOSITION_KINDS = new Set(["composition", "index_and_composition"]);

export function hasPublishedCompositionMetadata(series) {
  return typeof series?.compositionKind === "string" && series.compositionKind.length > 0;
}

/** { inspectable, source, reason } for one series. */
export function resolveCompositionCapability(series) {
  if (!series) return { inspectable: false, source: "none", reason: null };
  if (hasPublishedCompositionMetadata(series)) {
    if (!COMPOSITION_KINDS.has(series.compositionKind)) {
      return { inspectable: false, source: "surface_v2", reason: "This market publishes an index only; it has no inspectable composition." };
    }
    if (series.availability && series.availability !== "available") {
      return { inspectable: false, source: "surface_v2", reason: series.unavailableReason || "Composition is not available for this market right now." };
    }
    return {
      inspectable: true, source: "surface_v2", reason: null,
      // Stated so the panel can explain that index math and displayed rows differ.
      indexAndComposition: series.compositionKind === "index_and_composition",
    };
  }
  if (series.isParent === true) {
    const inspectable = Boolean(series.currentConstituents);
    // V1 publishes no enumerable roster for a parent market. Say so plainly.
    return { inspectable, source: "legacy_parent", reason: inspectable ? null : `${series.label || "This market"} composition is not available in the current published generation.` };
  }
  return { inspectable: true, source: "legacy", reason: null };
}

/**
 * ONE identity per visible market. The page still receives the legacy global
 * snapshot for overview families (`raw`, `sealedMarket`) while V2 publishes the
 * same parents under the same keys. When both are present the entry that
 * publishes composition metadata (V2) wins, in the position of the first
 * occurrence, so a parent is never drawn or listed twice.
 */
export function unifySeriesByKey(list) {
  const out = [];
  const index = new Map();
  for (const series of list || []) {
    if (!series) continue;
    const key = series.key;
    if (!index.has(key)) { index.set(key, out.length); out.push(series); continue; }
    const at = index.get(key);
    if (hasPublishedCompositionMetadata(series) && !hasPublishedCompositionMetadata(out[at])) out[at] = series;
  }
  return out;
}
