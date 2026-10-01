"use client";

import React from "react";

// Legend / key row.  Each selected entity is TWO controls: the key body (focus)
// and the x (remove).  Overall is a permanent, non-interactive reference key.
// Hover focus is pointer-only (mouse); touch and keyboard use the persistent toggle.

export const CLEAR_ALL_LABEL = "Clear all Financial RIP series";

const mousePointer = (event) => event.pointerType === "mouse";

export default function FinancialRipHistoryLegend({
  series = [],
  showOverall = true,
  persistentFocusId = null,
  onToggleFocus,
  onHoverFocus,
  onRemove,
  onClearAll,
  updating = false,
}) {
  return <div className="mt-3 flex items-start gap-2" data-financial-history-legend>
    <div className="max-h-36 min-w-0 flex-1 overflow-y-auto overscroll-contain" role="group" aria-label="Visible Financial RIP series">
      <div className="flex flex-wrap items-center gap-2">
        {showOverall ? <span data-legend-overall className="inline-flex min-h-9 items-center gap-1.5 rounded-full border border-[var(--border-subtle)] px-2.5 text-[10px]"><span className="h-0.5 w-3 bg-slate-200/75" />Overall Financial RIP</span> : null}
        {series.map((item) => {
          const focused = persistentFocusId != null && String(persistentFocusId) === String(item.entity_id);
          return <span key={item.entity_id} data-legend-entity={item.entity_id} data-focused={focused ? "true" : "false"} className={`inline-flex min-h-9 items-stretch overflow-hidden rounded-full border text-[10px] ${focused ? "bg-white/[.07]" : "border-[var(--border-subtle)]"}`} style={focused ? { borderColor: item.color } : undefined}>
            <button type="button" data-legend-focus aria-pressed={focused} aria-label={`${focused ? "Clear focus on" : "Focus"} ${item.name} on Financial RIP chart`} onClick={() => onToggleFocus?.(item.entity_id)} onPointerEnter={(event) => { if (mousePointer(event)) onHoverFocus?.(item.entity_id); }} onPointerLeave={(event) => { if (mousePointer(event)) onHoverFocus?.(null); }} className="inline-flex min-h-9 items-center gap-1.5 pl-2.5 pr-1.5 hover:bg-white/[.05] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)]"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} /><span>{item.name}</span></button>
            <button type="button" data-legend-remove onClick={() => onRemove?.(item.entity_id)} aria-label={`Remove ${item.name} from Financial RIP chart`} className="inline-flex min-h-9 min-w-9 items-center justify-center border-l border-[var(--border-subtle)] text-sm leading-none text-[var(--text-secondary)] hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)]">×</button>
          </span>;
        })}
        {updating ? <span aria-live="polite" className="text-[10px] text-[var(--text-secondary)]">Updating history…</span> : null}
      </div>
    </div>
    <button type="button" data-financial-history-clear-all aria-label={CLEAR_ALL_LABEL} disabled={!series.length} onClick={() => onClearAll?.()} className="inline-flex min-h-9 shrink-0 items-center rounded-full border border-red-400/45 bg-red-500/[.09] px-3 text-[11px] font-semibold text-red-300 transition-colors hover:bg-red-500/[.16] focus:outline-none focus-visible:ring-2 focus-visible:ring-red-300/70 disabled:cursor-not-allowed disabled:opacity-40">Clear All</button>
  </div>;
}
