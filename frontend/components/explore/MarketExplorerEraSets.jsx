"use client";

import { useMemo, useState } from "react";
import TableSearchInput from "@/components/ui/TableSearchInput";
import { filterEraSetTree } from "@/lib/explore/marketExplorerScope.mjs";

// ---------------------------------------------------------------------------
// Era & Sets — hierarchical scope navigation.
//
// TWO ACTIONS PER ERA ROW, and they are genuinely separate controls: a checkbox
// that SELECTS the era, and a chevron button that EXPANDS it. Merging them is
// the usual mistake — opening Sword & Shield to see what is in it would then
// silently select all of Sword & Shield.
//
// SELECTING AN ERA DOES NOT DRAW A LINE. Nothing publishes an era index, so
// this sets a scope which Build a Market can resolve into a real queried
// market. The panel says exactly that rather than leaving the user to discover
// that their click did nothing to the chart.
//
// MOBILE. Eras are collapsed, so the initial render is a handful of rows, not
// every tracked set at once. Names truncate rather than widening the rail.
// ---------------------------------------------------------------------------

/** Below this many eras a search field is furniture, not help. */
const SEARCH_THRESHOLD = 6;

function SetRow({ entry, onToggleSet }) {
  return (
    <li>
      <label
        data-explorer-set-option={entry.id}
        className="flex min-w-0 cursor-pointer items-center gap-2 py-0.5 pl-5 text-[11px] text-[var(--text-primary)]"
      >
        <input
          type="checkbox"
          checked={entry.selected === true}
          onChange={() => onToggleSet?.(entry.id)}
          className="h-3.5 w-3.5 flex-none rounded-[3px] border-[var(--border-subtle)] bg-transparent accent-[rgb(45,212,191)]"
        />
        <span className="min-w-0 truncate">{entry.label}</span>
      </label>
    </li>
  );
}

function EraRow({ era, isExpanded, onToggleExpanded, onToggleEra, onToggleSet }) {
  const panelId = `explorer-era-sets-${era.id}`;
  return (
    <li data-explorer-era-row={era.id} data-explorer-era-selected={era.selected ? "true" : "false"} className="min-w-0">
      <div className="flex min-w-0 items-center gap-1.5">
        {/* EXPAND. A separate button from the checkbox, on purpose. */}
        <button
          type="button"
          data-explorer-era-expand={era.id}
          aria-expanded={isExpanded}
          aria-controls={panelId}
          aria-label={`${isExpanded ? "Collapse" : "Expand"} ${era.label} sets`}
          onClick={() => onToggleExpanded(era.id)}
          className="flex-none rounded px-1 py-1 text-[10px] leading-none text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
        >
          <span aria-hidden="true" className={`inline-block transition-transform ${isExpanded ? "rotate-90" : ""}`}>▶</span>
        </button>
        {/* SELECT. Toggling this never opens the set list. */}
        <label
          data-explorer-era-option={era.id}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 py-1 text-xs text-[var(--text-primary)]"
        >
          <input
            type="checkbox"
            checked={era.selected === true}
            onChange={() => onToggleEra?.(era.id)}
            className="h-3.5 w-3.5 flex-none rounded-[3px] border-[var(--border-subtle)] bg-transparent accent-[rgb(45,212,191)]"
          />
          <span className="min-w-0 truncate">{era.label}</span>
          <span className="ml-auto flex-none text-[10px] tabular-nums text-[var(--text-secondary)]">{era.sets.length}</span>
        </label>
      </div>
      <ul id={panelId} hidden={!isExpanded} className="mt-0.5 space-y-0.5">
        {isExpanded ? era.sets.map((entry) => (
          <SetRow key={entry.id} entry={entry} onToggleSet={onToggleSet} />
        )) : null}
      </ul>
    </li>
  );
}

export default function MarketExplorerEraSets({
  tree = [],
  scope = { eraIds: [], setIds: [] },
  status = "ready",
  onToggleEra,
  onToggleSet,
  onClear,
  onUseInBuilder,
}) {
  const [expanded, setExpanded] = useState(() => new Set());
  const [search, setSearch] = useState("");
  const visible = useMemo(() => filterEraSetTree(tree, search), [tree, search]);
  const hasScope = (scope?.eraIds?.length || 0) + (scope?.setIds?.length || 0) > 0;

  const toggleExpanded = (eraId) => setExpanded((current) => {
    const next = new Set(current);
    if (next.has(eraId)) next.delete(eraId);
    else next.add(eraId);
    return next;
  });

  if (status === "signedOut") {
    return (
      <p data-explorer-era-sets-state="signedOut" className="mt-1 text-[11px] text-[var(--text-secondary)]">
        Sign in to browse eras and sets. Prepared segments above stay available to everyone.
      </p>
    );
  }
  if (status !== "ready") {
    return (
      <p role="status" data-explorer-era-sets-state={status} className="mt-1 text-[11px] text-[var(--text-secondary)]">
        {status === "loading" ? "Loading canonical eras and sets…" : "The canonical set catalogue is temporarily unavailable."}
      </p>
    );
  }
  if (!tree.length) {
    return (
      <p data-explorer-era-sets-state="empty" className="mt-1 text-[11px] text-[var(--text-secondary)]">
        No tracked eras are published.
      </p>
    );
  }

  return (
    <div data-explorer-era-sets className="mt-1 min-w-0">
      {/* Stated up front, because the click does not do what a checkbox in a
          chart-filter rail otherwise implies. */}
      <p className="text-[10px] leading-relaxed text-[var(--text-secondary)]">
        Eras and Sets set a research <span className="font-semibold text-[var(--text-primary)]">scope</span>. No standalone
        era index is published, so a scope becomes a chartable market in Build a Market.
      </p>

      {tree.length >= SEARCH_THRESHOLD ? (
        // The SAME field as Set Market search on /Market — same ground, radius,
        // height, typography, placeholder and green focus ring. It was a
        // one-off before, with a /45 alpha ground and a yellow focus ring, and
        // it read as a different product from the search two clicks away.
        // The rail is narrow, so the desktop max-width is released here.
        <div className="mt-2">
          <TableSearchInput
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search eras and sets…"
            ariaLabel="Search eras and sets"
            containerClassName="desk:max-w-none"
            inputProps={{ "data-explorer-era-sets-search": true }}
          />
        </div>
      ) : null}

      <ul className="mt-2 max-h-[19rem] min-w-0 space-y-0.5 overflow-y-auto overflow-x-hidden">
        {visible.map((era) => (
          <EraRow
            key={era.id}
            era={era}
            isExpanded={expanded.has(era.id)}
            onToggleExpanded={toggleExpanded}
            onToggleEra={onToggleEra}
            onToggleSet={onToggleSet}
          />
        ))}
        {visible.length === 0 ? (
          <li className="py-1 text-[11px] text-[var(--text-secondary)]">No eras or sets match that search.</li>
        ) : null}
      </ul>

      {hasScope ? (
        <div data-explorer-scope-actions className="mt-2 flex flex-wrap items-center gap-2 border-t border-[var(--border-subtle)] pt-2">
          {/* EXPLICIT hand-off. The builder is never rewritten silently. */}
          <button
            type="button"
            data-explorer-scope-use
            onClick={onUseInBuilder}
            // Green, like every other primary action in this workspace.
            // Yellow stays the scarce emphasis color and is not the generic
            // primary-action color.
            className="min-h-11 rounded-md border border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.16)] px-2.5 py-1.5 text-[11px] font-semibold text-[rgb(45,212,191)] transition-colors hover:bg-[rgba(45,212,191,0.24)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] desk:min-h-0"
          >
            Use in Build a Market
          </button>
          <button
            type="button"
            data-explorer-scope-clear
            onClick={onClear}
            className="min-h-11 rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] desk:min-h-0"
          >
            Clear scope
          </button>
        </div>
      ) : null}
    </div>
  );
}
