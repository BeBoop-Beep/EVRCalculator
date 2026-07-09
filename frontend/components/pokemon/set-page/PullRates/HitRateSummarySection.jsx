"use client";

import { selectPullRateHeadline } from "./pullRateSummarySelector.mjs";

// Priority 2: the main hit-rate summary, shown before the full table. Purely
// derived client-side from the same pullRateAssumptions payload the table
// uses (see pullRateSummarySelector.mjs) — no separate fetch.
export default function HitRateSummarySection({ pullRateAssumptions }) {
  const headline = selectPullRateHeadline(pullRateAssumptions);

  if (!headline) {
    return null;
  }

  return (
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 p-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Tracked Rarities</p>
        <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{headline.trackedRarityCount}</p>
      </div>
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 p-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Chase Slot</p>
        <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{headline.headlineRarityLabel || "—"}</p>
        <p className="text-xs text-[var(--text-secondary)]">{headline.headlinePullFrequency}</p>
      </div>
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 p-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Specific Card Odds</p>
        <p className="mt-1 text-lg font-semibold text-[var(--accent)]">{headline.headlineSpecificOdds || "—"}</p>
      </div>
    </div>
  );
}
