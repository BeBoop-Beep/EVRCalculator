const ASSET_LABELS = Object.freeze({ cards: "Cards", sealed: "Sealed", graded: "Graded" });

const normalize = (value) => String(value || "Market").trim();

/** Canonical asset-aware Explorer label. Identity comes from structured fields, never keys. */
export function formatExplorerMarketLabel(market) {
  const label = normalize(market?.baseLabel || market?.label || market?.displayName);
  const suffix = ASSET_LABELS[String(market?.asset || "").toLowerCase()];
  if (!suffix) return label;
  const normalized = label.toLowerCase().replace(/[\s\-–—]+/g, " ").trim();
  if (normalized.endsWith(suffix.toLowerCase())) return label;
  return `${label} — ${suffix}`;
}
