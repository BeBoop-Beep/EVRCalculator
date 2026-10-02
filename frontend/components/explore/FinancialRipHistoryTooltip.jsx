"use client";

import React from "react";
import { financialRipTooltipRows, formatTrendDelta, formatTrendValue } from "./financialRipHistoryModel.mjs";

const labelDate = (date) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`));

export const TOOLTIP_SCROLL_ATTR = "data-financial-history-tooltip-scroll";

/**
 * Tooltip body.  Date and Overall stay pinned at the top; ONLY the entity rows scroll.
 * In focus mode it lists the focused entity alone.  The scroll region is bounded by the
 * viewport (not a fixed 20rem), contains overscroll and allows vertical touch panning.
 */
export function FinancialRipTooltipContent({ point, series, metricKey = "financial", overallLabel = "Overall Financial RIP", focusId = null, pinned = false, onClose }) {
  if (!point) return null;
  const rows = financialRipTooltipRows(point, series, focusId);
  return <div data-financial-history-tooltip data-pinned={pinned ? "true" : "false"} data-focused={focusId != null ? "true" : "false"} className="flex max-h-[min(18rem,55vh)] min-w-56 max-w-[min(20rem,calc(100vw-2rem))] flex-col rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-3 text-xs shadow-2xl">
    <div className="flex items-start justify-between gap-3"><p className="font-semibold text-[var(--text-primary)]">{labelDate(point.date)}</p>{pinned ? <button type="button" onClick={onClose} aria-label="Close pinned Financial RIP details" className="-mr-1 -mt-1 inline-flex h-7 w-7 items-center justify-center rounded text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">×</button> : null}</div>
    <div className="mt-2 flex items-center justify-between gap-4 border-t border-[var(--border-subtle)] pt-2"><span className="text-[var(--text-secondary)]">{overallLabel}</span><strong className="tabular-nums">{formatTrendValue(point.overallTrend, metricKey)}</strong></div>
    <div {...{ [TOOLTIP_SCROLL_ATTR]: "" }} tabIndex={pinned ? 0 : undefined} role={pinned ? "region" : undefined} aria-label={pinned ? "Financial RIP series values" : undefined} style={{ touchAction: "pan-y", overscrollBehavior: "contain" }} className="mt-2 min-h-0 flex-1 space-y-1.5 overflow-y-auto overscroll-contain pr-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">
      {rows.map((row) => <div key={row.entity_id} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: row.color }} /><span className="truncate font-medium">{row.name} <strong className="ml-1">{formatTrendValue(row.score, metricKey)}</strong></span><span className="tabular-nums text-[var(--text-secondary)]">{formatTrendDelta(row.deltaVsOverall, metricKey)}</span></div>)}
    </div>
  </div>;
}

/** Recharts hover tooltip.  Pure display: hovering it never changes focus or selection. */
export default function ChartTooltip({ active, payload, series, metricKey = "financial", overallLabel, focusId = null, suppressed = false }) {
  const point = payload?.[0]?.payload;
  if (!active || !point || suppressed) return null;
  return <FinancialRipTooltipContent point={point} series={series} metricKey={metricKey} overallLabel={overallLabel} focusId={focusId} />;
}
