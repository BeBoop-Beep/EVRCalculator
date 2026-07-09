"use client";

import { PullRateTable, PullRateMobileRows, buildGroupsForRender } from "./PullRateAssumptionsCard";

// Priority 5: hit_rarity_model + special_pack_rules groups — collapsed by
// default (native <details>, matching PullRateAssumptionsCard's own
// non-embedded pattern) so this deliberately-lower-priority content doesn't
// compete with the basic table for attention.
export default function AdvancedOddsSection({ pullRateAssumptions }) {
  const groups = buildGroupsForRender(pullRateAssumptions).filter((group) => group.key !== "pack_structure");

  if (groups.length === 0) {
    return null;
  }

  return (
    <details className="group rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/40 p-3">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-[var(--text-primary)]">
        Advanced &amp; Special-Pack Odds
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className="h-4 w-4 flex-none text-[var(--text-secondary)] transition-transform duration-150 group-open:rotate-180"
          fill="currentColor"
        >
          <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
        </svg>
      </summary>
      <div className="mt-3 space-y-3">
        <div className="hidden md:block">
          <PullRateTable groups={groups} />
        </div>
        <div className="md:hidden">
          <PullRateMobileRows groups={groups} />
        </div>
      </div>
    </details>
  );
}
