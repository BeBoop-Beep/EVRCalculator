import { RANK_CONFIG } from "../../constants/rankConfig.mjs";

const FALLBACK_COLOR = "rgba(148,163,184,0.72)";

export function normalizeRipTier(tier) {
  const key = String(tier || "").trim().toUpperCase();
  return Object.prototype.hasOwnProperty.call(RANK_CONFIG, key) ? key : null;
}

export function getRipTierPresentation(tier, { strength = "factor" } = {}) {
  const normalized = normalizeRipTier(tier);
  const config = normalized ? RANK_CONFIG[normalized] : null;
  const color = config?.color || FALLBACK_COLOR;
  const alpha = strength === "hero" ? "14%" : strength === "supporting" ? "9%" : "5%";
  return {
    tier: normalized,
    label: normalized ? `${normalized} Tier` : "Tier unavailable",
    color,
    style: {
      "--tier-color": color,
      "--tier-border": `color-mix(in srgb, ${color} ${strength === "hero" ? "38%" : "25%"}, var(--border-subtle))`,
      "--tier-surface": `color-mix(in srgb, ${color} ${alpha}, rgba(2,8,23,0.5))`,
      "--tier-glow": config?.glowColor || "transparent",
      "--tier-track-fill": color,
    },
  };
}
