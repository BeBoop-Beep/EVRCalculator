"use client";

import { MARKET_CHART_VIEW_INDEX, MARKET_CHART_VIEW_PERFORMANCE } from "./marketPerformanceDomain.mjs";

const VIEW_OPTIONS = [
  { value: MARKET_CHART_VIEW_PERFORMANCE, label: "Performance" },
  { value: MARKET_CHART_VIEW_INDEX, label: "Index" },
];

export default function MarketChartViewToggle({ value = MARKET_CHART_VIEW_PERFORMANCE, onChange }) {
  return (
    <div data-market-chart-view-toggle role="group" aria-label="Chart view" className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/40 p-0.5">
      {VIEW_OPTIONS.map((option) => {
        const selected = value === option.value;
        return (
          <button key={option.value} type="button" data-market-chart-view={option.value} aria-pressed={selected} onClick={() => onChange?.(option.value)} className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] ${selected ? "bg-[rgba(45,212,191,0.16)] text-[rgb(45,212,191)] shadow-sm" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}>
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
