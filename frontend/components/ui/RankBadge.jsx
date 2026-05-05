"use client";

import { RANK_CONFIG } from "@/constants/rankConfig";

function withAlpha(color, alpha) {
  if (typeof color !== "string") {
    return color;
  }

  const rgbaMatch = color.match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[^)]+)?\)$/i);
  if (!rgbaMatch) {
    return color;
  }

  return `rgba(${rgbaMatch[1]},${rgbaMatch[2]},${rgbaMatch[3]},${alpha})`;
}

const SIZE_STYLES = {
  default: {
    className: "gap-1.5 px-2.5 py-0.5 text-[11px]",
    labelOpacity: 0.75,
  },
  supporting: {
    className: "gap-1.5 px-3 py-1 text-[12px]",
    labelOpacity: 0.82,
  },
  hero: {
    className: "gap-2 px-3.5 py-1.5 text-[13px]",
    labelOpacity: 0.9,
  },
};

/**
 * RankBadge — reusable tier badge for any rank display across the app.
 *
 * Props:
 *   rank  — one of "S" | "A" | "B" | "C" | "D" | "F" | null
 *   label — optional prefix string, e.g. "Profit" → renders "Profit: A"
 *   title — optional native tooltip override
 *   subtle — optional boolean to reduce glow/intensity (e.g. for header contexts)
 *
 * All dynamic colors use inline styles to prevent Tailwind purging
 * class strings that are constructed at runtime from config objects.
 */
export default function RankBadge({ rank, label, title: titleProp, subtle = false, size = "default", format = "letter" }) {
  const config = rank ? RANK_CONFIG[rank] : null;
  const sizeStyle = SIZE_STYLES[size] || SIZE_STYLES.default;
  const isHero = size === "hero";
  const rankDisplay = format === "tier" && rank ? `${rank} Tier` : rank;
  const borderAlpha = subtle ? (isHero ? 0.32 : 0.22) : isHero ? 0.46 : 0.3;
  const glowStrength = subtle ? (isHero ? 0.3 : 0.18) : isHero ? 0.46 : 0.27;
  const textColor = isHero ? withAlpha(config?.color, 0.95) : subtle ? withAlpha(config?.color, 0.86) : config?.color;

  /* Unavailable / null rank */
  if (!config) {
    return (
      <span
        className={`inline-flex items-center rounded-full border ${sizeStyle.className}`}
        style={{
          background: isHero ? "rgba(2,8,23,0.72)" : "rgba(2,8,23,0.55)",
          borderColor: subtle ? "rgba(255,255,255,0.1)" : isHero ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.12)",
          color: subtle ? "rgba(203,213,225,0.72)" : isHero ? "rgba(226,232,240,0.9)" : "rgba(148,163,184,0.8)",
          boxShadow: isHero ? "0 0 10px rgba(148,163,184,0.14), inset 0 0 10px rgba(255,255,255,0.03)" : undefined,
        }}
        title={titleProp ?? "Rank unavailable"}
      >
        {label ? <span className="font-medium" style={{ opacity: sizeStyle.labelOpacity }}>{label}:</span> : null}
        <span className="font-bold">—</span>
      </span>
    );
  }

  /* S tier: dark glass pill + gradient text + border glow */
  if (config.gradient) {
    return (
      <span
        className={`inline-flex items-center rounded-full border ${sizeStyle.className}`}
        style={{
          background: isHero ? "rgba(2,8,23,0.72)" : "rgba(2,8,23,0.6)",
          borderColor: subtle ? "rgba(192,132,252,0.35)" : isHero ? "rgba(192,132,252,0.68)" : "rgba(192,132,252,0.55)",
          boxShadow: subtle
            ? `0 0 3px 0px ${withAlpha(config.glowColor, 0.75)}`
            : isHero
            ? `0 0 8px 0px ${withAlpha(config.glowColor, 0.82)}, inset 0 0 8px rgba(192,132,252,0.09)`
            : `0 0 5px 0px ${withAlpha(config.glowColor, 0.78)}, inset 0 0 4px rgba(192,132,252,0.06)`,
        }}
        title={titleProp ?? "S Tier — Top 10%"}
      >
        {label ? (
          <span
            className="font-medium"
            style={{ color: isHero ? "rgba(216,180,254,0.9)" : "rgba(192,132,252,0.75)", opacity: sizeStyle.labelOpacity }}
          >
            {label}:
          </span>
        ) : null}
        {format === "tier" ? (
          <span className="font-bold tracking-wide" style={{ color: textColor }}>
            {rankDisplay}
          </span>
        ) : (
          <span
            className="font-bold tracking-wide"
            style={{
              background: config.gradientText,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            S
          </span>
        )}
      </span>
    );
  }

  /* A – F tiers: dark glass pill + colored border + colored text */
  return (
    <span
      className={`inline-flex items-center rounded-full border ${sizeStyle.className}`}
      style={{
        background: isHero ? "rgba(2,8,23,0.74)" : subtle ? "rgba(2,8,23,0.58)" : "rgba(2,8,23,0.55)",
        borderColor: withAlpha(config.color, borderAlpha),
        color: textColor,
        boxShadow: `0 0 ${isHero ? 8 : 5}px 0px ${withAlpha(config.color, glowStrength)}, inset 0 0 ${isHero ? 8 : 4}px ${withAlpha(config.color, isHero ? 0.06 : 0.03)}`,
      }}
      title={titleProp ?? `${rank} Tier`}
    >
      {label ? (
        <span className="font-medium" style={{ opacity: sizeStyle.labelOpacity }}>
          {label}:
        </span>
      ) : null}
      <span className="font-bold tracking-wide">{rankDisplay}</span>
    </span>
  );
}

