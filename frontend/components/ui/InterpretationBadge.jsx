"use client";

import { getInterpretationBadgeStyle } from "@/lib/explore/interpretationTone";

export default function InterpretationBadge({
  label,
  rankTier,
  severity,
  className = "",
}) {
  if (!label) {
    return null;
  }

  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.06em]",
        className,
      ].join(" ")}
      style={getInterpretationBadgeStyle({ label, rankTier, severity })}
    >
      {label}
    </span>
  );
}
