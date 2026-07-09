"use client";

import SectionLoadingPanel from "@/components/ui/SectionLoadingPanel";
import SectionErrorPanel from "@/components/ui/SectionErrorPanel";

// Reusable section-level loading/error/success boundary. This is the primary
// lever for prioritized progressive rendering: each section of a tab (Set
// Value, Market Movers, RIP Score hero, a Pull Rates table, ...) owns its own
// SectionBoundary keyed to its own fetch status, instead of one tab-wide gate
// blocking everything behind its slowest section. Presentation-only — it does
// not fetch or time anything itself; pair it with useSectionFetchState and/or
// useSectionTiming in the caller.
//
// minHeightClassName is not just cosmetic: it is THE mechanism that keeps
// layout stable as a section moves from loading -> success, so callers must
// size it to that section's real loaded height rather than leaving the
// default.
export default function SectionBoundary({
  status, // "idle" | "loading" | "success" | "error"
  error = null,
  onRetry = null,
  title,
  helper = null,
  errorMessage = null,
  minHeightClassName = "min-h-[16rem]",
  className = "",
  skeleton = null,
  shouldDelayLoader = false,
  delayConfig = {},
  isEmpty = false,
  emptyState = null,
  children,
}) {
  const isLoading = status === "idle" || status === "loading";
  const isError = status === "error";

  return (
    <section aria-busy={isLoading} className={`scroll-mt-24 md:scroll-mt-28 ${className}`.trim()}>
      {isLoading ? (
        skeleton ?? (
          <SectionLoadingPanel
            title={title}
            helper={helper}
            minHeightClassName={minHeightClassName}
            shouldDelay={shouldDelayLoader}
            delayConfig={delayConfig}
          />
        )
      ) : isError ? (
        <SectionErrorPanel
          title={title}
          message={errorMessage || error?.message || "This section couldn't load."}
          onRetry={onRetry}
          minHeightClassName={minHeightClassName}
        />
      ) : isEmpty ? (
        emptyState
      ) : (
        children
      )}
    </section>
  );
}
