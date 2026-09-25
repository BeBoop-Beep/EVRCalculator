"use client";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { groupPreparedDirectory, listPreparedSealedMarkets } from "@/lib/explore/marketExplorerPrepared.mjs";
import { NO_APPROVED_SEALED_QUICK_COPY } from "@/lib/explore/marketExplorerAssetOptions.mjs";
import MarketExplorerContextualSearch from "./MarketExplorerContextualSearch";

const CARD_CATEGORIES = [["sets", "Sets"], ["eras", "Eras"], ["quick", "Quick Markets"]];
// Sealed IA: Sets, Eras, Quick Markets (Sealed Types + Screens render in the Analyze
// section; the Build trigger is shared). "Sealed Markets" stays as the flat
// list of every published sealed market.
const SEALED_CATEGORIES = [["sets", "Sets"], ["eras", "Eras"], ["quick", "Quick Markets"], ["sealed", "Sealed Markets"]];
const CATEGORIES = [...CARD_CATEGORIES, ["sealed", "Sealed Markets"]];
const GRADED_FALLBACK_REASON = "Graded markets are not available yet: there is not enough graded price coverage to publish one.";
// Directory ASSET LAYER. Browsing state only: switching it changes which browse
// choices are listed and never touches the chart's active markets. Graded has
// no prepared-market authority yet, so it is visible but inert.
const ASSET_LAYERS = [["cards", "Cards"], ["sealed", "Sealed"], ["graded", "Graded"]];
const NO_HIGHLIGHT = -1;
const QUICK_COPY = {
  Obtainable: ["Obtainable Cards", "Lower-priced cards grouped as a card market."],
  Intermediate: ["Intermediate Cards", "Mid-priced cards grouped as a card market."],
  Premium: ["Premium Cards", "Higher-priced cards grouped as a card market."],
  "New Releases": ["New Release Cards", "Cards from newer releases."],
  Established: ["Established Cards", "Cards from established releases."],
  "Global Top 10": ["Global Top 10 Cards", "The ten highest-ranked cards in the global card market."],
};
const displayMarket = (market) => {
  const copy = market?.market_type === "curated" ? QUICK_COPY[market.label] : null;
  return { label: copy?.[0] || market.label, description: copy?.[1] || null };
};

export default function MarketExplorerBrowse({ directory = [], directoryStatus = "ready", activeKeys = [], pendingKeys = [], failedKeys = [], canCompare, onSelect, onCompare, onBuild, assetLayer: assetLayerProp, onAssetLayerChange, gradedReason = null, onAddToBasket, enableContextualSearch = true }) {
  const [open, setOpen] = useState(null);
  const [search, setSearch] = useState("");
  // activeBrowseAsset: what the directory/search/builder default LIST. It never
  // touches the chart's active markets. Controlled when the parent owns it.
  const [assetLayerState, setAssetLayerState] = useState("cards");
  const assetLayer = assetLayerProp ?? assetLayerState;
  const setAssetLayer = (value) => { setAssetLayerState(value); onAssetLayerChange?.(value); };
  // KEYBOARD highlight only. -1 = none. Opening a menu, typing, or resetting never
  // creates one; only ArrowDown/ArrowUp do. Selected/active styling comes solely
  // from activeKeys.
  const [highlightedIndex, setHighlightedIndex] = useState(NO_HIGHLIGHT);
  const rootRef = useRef(null);
  const searchRef = useRef(null);
  const triggerRefs = useRef(new Map());
  const listboxId = useId();
  // One asset at a time: a sealed Set/Era is never listed under Cards and vice versa.
  const layerRows = useMemo(() => directory.filter((row) => (assetLayer === "sealed" ? row?.asset === "sealed" : row?.asset !== "sealed")), [directory, assetLayer]);
  const grouped = useMemo(() => groupPreparedDirectory(layerRows, search), [layerRows, search]);
  const sealedRows = useMemo(() => listPreparedSealedMarkets(directory, search), [directory, search]);
  const rows = open === "sealed" ? sealedRows : open === "eras" ? grouped.eras : open === "quick" ? grouped.quick : grouped.sets.flatMap((group) => group.rows);
  const groups = open === "sets" ? grouped.sets : null;
  useEffect(() => { if (open) requestAnimationFrame(() => searchRef.current?.focus()); }, [open]);
  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const outside = (event) => { if (!rootRef.current?.contains(event.target)) { setOpen(null); setSearch(""); setHighlightedIndex(NO_HIGHLIGHT); } };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);
  const close = (restoreFocus = false) => {
    const trigger = triggerRefs.current.get(open);
    setOpen(null); setSearch(""); setHighlightedIndex(NO_HIGHLIGHT);
    if (restoreFocus) requestAnimationFrame(() => trigger?.focus());
  };
  const choose = (key) => { onSelect(key); };
  const row = (market, index) => {
    const active = activeKeys.includes(market.market_key);
    // ACTIVE means LOADED. A requested market is "loading"; one that did not
    // load is "failed" and a click retries it. Neither is styled as active.
    const loading = !active && pendingKeys.includes(market.market_key);
    const failed = !active && !loading && failedKeys.includes(market.market_key);
    const highlighted = highlightedIndex >= 0 && index === highlightedIndex;
    const display = displayMarket(market);
    return <li key={market.market_key} role="option" aria-selected={active} id={`${listboxId}-${index}`} data-market-row-state={active ? "active" : loading ? "loading" : failed ? "failed" : highlighted ? "keyboard" : "idle"} className={`flex items-center gap-2 rounded-md border-l-2 ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)]" : "border-transparent hover:bg-white/[.06]"} ${highlighted ? "ring-2 ring-inset ring-sky-400/80" : ""}`}>
      <button type="button" data-prepared-market={market.market_key} data-search-highlighted={highlighted ? "true" : "false"} aria-pressed={active} onClick={() => choose(market.market_key)} className="min-w-0 flex-1 px-2 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70"><strong className={`block truncate text-xs ${active ? "font-bold text-[rgb(45,212,191)]" : "text-[var(--text-primary)]"}`}>{display.label}{active ? <span aria-label="Active market"> ✓</span> : null}</strong>{display.description ? <span className="block text-[9px] text-[var(--text-secondary)]">{display.description}</span> : null}<span className="text-[10px] text-[var(--text-secondary)]">{market.current_value == null ? "Value unavailable" : `${Number(market.current_value).toLocaleString()}`}</span></button>
      <button type="button" data-compare-market={market.market_key} aria-pressed={active} onClick={() => onCompare(market.market_key)} className={`mr-1 rounded border px-2 py-1 text-[10px] font-semibold ${active ? "border-[rgba(248,113,113,.45)] text-[rgb(248,113,113)]" : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>{active ? "Remove" : loading ? "Adding…" : failed ? "Retry" : `+ Compare${canCompare ? "" : " with Index+"}`}</button>
    </li>;
  };
  let rowIndex = 0;
  const categoryLabel = (assetLayer === "sealed" ? SEALED_CATEGORIES : CATEGORIES).find(([id]) => id === open)?.[1];
  return <section ref={rootRef} data-market-explorer-browse aria-labelledby="browse-markets-heading" className="relative min-w-0 px-3 pb-3 pt-3">
    <h3 id="browse-markets-heading" className="text-sm font-semibold text-[var(--text-primary)]">Market Directory</h3><p className="mb-3 text-[11px] text-[var(--text-secondary)]">Search prepared markets or create your own.</p>
    <div role="group" aria-label="Directory asset" data-market-directory-asset-layer className="mb-2 grid grid-cols-3 gap-1 rounded-lg border border-[var(--border-subtle)] p-0.5">
      {ASSET_LAYERS.map(([id, label]) => <button key={id} type="button" data-market-directory-asset={id} aria-pressed={assetLayer === id} onClick={() => { setAssetLayer(id); setOpen(null); setSearch(""); setHighlightedIndex(NO_HIGHLIGHT); }} className={`min-h-8 rounded-md px-1 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70 ${assetLayer === id ? "bg-sky-400/15 text-sky-200" : "text-[var(--text-primary)] hover:bg-white/[.05]"}`}>{label}</button>)}
    </div>
    {enableContextualSearch ? <MarketExplorerContextualSearch asset={assetLayer} activeKeys={activeKeys} pendingKeys={pendingKeys} failedKeys={failedKeys} onActivateMarket={onSelect} onAddToBasket={onAddToBasket} /> : null}
    {assetLayer === "graded"
      ? <div role="status" data-market-directory-state="graded-unavailable" className="rounded-md border border-[var(--border-subtle)] px-3 py-3 text-xs text-[var(--text-secondary)]"><strong className="block text-[var(--text-primary)]">Graded markets are unavailable</strong><span data-graded-reason>{gradedReason || GRADED_FALLBACK_REASON}</span></div>
      : <div className="grid grid-cols-2 gap-2">
      {(assetLayer === "sealed" ? SEALED_CATEGORIES : CARD_CATEGORIES).map(([id, label]) => <button key={id} data-market-directory-category={id} ref={(node) => { if (node) triggerRefs.current.set(id, node); else triggerRefs.current.delete(id); }} type="button" aria-haspopup="listbox" aria-expanded={open === id} aria-controls={open === id ? listboxId : undefined} onClick={() => { setOpen((value) => value === id ? null : id); setSearch(""); setHighlightedIndex(NO_HIGHLIGHT); }} className={`min-h-10 rounded-md border px-2 text-xs font-semibold ${open === id ? "border-sky-400 bg-sky-400/10 text-sky-200" : "border-slate-500/50 bg-slate-400/[.06] text-[var(--text-primary)] hover:border-sky-400/60"}`}>{label} <span aria-hidden="true">▾</span></button>)}
      <button type="button" data-market-explorer-build-trigger onClick={onBuild} className="min-h-10 rounded-md border border-[rgb(45,212,191)] bg-[rgba(45,212,191,.16)] px-2 text-xs font-bold text-[rgb(45,212,191)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(45,212,191)]"><span aria-hidden="true">＋</span> Build Your Market</button>
    </div>}
    {open ? <div data-market-directory-popover className="absolute left-3 right-3 z-40 mt-2 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] shadow-2xl">
      <input ref={searchRef} role="combobox" aria-expanded="true" aria-controls={listboxId} aria-activedescendant={highlightedIndex >= 0 && highlightedIndex < rows.length ? `${listboxId}-${highlightedIndex}` : undefined} data-market-browser-search value={search} onChange={(event) => { setSearch(event.target.value); setHighlightedIndex(NO_HIGHLIGHT); }} onKeyDown={(event) => { if (event.key === "ArrowDown") { event.preventDefault(); setHighlightedIndex((i) => (rows.length ? (i < 0 ? 0 : Math.min(i + 1, rows.length - 1)) : NO_HIGHLIGHT)); } if (event.key === "ArrowUp") { event.preventDefault(); setHighlightedIndex((i) => (rows.length ? (i < 0 ? rows.length - 1 : Math.max(i - 1, 0)) : NO_HIGHLIGHT)); } if (event.key === "Enter") { const target = highlightedIndex >= 0 && highlightedIndex < rows.length ? rows[highlightedIndex] : (search.trim() && rows.length === 1 ? rows[0] : null); if (target) { event.preventDefault(); choose(target.market_key); } } if (event.key === "Escape") { event.preventDefault(); close(true); } }} placeholder={`Search ${categoryLabel}…`} aria-label={`Search ${categoryLabel}`} className="w-full border-b border-[var(--border-subtle)] bg-transparent px-3 py-3 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-400/70" />
      <div id={listboxId} role="listbox" aria-label={`${categoryLabel} prepared markets`} className="max-h-[min(25rem,55vh)] overflow-y-auto p-2">{directoryStatus === "unavailable" ? <div role="alert" data-market-directory-state="unavailable" className="p-3 text-xs text-[var(--text-secondary)]"><p>Market directory is temporarily unavailable.</p><button type="button" onClick={() => globalThis.location?.reload()} className="mt-2 rounded border border-[var(--border-subtle)] px-2 py-1 font-semibold text-[var(--text-primary)]">Retry</button></div> : !rows.length ? <p data-market-directory-state={search ? "no-match" : "empty"} className="p-3 text-xs text-[var(--text-secondary)]">{search ? `No matching ${categoryLabel}.` : open === "quick" && assetLayer === "sealed" ? NO_APPROVED_SEALED_QUICK_COPY : `No canonical ${categoryLabel} are currently published.`}</p> : groups ? groups.map((group) => <div key={group.era?.market_key || group.rows[0]?.parent_era_id}><h4 className="sticky top-0 bg-[var(--surface-page)] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-[var(--text-secondary)]">{group.era?.label || "Unknown Era"}</h4><ul>{group.rows.map((market) => row(market, rowIndex++))}</ul></div>) : <ul>{rows.map(row)}</ul>}</div>
    </div> : null}
  </section>;
}
