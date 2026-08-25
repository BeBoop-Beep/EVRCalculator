"use client";

import { formatModeScore, SCORE_KIND_PUBLIC } from "@/constants/exploreRankingConfig";
import { getTierTone } from "@/lib/explore/interpretationTone";

export function RipScoreBadge({ score, tier, compact = false, label = "RIP Score" }) {
  const tone = tier ? getTierTone(tier) : null;
  const accent = tone?.accentColor || "var(--border-subtle)";
  const available = score !== null && score !== undefined;
  return (
    <div data-rip-score-badge className={`relative inline-flex flex-col items-center justify-center text-center ${compact ? "h-[3.25rem] w-[3.65rem]" : "h-[3.75rem] w-[4.5rem]"}`}>
      <svg aria-hidden="true" viewBox="0 0 72 60" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible"><polygon points="10,1 62,1 71,11 71,49 62,59 10,59 1,49 1,11" fill="rgba(7,14,25,0.72)" stroke={accent} strokeWidth="1.25" vectorEffect="non-scaling-stroke" /></svg>
      <strong className={`relative ${compact ? "text-xl" : "text-[23px]"} font-bold leading-none tabular-nums text-[var(--text-primary)]`}>{available ? formatModeScore(score, SCORE_KIND_PUBLIC) : "Unavailable"}</strong>
      {available ? <span className="relative text-[9px] text-[var(--text-secondary)]">/ 10</span> : null}
      <span className="mt-1 text-[7px] font-bold uppercase tracking-[0.1em] text-[var(--text-secondary)]">{label}</span>
    </div>
  );
}

export function RipTierMark({ tier }) {
  const tone = tier ? getTierTone(tier) : null;
  return tier ? <span data-rip-tier-mark className="inline-flex flex-col items-center leading-none"><strong className="inline-flex h-9 w-9 items-center justify-center rounded-lg border bg-[var(--surface-page)]/55 text-lg" style={tone ? { color: tone.textColor, borderColor: tone.accentColor } : undefined}>{tier}</strong><span className="mt-1 text-[8px] font-bold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Tier</span></span> : null;
}
