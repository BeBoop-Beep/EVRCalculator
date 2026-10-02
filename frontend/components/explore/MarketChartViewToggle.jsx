"use client";

import { MARKET_CHART_VIEW_ACTIVITY, MARKET_CHART_VIEW_INDEX } from "./marketPerformanceDomain.mjs";
import { FOCUS_TOOL_STATE } from "@/lib/explore/marketExplorerAccess.mjs";

/**
 * Explorer's primary chart is always the canonical Market Index.
 *
 * Market Activity is an alternate focused-market lens, not a peer normalization
 * mode. Keep one compact action here: enter Activity when Index is showing, and
 * return to Index when Activity is open. Performance remains visible in the
 * Index tooltip and comparison detail, so a duplicate chart mode adds no new
 * information.
 */
export default function MarketChartViewToggle({ value = MARKET_CHART_VIEW_INDEX, onChange, activity = null }) {
  if (!activity) return null;
  const activitySelected = value === MARKET_CHART_VIEW_ACTIVITY;
  const disabled = !activitySelected && activity.state !== FOCUS_TOOL_STATE.available;
  const reason = activitySelected ? null : activity.reason;
  const label = activitySelected ? "Back to Index" : "Market Activity";
  const next = activitySelected ? MARKET_CHART_VIEW_INDEX : MARKET_CHART_VIEW_ACTIVITY;
  return (
    <div data-market-chart-view-toggle role="group" aria-label="Chart view" className="inline-flex w-fit items-center">
      <button
        type="button"
        data-market-chart-view={activitySelected ? MARKET_CHART_VIEW_INDEX : MARKET_CHART_VIEW_ACTIVITY}
        data-market-chart-view-state={activity.state}
        aria-pressed={activitySelected}
        aria-label={reason ? `${label}. ${reason}` : label}
        title={reason || undefined}
        disabled={disabled}
        onClick={() => onChange?.(next)}
        className={`min-h-10 rounded-lg border border-cyan-400/30 bg-[var(--surface-page)]/55 px-4 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/75 focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--surface-page)] disabled:cursor-not-allowed disabled:opacity-45 ${activitySelected ? "bg-cyan-400/15 text-cyan-200 shadow-sm ring-1 ring-inset ring-cyan-300/25" : "text-[var(--text-secondary)] hover:bg-white/[0.03] hover:text-[var(--text-primary)]"}`}
      >
        {label}
        {!activitySelected && activity.state === FOCUS_TOOL_STATE.locked ? <span className="ml-1 rounded-full bg-violet-500/25 px-1 text-[8px]">Index+</span> : null}
      </button>
    </div>
  );
}
