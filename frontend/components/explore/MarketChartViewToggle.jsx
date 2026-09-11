"use client";

import { MARKET_CHART_VIEW_INDEX, MARKET_CHART_VIEW_PERFORMANCE } from "./marketPerformanceDomain.mjs";

const VIEW_OPTIONS = [
  { value: MARKET_CHART_VIEW_PERFORMANCE, label: "Performance" },
  { value: MARKET_CHART_VIEW_INDEX, label: "Index" },
];

export default function MarketChartViewToggle({ value = MARKET_CHART_VIEW_PERFORMANCE, onChange }) {
  return (
    <div data-market-chart-view-toggle role="group" aria-label="Chart view" className="inline-flex w-fit items-center rounded-lg border border-[rgba(45,212,191,0.28)] bg-[var(--surface-page)]/55 p-1 shadow-sm">
      {VIEW_OPTIONS.map((option) => {
        const selected = value === option.value;
        return (
          <button key={option.value} type="button" data-market-chart-view={option.value} aria-pressed={selected} onClick={() => onChange?.(option.value)} className={`min-h-10 rounded-md px-4 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.75)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--surface-page)] ${selected ? "bg-[rgba(45,212,191,0.18)] text-[rgb(45,212,191)] shadow-sm" : "text-[var(--text-secondary)] hover:bg-white/[0.03] hover:text-[var(--text-primary)]"}`}>
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
