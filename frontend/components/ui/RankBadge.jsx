"use client";

import { RANK_CONFIG } from "@/constants/rankConfig";

/**
 * RankBadge — reusable tier badge for any rank display across the app.
 *
 * Props:
 *   rank  — one of "S" | "A" | "B" | "C" | "D" | "F" | null
 *   label — optional prefix string, e.g. "Profit" → renders "Profit: A"
 *   title — optional native tooltip override
 *
 * All dynamic colors use inline styles to prevent Tailwind purging
 * class strings that are constructed at runtime from config objects.
 */
export default function RankBadge({ rank, label, title: titleProp }) {
  const config = rank ? RANK_CONFIG[rank] : null;

  /* Unavailable / null rank */
  if (!config) {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs"
        style={{
          background: "rgba(2,8,23,0.55)",
          borderColor: "rgba(255,255,255,0.12)",
          color: "rgba(148,163,184,0.8)",
        }}
        title={titleProp ?? "Rank unavailable"}
      >
        {label ? <span className="font-medium opacity-75">{label}:</span> : null}
        <span className="font-bold">—</span>
      </span>
    );
  }

  /* S tier: dark glass pill + gradient text + border glow */
  if (config.gradient) {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs"
        style={{
          background: "rgba(2,8,23,0.6)",
          borderColor: "rgba(192,132,252,0.55)",
          boxShadow: `0 0 10px 1px ${config.glowColor}, inset 0 0 6px rgba(192,132,252,0.08)`,
        }}
        title={titleProp ?? "S Tier — Top 10%"}
      >
        {label ? (
          <span
            className="font-medium"
            style={{ color: "rgba(192,132,252,0.75)" }}
          >
            {label}:
          </span>
        ) : null}
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
      </span>
    );
  }

  /* A – F tiers: dark glass pill + colored border + colored text */
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs"
      style={{
        background: "rgba(2,8,23,0.55)",
        borderColor: config.color.replace(/[^,]+\)$/, "0.35)"),
        color: config.color,
        boxShadow: config.glowColor
          ? `0 0 8px 1px ${config.glowColor}`
          : undefined,
      }}
      title={titleProp ?? `${rank} Tier`}
    >
      {label ? (
        <span className="font-medium" style={{ opacity: 0.75 }}>
          {label}:
        </span>
      ) : null}
      <span className="font-bold tracking-wide">{rank}</span>
    </span>
  );
}

