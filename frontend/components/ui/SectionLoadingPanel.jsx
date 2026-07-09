"use client";

import InDexLogoLoader from "@/components/brand/InDexLogoLoader";

// Generic, page-agnostic evolution of components/explore/SetTabLoadingPanel.jsx
// (which stays in place for its existing whole-tab usages). This version is
// meant for a single SECTION of a tab rather than an entire tab, so callers
// are expected to pass a minHeightClassName sized to that section's own
// typical loaded height — that per-section sizing is what actually prevents
// layout shift as sections resolve independently. Reuses the exact inDex
// logo + three-dot loader (InDexLogoLoader) — never a generic spinner.
export default function SectionLoadingPanel({
  title,
  helper = null,
  minHeightClassName = "min-h-[16rem]",
  className = "",
  shouldDelay = false,
  delayConfig = {},
}) {
  return (
    <div
      className={`flex ${minHeightClassName} flex-col items-center justify-center gap-1.5 rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(15,23,42,0.78),rgba(2,6,23,0.62))] p-8 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_18px_44px_rgba(2,6,23,0.22)] ${className}`.trim()}
    >
      <InDexLogoLoader
        fullScreen={false}
        label={title}
        shouldDelay={shouldDelay}
        delayConfig={delayConfig}
        isLoading={true}
        className="index-loader-shell--embedded"
      />
      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
      {helper ? (
        <p className="max-w-sm text-xs leading-relaxed text-[var(--text-secondary)]">{helper}</p>
      ) : null}
    </div>
  );
}
