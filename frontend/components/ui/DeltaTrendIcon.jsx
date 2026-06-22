"use client";

import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import { getDeltaTrendDirection } from "@/lib/explore/marketDeltaWindows.mjs";

export default function DeltaTrendIcon({
  value = null,
  direction = null,
  size = "sm",
  className = "",
  title = null,
}) {
  const resolvedDirection = direction || getDeltaTrendDirection(value);

  if (resolvedDirection !== "up" && resolvedDirection !== "down") {
    return null;
  }

  const sizeClassName = size === "md" ? "text-[0.72em]" : "text-[0.66em]";
  const label = title || (resolvedDirection === "up" ? "Positive change" : "Negative change");

  return (
    <span
      className={["inline-flex flex-none items-center leading-none", sizeClassName, className].filter(Boolean).join(" ")}
      style={{ color: resolvedDirection === "up" ? POSITIVE_VALUE_COLOR : NEGATIVE_VALUE_COLOR }}
      aria-label={label}
      title={label}
    >
      {resolvedDirection === "up" ? "\u25b2" : "\u25bc"}
    </span>
  );
}
