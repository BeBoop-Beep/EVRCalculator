"use client";

import SectionBoundary from "@/components/ui/SectionBoundary";
import SectionErrorBoundary from "@/components/ui/SectionErrorBoundary";
import { useSectionTiming } from "@/hooks/useSectionTiming";
import PullRateAssumptionsTable from "./PullRateAssumptionsTable";

// pullRateAssumptions / pullRatesTabPending / pullRatesPendingTimedOut /
// activePullRatesState are computed in RipStatisticsPageClient.jsx from its
// existing, contract-test-guarded pullRatesState fetch effect (request-key
// dedupe, set-id staleness guard, 8s timeout escape) — deliberately left
// untouched there. This component only owns the render, not the fetch.
//
// The tab is now a single section: title + one compact quick-reference table.
// The previous 4-section split (hit-rate summary cards, a pack-structure-only
// table, a source-reference note, and a collapsed advanced-odds accordion) was
// collapsed into one always-visible table, so there is one loading/error
// boundary rather than four.
export default function PullRatesTab({
  pullRateAssumptions,
  pullRatesTabPending,
  pullRatesPendingTimedOut,
  activePullRatesState,
  resolvedSetResourceId,
}) {
  const hasAssumptions = Boolean(pullRateAssumptions);
  const isLoading = !hasAssumptions && pullRatesTabPending;
  const isError = !hasAssumptions && !pullRatesTabPending && activePullRatesState.status === "error";
  const isSettledEmpty = !hasAssumptions && !pullRatesTabPending && !isError;

  const status = hasAssumptions ? "success" : isError ? "error" : isLoading ? "loading" : "success";
  const errorObject = activePullRatesState.error ? new Error(activePullRatesState.error) : null;
  const resetKeys = [resolvedSetResourceId];

  useSectionTiming("criticalHero", status, { setId: resolvedSetResourceId, tab: "pull-rates" });

  return (
    <section
      id="set-detail-pull-rates"
      className="set-glass-surface scroll-mt-24 space-y-3 rounded-xl border p-4 md:scroll-mt-28 md:p-5"
    >
      <p className="text-base font-semibold text-[var(--text-primary)]">Pull Rate Assumptions</p>

      <SectionErrorBoundary sectionName="pull-rates-table" resetKeys={resetKeys} title="Pull Rate Assumptions" minHeightClassName="min-h-[12rem]">
        <SectionBoundary
          status={status}
          error={errorObject}
          title={pullRatesPendingTimedOut ? "Still loading pull rates…" : "Loading pull rate assumptions…"}
          helper={
            pullRatesPendingTimedOut
              ? "Pull rates are taking longer than expected to load. Refresh the page to retry."
              : "Pulling rarity frequencies and specific-card odds for this set."
          }
          minHeightClassName="min-h-[12rem]"
          isEmpty={isSettledEmpty}
          emptyState={
            <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-4 py-3 text-sm text-[var(--text-secondary)]">
              Pull-rate data coming soon for this set. Modeled odds appear once this set&apos;s pack structure has been configured.
            </p>
          }
        >
          <PullRateAssumptionsTable pullRateAssumptions={pullRateAssumptions} />
        </SectionBoundary>
      </SectionErrorBoundary>
    </section>
  );
}
