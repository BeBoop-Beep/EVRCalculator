"use client";
import { useMemo, useRef, useState } from "react";
import { groupPreparedDirectory } from "@/lib/explore/marketExplorerPrepared.mjs";

function MarketRow({ market, active, canCompare, onSelect, onCompare, highlighted = false }) {
  return <li className="flex items-stretch gap-2 border-b border-[var(--border-subtle)] py-1 last:border-0">
    <button type="button" data-prepared-market={market.market_key} data-search-highlighted={highlighted ? "true" : "false"} aria-pressed={active} onClick={() => onSelect(market.market_key)} className={`min-w-0 flex-1 rounded-md border-l-2 px-2 py-2 text-left transition-all hover:-translate-y-px hover:border-[rgba(45,212,191,.45)] hover:bg-white/[.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,.65)] ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)] shadow-[inset_0_0_0_1px_rgba(45,212,191,.16)]" : highlighted ? "border-sky-400/50 bg-sky-400/[.06]" : "border-transparent"}`}>
      <strong className={`block truncate text-xs ${active ? "font-bold text-[rgb(45,212,191)]" : "text-[var(--text-primary)]"}`}>{market.label}</strong>
      <span className="text-[10px] text-[var(--text-secondary)]">{market.current_value == null ? "Value unavailable" : `$${Number(market.current_value).toLocaleString()}`} · as of {market.source_as_of || "unavailable"}{market.history_available ? "" : " · Browse only"}{market.source_status === "failed" ? " · latest refresh failed; using previous good series" : ""}</span>
    </button>
    <button type="button" data-compare-market={market.market_key} onClick={() => onCompare(market.market_key)} className="self-center rounded border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold text-[var(--text-secondary)]">+ Compare{canCompare ? "" : " with Index+"}</button>
  </li>;
}

export default function MarketExplorerBrowse({ directory = [], activeKeys = [], canCompare, onSelect, onCompare }) {
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState("sets");
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const searchRef = useRef(null);
  const grouped = useMemo(() => groupPreparedDirectory(directory, search), [directory, search]);
  const rows = tab === "eras" ? grouped.eras : tab === "quick" ? grouped.quick : null;
  const searchableRows = rows || grouped.sets.flatMap((group) => group.rows);
  const openHighlighted = () => {
    const market = searchableRows[Math.min(highlightedIndex, Math.max(0, searchableRows.length - 1))];
    if (market) onSelect(market.market_key);
  };
  const row = (market, index) => <MarketRow key={market.market_key} market={market} active={activeKeys.includes(market.market_key)} highlighted={Boolean(search) && index === highlightedIndex} canCompare={canCompare} onSelect={onSelect} onCompare={onCompare} />;
  let rowIndex = 0;
  return <section data-market-explorer-browse aria-labelledby="browse-markets-heading" className="min-w-0">
    <div className="px-3 py-3"><h3 id="browse-markets-heading" className="text-sm font-semibold text-[var(--text-primary)]">Market Directory</h3>
      <p className="text-[11px] text-[var(--text-secondary)]">Select a market to open it, or add it to a comparison.</p></div>
    <div role="tablist" aria-label="Prepared market type" className="flex gap-1 px-3">
      {[["sets","Sets"],["eras","Eras"],["quick","Quick Markets"]].map(([id,label]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => { setTab(id); setHighlightedIndex(0); }} className={`rounded-t border-b-2 px-3 py-2 text-xs font-semibold transition-colors ${tab === id ? "border-sky-400 bg-sky-400/10 text-sky-200" : "border-transparent text-[var(--text-secondary)] hover:bg-slate-400/10 hover:text-[var(--text-primary)]"}`}>{label}</button>)}
    </div>
    <div className="px-3 pb-3"><input ref={searchRef} data-market-browser-search value={search} onChange={(event) => { setSearch(event.target.value); setHighlightedIndex(0); }} onKeyDown={(event) => {
      if (event.key === "ArrowDown") { event.preventDefault(); setHighlightedIndex((index) => Math.min(index + 1, searchableRows.length - 1)); }
      if (event.key === "ArrowUp") { event.preventDefault(); setHighlightedIndex((index) => Math.max(index - 1, 0)); }
      if (event.key === "Enter") { event.preventDefault(); openHighlighted(); }
      if (event.key === "Escape") { setSearch(""); setHighlightedIndex(0); searchRef.current?.blur(); }
    }} placeholder="Search markets…" aria-label="Search prepared markets" className="mb-2 w-full rounded-md border border-[var(--border-subtle)] bg-transparent px-3 py-2 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70" />
      <div className="max-h-[25rem] overflow-y-auto">
        {rows ? <ul>{rows.map((market, index) => row(market, index))}</ul>
          : grouped.sets.map((group) => <section key={group.era?.market_key || group.rows[0]?.parent_era_id} data-market-era-group={group.era?.market_key}><h3 className="sticky top-0 bg-[var(--surface-page)] py-1 text-[10px] font-bold uppercase tracking-wide text-[var(--text-secondary)]">{group.era?.label || "Unknown Era"}</h3><ul>{group.rows.map((market) => row(market, rowIndex++))}</ul></section>)}
      </div>
    </div>
  </section>;
}
