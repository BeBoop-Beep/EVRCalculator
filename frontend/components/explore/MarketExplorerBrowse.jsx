"use client";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { groupPreparedDirectory } from "@/lib/explore/marketExplorerPrepared.mjs";

const CATEGORIES = [["sets", "Sets"], ["eras", "Eras"], ["quick", "Quick Markets"]];

export default function MarketExplorerBrowse({ directory = [], activeKeys = [], canCompare, onSelect, onCompare, onBuild }) {
  const [open, setOpen] = useState(null);
  const [search, setSearch] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const rootRef = useRef(null);
  const searchRef = useRef(null);
  const listboxId = useId();
  const grouped = useMemo(() => groupPreparedDirectory(directory, search), [directory, search]);
  const rows = open === "eras" ? grouped.eras : open === "quick" ? grouped.quick : grouped.sets.flatMap((group) => group.rows);
  const groups = open === "sets" ? grouped.sets : null;
  useEffect(() => { if (open) requestAnimationFrame(() => searchRef.current?.focus()); }, [open]);
  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const outside = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(null); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);
  const close = () => { setOpen(null); setSearch(""); setHighlightedIndex(0); };
  const choose = (key) => { onSelect(key); close(); };
  const row = (market, index) => {
    const active = activeKeys.includes(market.market_key);
    const highlighted = index === highlightedIndex;
    return <li key={market.market_key} role="option" aria-selected={active} id={`${listboxId}-${index}`} className={`flex items-center gap-2 rounded-md border-l-2 ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)]" : highlighted ? "border-sky-400/60 bg-sky-400/[.08]" : "border-transparent"}`}>
      <button type="button" data-prepared-market={market.market_key} data-search-highlighted={highlighted ? "true" : "false"} onClick={() => choose(market.market_key)} className="min-w-0 flex-1 px-2 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70"><strong className={`block truncate text-xs ${active ? "font-bold text-[rgb(45,212,191)]" : "text-[var(--text-primary)]"}`}>{market.label}{active ? <span aria-label="Active market"> ✓</span> : null}</strong><span className="text-[10px] text-[var(--text-secondary)]">{market.current_value == null ? "Value unavailable" : `$${Number(market.current_value).toLocaleString()}`}</span></button>
      <button type="button" data-compare-market={market.market_key} onClick={() => onCompare(market.market_key)} className="mr-1 rounded border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold text-[var(--text-secondary)]">+ Compare{canCompare ? "" : " with Index+"}</button>
    </li>;
  };
  let rowIndex = 0;
  const categoryLabel = CATEGORIES.find(([id]) => id === open)?.[1];
  return <section ref={rootRef} data-market-explorer-browse aria-labelledby="browse-markets-heading" className="relative min-w-0 px-3 pb-3">
    <h3 id="browse-markets-heading" className="text-sm font-semibold text-[var(--text-primary)]">Market Directory</h3><p className="mb-3 text-[11px] text-[var(--text-secondary)]">Search prepared markets or create your own.</p>
    <div className="grid grid-cols-2 gap-2">
      {CATEGORIES.map(([id, label]) => <button key={id} type="button" aria-haspopup="listbox" aria-expanded={open === id} aria-controls={open === id ? listboxId : undefined} onClick={() => { setOpen((value) => value === id ? null : id); setSearch(""); setHighlightedIndex(0); }} className={`min-h-10 rounded-md border px-2 text-xs font-semibold ${open === id ? "border-sky-400 bg-sky-400/10 text-sky-200" : "border-slate-500/50 bg-slate-400/[.06] text-[var(--text-primary)] hover:border-sky-400/60"}`}>{label} <span aria-hidden="true">▾</span></button>)}
      <button type="button" data-market-explorer-build-trigger onClick={onBuild} className="min-h-10 rounded-md border border-[rgb(45,212,191)] bg-[rgba(45,212,191,.16)] px-2 text-xs font-bold text-[rgb(45,212,191)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(45,212,191)]"><span aria-hidden="true">＋</span> Build Your Market</button>
    </div>
    {open ? <div data-market-directory-popover className="absolute left-3 right-3 z-40 mt-2 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] shadow-2xl">
      <input ref={searchRef} role="combobox" aria-expanded="true" aria-controls={listboxId} aria-activedescendant={rows.length ? `${listboxId}-${Math.min(highlightedIndex, rows.length - 1)}` : undefined} data-market-browser-search value={search} onChange={(event) => { setSearch(event.target.value); setHighlightedIndex(0); }} onKeyDown={(event) => { if (event.key === "ArrowDown") { event.preventDefault(); setHighlightedIndex((i) => Math.min(i + 1, rows.length - 1)); } if (event.key === "ArrowUp") { event.preventDefault(); setHighlightedIndex((i) => Math.max(i - 1, 0)); } if (event.key === "Enter" && rows.length) { event.preventDefault(); choose(rows[Math.min(highlightedIndex, rows.length - 1)].market_key); } if (event.key === "Escape") { event.preventDefault(); close(); } }} placeholder={`Search ${categoryLabel}…`} aria-label={`Search ${categoryLabel}`} className="w-full border-b border-[var(--border-subtle)] bg-transparent px-3 py-3 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-400/70" />
      <div id={listboxId} role="listbox" aria-label={`${categoryLabel} prepared markets`} className="max-h-[min(25rem,55vh)] overflow-y-auto p-2">{!rows.length ? <p className="p-3 text-xs text-[var(--text-secondary)]">No matching markets.</p> : groups ? groups.map((group) => <div key={group.era?.market_key || group.rows[0]?.parent_era_id}><h4 className="sticky top-0 bg-[var(--surface-page)] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-[var(--text-secondary)]">{group.era?.label || "Unknown Era"}</h4><ul>{group.rows.map((market) => row(market, rowIndex++))}</ul></div>) : <ul>{rows.map(row)}</ul>}</div>
    </div> : null}
  </section>;
}
