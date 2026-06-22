"use client";

import { RANK_CONFIG } from "@/constants/rankConfig";
import { getTierTone } from "@/lib/explore/interpretationTone";

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
    className: "gap-2 px-4 py-2 text-[14px]",
    labelOpacity: 0.9,
  },
};

export default function RankBadge({ rank, label, title: titleProp, subtle = false, size = "default", format = "letter" }) {
  const config = rank ? RANK_CONFIG[rank] : null;
  const tone = rank ? getTierTone(rank) : null;
  const sizeStyle = SIZE_STYLES[size] || SIZE_STYLES.default;
  const isHero = size === "hero";
  const rankDisplay = format === "tier" && rank ? `${rank} Tier` : rank;

  if (!config) {
    return (
      <span
        className={`inline-flex items-center rounded-full border ${sizeStyle.className}`}
        style={{
          background: isHero ? "rgba(2,8,23,0.72)" : "rgba(2,8,23,0.55)",
          borderColor: subtle ? "rgba(255,255,255,0.1)" : isHero ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.12)",
          color: subtle ? "rgba(203,213,225,0.72)" : isHero ? "rgba(226,232,240,0.9)" : "rgba(148,163,184,0.8)",
          boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.035)",
        }}
        title={titleProp ?? "Rank unavailable"}
      >
        {label ? <span className="font-medium" style={{ opacity: sizeStyle.labelOpacity }}>{label}:</span> : null}
        <span className="font-semibold">-</span>
      </span>
    );
  }

  const accentColor = tone?.accentColor || config.color;
  const textColor = tone?.textColor || (isHero ? withAlpha(config.color, 0.95) : subtle ? withAlpha(config.color, 0.86) : config.color);
  const borderColor = tone?.borderColor || withAlpha(config.color, subtle ? 0.2 : 0.26);
  const background = tone?.badgeBackground || (isHero ? "rgba(2,8,23,0.72)" : "rgba(2,8,23,0.58)");

  return (
    <span
      className={`inline-flex items-center rounded-full border ${sizeStyle.className}`}
      style={{
        background,
        borderColor,
        color: textColor,
        boxShadow: `inset 0 0 0 1px ${withAlpha(accentColor, 0.04)}`,
      }}
      title={titleProp ?? `${rank} Tier`}
    >
      {label ? (
        <span className="font-medium" style={{ opacity: sizeStyle.labelOpacity }}>
          {label}:
        </span>
      ) : null}
      {config.gradient && format !== "tier" ? (
        <span
          className="font-semibold tracking-wide"
          style={{
            background: config.gradientText,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          {rankDisplay}
        </span>
      ) : (
        <span className="font-semibold tracking-wide">{rankDisplay}</span>
      )}
    </span>
  );
}
