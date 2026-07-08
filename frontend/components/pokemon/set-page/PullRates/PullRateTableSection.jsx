"use client";

import { PullRateTable, PullRateMobileRows, buildGroupsForRender } from "./PullRateAssumptionsCard";

// Priority 3: the main pull-rate table, scoped to the pack_structure group
// (the "basic" model) — hit_rarity_model/special_pack_rules move to
// AdvancedOddsSection.
export default function PullRateTableSection({ pullRateAssumptions }) {
  const groups = buildGroupsForRender(pullRateAssumptions).filter((group) => group.key === "pack_structure");

  if (groups.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-4 py-3 text-sm text-[var(--text-secondary)]">
        Pull-rate data coming soon for this set. Modeled odds appear once this set&apos;s pack structure has been configured.
      </p>
    );
  }

  return (
    <>
      <div className="hidden md:block">
        <PullRateTable groups={groups} />
      </div>
      <div className="md:hidden">
        <PullRateMobileRows groups={groups} />
      </div>
    </>
  );
}
