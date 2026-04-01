import { PERFORMANCE_TIME_RANGES } from "@/lib/profile/portfolioPerformanceRange";

export default function OverviewRangeToggle({
  selectedRange,
  onRangeChange,
  ariaLabel = "Portfolio performance time range",
}) {
  return (
    <div
      className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5"
      role="group"
      aria-label={ariaLabel}
    >
      {PERFORMANCE_TIME_RANGES.map((range) => (
        <button
          key={range}
          type="button"
          onClick={() => onRangeChange?.(range)}
          aria-pressed={selectedRange === range}
          className={`min-w-[2.3rem] rounded-md px-3 py-1 text-[11px] font-semibold leading-none transition-colors ${
            selectedRange === range
              ? "bg-[var(--brand)] text-white"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          }`}
        >
          {range}
        </button>
      ))}
    </div>
  );
}