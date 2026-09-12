"use client";

import { MARKET_CHART_VIEW_INDEX, MARKET_CHART_VIEW_PERFORMANCE } from "./marketPerformanceDomain.mjs";

const VIEW_OPTIONS = [
  { value: MARKET_CHART_VIEW_PERFORMANCE, label: "Performance" },
  { value: MARKET_CHART_VIEW_INDEX, label: "Index" },
];

export default function MarketChartViewToggle({ value = MARKET_CHART_VIEW_PERFORMANCE, onChange }) {
  return (
    <div data-market-chart-view-toggle role="group" aria-label="Chart view" className="inline-flex w-fit items-center rounded-lg border border-cyan-400/30 bg-[var(--surface-page)]/55 p-1 shadow-sm">
      {VIEW_OPTIONS.map((option) => {
        const selected = value === option.value;
        return (
          <button key={option.value} type="button" data-market-chart-view={option.value} aria-pressed={selected} onClick={() => onChange?.(option.value)} className={`min-h-10 rounded-md px-4 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/75 focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--surface-page)] ${selected ? "bg-cyan-400/15 text-cyan-200 shadow-sm ring-1 ring-inset ring-cyan-300/25" : "text-[var(--text-secondary)] hover:bg-white/[0.03] hover:text-[var(--text-primary)]"}`}>
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
