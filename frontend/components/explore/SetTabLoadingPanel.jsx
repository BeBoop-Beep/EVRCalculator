'use client';

import InDexLogoLoader from "@/components/brand/InDexLogoLoader";

// Shared branded loading panel for set-detail tabs (Phase 9D.2). Every tab
// (Overview, Cards, Pull Rates, Insights) shows this one panel while its
// critical data assets are still loading, so tab switches read as one
// deliberate branded moment instead of four different skeleton treatments.
// It reuses the exact inDex logo + three-dot loader from the route-level
// loading screens (InDexLogoLoader) — never a generic circular spinner.
// This is only for critical tab data: lazy per-card image loading keeps its
// card-shaped placeholders and must not route through this panel.
export default function SetTabLoadingPanel({
  title,
  helper = null,
  minHeightClassName = "min-h-[24rem]",
  className = "",
  compactMobile = false,
}) {
  if (compactMobile) {
    return (
      <section aria-busy="true" className={`scroll-mt-24 md:scroll-mt-28 ${className}`.trim()}>
        <div
          className={`hidden ${minHeightClassName} flex-col items-center justify-center gap-1.5 rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(15,23,42,0.78),rgba(2,6,23,0.62))] p-8 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_18px_44px_rgba(2,6,23,0.22)] desk:flex`}
        >
          <InDexLogoLoader
            fullScreen={false}
            label={title}
            shouldDelay={false}
            isLoading={true}
            className="index-loader-shell--embedded"
          />
          <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
          {helper ? (
            <p className="max-w-sm text-xs leading-relaxed text-[var(--text-secondary)]">{helper}</p>
          ) : null}
        </div>

        <div className="desk:hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4">
          <div className="space-y-2.5 motion-safe:animate-pulse motion-reduce:animate-none" aria-hidden="true">
            <div className="h-4 w-32 rounded bg-[var(--surface-page)]/75" />
            <div className="h-11 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/55" />
            <div className="h-10 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/50" />
            <div className="h-10 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/50" />
            <div className="h-10 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/50" />
          </div>
          <p className="mt-3 text-xs leading-relaxed text-[var(--text-secondary)]">{helper || title}</p>
        </div>
      </section>
    );
  }

  return (
    <section aria-busy="true" className={`scroll-mt-24 md:scroll-mt-28 ${className}`.trim()}>
      <div
        className={`flex ${minHeightClassName} flex-col items-center justify-center gap-1.5 rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(15,23,42,0.78),rgba(2,6,23,0.62))] p-8 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_18px_44px_rgba(2,6,23,0.22)]`}
      >
        <InDexLogoLoader
          fullScreen={false}
          label={title}
          shouldDelay={false}
          isLoading={true}
          className="index-loader-shell--embedded"
        />
        <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
        {helper ? (
          <p className="max-w-sm text-xs leading-relaxed text-[var(--text-secondary)]">{helper}</p>
        ) : null}
      </div>
    </section>
  );
}
