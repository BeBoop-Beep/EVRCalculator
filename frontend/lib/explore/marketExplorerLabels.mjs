const ASSET_LABELS = Object.freeze({ cards: "Cards", sealed: "Sealed", graded: "Graded" });

const normalize = (value) => String(value || "Market").trim();

/** Canonical asset-aware Explorer label. Identity comes from structured fields, never keys. */
export function formatExplorerMarketLabel(market) {
  const label = normalize(market?.baseLabel || market?.label || market?.displayName);
  const asset = String(market?.asset || "").toLowerCase();
  const suffix = ASSET_LABELS[asset];
  if (!suffix) return label;
  if (String(market?.market_type || market?.marketType || "").toLowerCase() === "set") {
    const suffixLabel = asset === "cards" ? "Card Market" : asset === "sealed" ? "Sealed Market" : `${suffix} Market`;
    const base = label.replace(/\s+(?:—|-)?\s*(?:Cards?|Sealed|Graded)(?:\s+Market)?$/i, "").trim();
    return `${base} ${suffixLabel}`;
  }
  const normalized = label.toLowerCase().replace(/[\s\-–—]+/g, " ").trim();
  if (normalized.endsWith(suffix.toLowerCase())) return label;
  return `${label} — ${suffix}`;
}
