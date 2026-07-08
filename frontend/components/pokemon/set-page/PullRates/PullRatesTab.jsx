"use client";

import SectionBoundary from "@/components/ui/SectionBoundary";
import SectionErrorBoundary from "@/components/ui/SectionErrorBoundary";
import { useSectionTiming } from "@/hooks/useSectionTiming";
import HitRateSummarySection from "./HitRateSummarySection";
import PullRateTableSection from "./PullRateTableSection";
import SourceReferenceSection from "./SourceReferenceSection";
import AdvancedOddsSection from "./AdvancedOddsSection";

// Quiet placeholder for the 3 sections that aren't the tab's primary/hero
// content — avoids stacking the full branded InDexLogoLoader panel 4 times
// when, today, all 4 sections settle in lockstep off the one existing
// /pull-rates fetch (see the plan note: no backend split for this tab, the
// sources/assumptions fields are permanently empty so a second round trip
// would add latency for zero benefit).
function QuietSkeleton({ minHeightClassName }) {
  return (
    <div
      className={`${minHeightClassName} animate-pulse rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/30`}
      aria-hidden="true"
    />
  );
}

// pullRateAssumptions / pullRatesTabPending / pullRatesPendingTimedOut /
// activePullRatesState are computed in RipStatisticsPageClient.jsx from its
// existing, contract-test-guarded pullRatesState fetch effect (request-key
// dedupe, set-id staleness guard, 8s timeout escape) — deliberately left
// untouched there. This component only owns the render/section-priority
// split, not the fetch itself.
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
      className="scroll-mt-24 space-y-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/70 p-4 md:scroll-mt-28 md:p-5"
    >
      <div>
        <p className="text-base font-semibold text-[var(--text-primary)]">Pull Rate Assumptions</p>
        <p className="mt-0.5 text-sm text-[var(--text-secondary)]">Modeled rarity frequency and specific-card odds used by this simulation.</p>
        <p className="mt-1 text-xs text-[var(--text-tertiary,var(--text-secondary))]">These are modeled estimates, not official Pokémon odds.</p>
      </div>

      <div className="space-y-3">
        {/* Priority 2: main hit-rate summary */}
        <SectionErrorBoundary sectionName="pull-rates-summary" resetKeys={resetKeys} title="Hit Rate Summary" minHeightClassName="min-h-[7rem]">
          <SectionBoundary
            status={status}
            error={errorObject}
            title={pullRatesPendingTimedOut ? "Still loading pull rates…" : "Loading pull rate assumptions…"}
            helper={
              pullRatesPendingTimedOut
                ? "Pull rates are taking longer than expected to load. Refresh the page to retry."
                : "Pulling rarity frequencies and specific-card odds for this set."
            }
            minHeightClassName="min-h-[7rem]"
            isEmpty={isSettledEmpty}
            emptyState={
              <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-4 py-3 text-sm text-[var(--text-secondary)]">
                Pull-rate data coming soon for this set. Modeled odds appear once this set&apos;s pack structure has been configured.
              </p>
            }
          >
            <HitRateSummarySection pullRateAssumptions={pullRateAssumptions} />
          </SectionBoundary>
        </SectionErrorBoundary>

        {/* Priority 3: the full pull-rate table */}
        <SectionErrorBoundary sectionName="pull-rates-table" resetKeys={resetKeys} title="Pull Rate Table" minHeightClassName="min-h-[18rem]">
          <SectionBoundary
            status={status}
            error={errorObject}
            title="Pull Rate Table"
            minHeightClassName="min-h-[18rem]"
            skeleton={isLoading ? <QuietSkeleton minHeightClassName="min-h-[18rem]" /> : null}
          >
            <PullRateTableSection pullRateAssumptions={pullRateAssumptions} />
          </SectionBoundary>
        </SectionErrorBoundary>

        {/* Priority 4: source/reference details (always the same static note today — see SourceReferenceSection) */}
        <SectionErrorBoundary sectionName="pull-rates-sources" resetKeys={resetKeys} title="Source & Reference" minHeightClassName="min-h-[4rem]">
          <SectionBoundary
            status={hasAssumptions || isSettledEmpty ? "success" : status}
            error={errorObject}
            title="Source & Reference"
            minHeightClassName="min-h-[4rem]"
            skeleton={isLoading ? <QuietSkeleton minHeightClassName="min-h-[4rem]" /> : null}
          >
            <SourceReferenceSection />
          </SectionBoundary>
        </SectionErrorBoundary>

        {/* Priority 5: advanced/expanded odds, collapsed by default */}
        <SectionErrorBoundary sectionName="pull-rates-advanced" resetKeys={resetKeys} title="Advanced Odds" minHeightClassName="min-h-[3.5rem]">
          <SectionBoundary
            status={status}
            error={errorObject}
            title="Advanced Odds"
            minHeightClassName="min-h-[3.5rem]"
            skeleton={isLoading ? <QuietSkeleton minHeightClassName="min-h-[3.5rem]" /> : null}
          >
            <AdvancedOddsSection pullRateAssumptions={pullRateAssumptions} />
          </SectionBoundary>
        </SectionErrorBoundary>
      </div>
    </section>
  );
}
