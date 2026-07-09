"use client";

// Visual sibling of SectionLoadingPanel for a section's error state — covers
// both a failed fetch (status "error") and a caught render-time exception
// (via SectionErrorBoundary), so the two failure modes look identical to the
// user. Always local to the section; never replaces the rest of the tab.
export default function SectionErrorPanel({
  title,
  message = "This section couldn't load.",
  onRetry = null,
  minHeightClassName = "min-h-[16rem]",
  className = "",
}) {
  return (
    <div
      className={`flex ${minHeightClassName} flex-col items-center justify-center gap-2 rounded-2xl border border-[rgba(248,113,113,0.28)] bg-[linear-gradient(180deg,rgba(56,17,20,0.55),rgba(2,6,23,0.62))] p-8 text-center ${className}`.trim()}
    >
      {title ? <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p> : null}
      <p className="max-w-sm text-xs leading-relaxed text-[var(--text-secondary)]">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded-md border border-[rgba(255,255,255,0.14)] bg-[rgba(255,255,255,0.04)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[rgba(255,255,255,0.08)]"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
