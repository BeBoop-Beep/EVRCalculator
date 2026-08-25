"use client";

export default function ReturnToTopButton({ visible, onActivate, ariaLabel = "Return to top", className = "" }) {
  if (!visible) return null;

  return (
    <button
      type="button"
      onClick={onActivate}
      className={`fixed bottom-[calc(5.25rem+env(safe-area-inset-bottom)+0.75rem)] left-1/2 z-[60] h-12 w-12 -translate-x-1/2 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 text-[var(--text-primary)] shadow-[0_12px_30px_rgba(2,6,23,0.32)] backdrop-blur transition-transform hover:scale-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] motion-reduce:transition-none ${className}`}
      aria-label={ariaLabel}
    >
      <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor" aria-hidden="true">
        <path d="M10 4.25a.75.75 0 0 1 .53.22l4.5 4.5a.75.75 0 1 1-1.06 1.06L10.75 6.56v8.19a.75.75 0 0 1-1.5 0V6.56L6.03 9.98a.75.75 0 0 1-1.06-1.06l4.5-4.5A.75.75 0 0 1 10 4.25Z" />
      </svg>
    </button>
  );
}
