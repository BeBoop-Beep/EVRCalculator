"use client";

import { MARKET_CHART_VIEW_ACTIVITY, MARKET_CHART_VIEW_INDEX, MARKET_CHART_VIEW_PERFORMANCE } from "./marketPerformanceDomain.mjs";
import { FOCUS_TOOL_STATE } from "@/lib/explore/marketExplorerAccess.mjs";

const VIEW_OPTIONS = [
  { value: MARKET_CHART_VIEW_INDEX, label: "Index" },
  { value: MARKET_CHART_VIEW_PERFORMANCE, label: "Performance" },
];

export default function MarketChartViewToggle({ value = MARKET_CHART_VIEW_INDEX, onChange, activity = null }) {
  const options = activity ? [...VIEW_OPTIONS, { value: MARKET_CHART_VIEW_ACTIVITY, label: "Market Activity" }] : VIEW_OPTIONS;
  return (
    <div data-market-chart-view-toggle role="group" aria-label="Chart view" className="inline-flex w-fit items-center rounded-lg border border-cyan-400/30 bg-[var(--surface-page)]/55 p-1 shadow-sm">
      {options.map((option) => {
        const selected = value === option.value;
        const activityOption = option.value === MARKET_CHART_VIEW_ACTIVITY;
        const disabled = activityOption && activity.state !== FOCUS_TOOL_STATE.available;
        const reason = activityOption ? activity.reason : null;
        return (
          <button key={option.value} type="button" data-market-chart-view={option.value} data-market-chart-view-state={activityOption ? activity.state : "available"} aria-pressed={selected} aria-label={reason ? `${option.label}. ${reason}` : option.label} title={reason || undefined} disabled={disabled} onClick={() => onChange?.(option.value)} className={`min-h-10 rounded-md px-4 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/75 focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--surface-page)] disabled:cursor-not-allowed disabled:opacity-45 ${selected ? "bg-cyan-400/15 text-cyan-200 shadow-sm ring-1 ring-inset ring-cyan-300/25" : "text-[var(--text-secondary)] hover:bg-white/[0.03] hover:text-[var(--text-primary)]"}`}>
            {option.label}{activityOption && activity.state === FOCUS_TOOL_STATE.locked ? <span className="ml-1 rounded-full bg-violet-500/25 px-1 text-[8px]">Index+</span> : null}
          </button>
        );
      })}
    </div>
  );
}
