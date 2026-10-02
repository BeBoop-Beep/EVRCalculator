"use client";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { groupPreparedDirectory } from "@/lib/explore/marketExplorerPrepared.mjs";
import { NO_APPROVED_SEALED_QUICK_COPY } from "@/lib/explore/marketExplorerAssetOptions.mjs";
import MarketExplorerContextualSearch from "./MarketExplorerContextualSearch";
import { formatExplorerMarketLabel } from "@/lib/explore/marketExplorerLabels.mjs";

const CARD_CATEGORIES = [["sets", "Sets"], ["eras", "Eras"], ["quick", "Quick Markets"]];
// Sealed IA: Sets, Eras, Quick Markets (Sealed Types + Screens render in the Analyze
// section; the Build trigger is shared). "Sealed Markets" stays as the flat
// list of every published sealed market.
// V2 Sealed Browse IA: Sets, Eras, Quick Markets. Sealed Types and Screens live
// beside one another under Analyze; Build is the shared exact-market action.
const SEALED_V2_CATEGORIES = [["sets", "Sets"], ["eras", "Eras"], ["quick", "Quick Markets"]];
// V1 compatibility keeps the same final IA; missing Set/Era/Quick rows render the
// explicit awaiting-publication states instead of reviving "Sealed Markets".
const SEALED_V1_CATEGORIES = SEALED_V2_CATEGORIES;
const CATEGORIES = CARD_CATEGORIES;
const AWAITING_COPY = Object.freeze({
  sets: "Sealed Set markets are awaiting the current prepared generation.",
  eras: "Sealed Era markets are awaiting the current prepared generation.",
});
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
  // Card Quick copy predates the sealed V2 publication. Sealed Quick labels and
  // definitions are DB authority and must not be relabelled as card markets.
  if (market?.asset === "sealed") return { label: formatExplorerMarketLabel(market), description: null };
  const copy = market?.market_type === "curated" ? QUICK_COPY[market.label] : null;
  return { label: copy?.[0] || formatExplorerMarketLabel(market), description: copy?.[1] || null };
};

export default function MarketExplorerBrowse({ directory = [], directoryStatus = "ready", activeKeys = [], pendingKeys = [], failedKeys = [], canCompare, onSelect, onCompare, onBuild, assetLayer: assetLayerProp, onAssetLayerChange, gradedReason = null, onAddToBasket, onDirectSelect, enableContextualSearch = true, resetKey = 0, disclosureOpen, onDisclosureChange }) {
  const [internalOpen, setInternalOpen] = useState(null);
  const open = disclosureOpen === undefined ? internalOpen : disclosureOpen;
  const setOpen = useCallback((next) => {
    const resolved = typeof next === "function" ? next(open) : next;
    if (disclosureOpen === undefined) setInternalOpen(resolved);
    onDisclosureChange?.(resolved);
  }, [disclosureOpen, onDisclosureChange, open]);
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
  // V2 mode = the directory is published by the V2 surface. Decided from row data only.
  const v2Mode = useMemo(() => directory.some((row) => row?.surface_version === "v2"), [directory]);
  const SEALED_CATEGORIES = v2Mode ? SEALED_V2_CATEGORIES : SEALED_V1_CATEGORIES;
  const layerRows = useMemo(() => directory.filter((row) => {
    // V2 publishes explicit asset identity. Keep Browse layers exact so future
    // Graded rows can never leak into Cards merely because they are "not sealed".
    if (v2Mode) return row?.asset === assetLayer;
    // Legacy prepared generations predate the full asset contract.
    return assetLayer === "sealed" ? row?.asset === "sealed" : row?.asset !== "sealed";
  }), [directory, assetLayer, v2Mode]);
  const grouped = useMemo(() => groupPreparedDirectory(layerRows, search), [layerRows, search]);
  const parentGroup = grouped.parents.length ? [{ era: { label: "Whole market", market_key: "parents" }, rows: grouped.parents }] : [];
  const rows = open === "eras" ? grouped.eras : open === "quick" ? grouped.quick : [...grouped.parents, ...grouped.sets.flatMap((group) => group.rows)];
  const groups = open === "sets" ? [...parentGroup, ...grouped.sets] : null;
  useEffect(() => { if (open) requestAnimationFrame(() => searchRef.current?.focus()); }, [open]);
  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const outside = (event) => {
      const root = rootRef.current;
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      if (root && (path.includes(root) || root.contains(event.target))) return;
      setOpen(null); setSearch(""); setHighlightedIndex(NO_HIGHLIGHT);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [setOpen]);
  const close = (restoreFocus = false) => {
    const trigger = triggerRefs.current.get(open);
    setOpen(null); setSearch(""); setHighlightedIndex(NO_HIGHLIGHT);
    if (restoreFocus) requestAnimationFrame(() => trigger?.focus());
  };
  // One-market users are SWITCHING: the menu closes once they choose. Compare-capable users keep it open to add more.
  const choose = (key) => { onSelect(key); if (!canCompare) close(); };
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
      {/* PRIMARY ACTION IS THE ROW ITSELF (open this market). The secondary control only
          exists to remove an active market or retry a failed one; there is no per-row
          compare/upsell button. */}
      {canCompare && (active || failed) ? <button type="button" data-compare-market={market.market_key} aria-pressed={active} onClick={() => onCompare(market.market_key)} className={`mr-1 rounded border px-2 py-1 text-[10px] font-semibold ${active ? "border-[rgba(248,113,113,.45)] text-[rgb(248,113,113)]" : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>{active ? "Remove" : "Retry"}</button> : null}
      {canCompare && loading ? <span data-market-row-adding className="mr-2 text-[10px] text-[var(--text-secondary)]">Adding…</span> : null}
    </li>;
  };
  let rowIndex = 0;
  const categoryLabel = (assetLayer === "sealed" ? SEALED_CATEGORIES : CATEGORIES).find(([id]) => id === open)?.[1];
  return <section ref={rootRef} data-market-explorer-browse aria-labelledby="browse-markets-heading" className={`relative min-w-0 px-3 pb-3 pt-3 ${open ? "z-[80]" : "z-0"}`}>
    <h3 id="browse-markets-heading" className="text-sm font-semibold text-[var(--text-primary)]">Market Directory</h3><p className="mb-3 text-[11px] text-[var(--text-secondary)]">Search prepared markets or create your own.</p>
    <div role="group" aria-label="Browse context" data-market-directory-asset-layer className="mb-2 grid grid-cols-3 gap-1 rounded-lg border border-[var(--border-subtle)] p-0.5">
      {ASSET_LAYERS.map(([id, label]) => <button key={id} type="button" data-market-directory-asset={id} aria-pressed={assetLayer === id} onClick={() => { setAssetLayer(id); setOpen(null); setSearch(""); setHighlightedIndex(NO_HIGHLIGHT); }} className={`min-h-8 rounded-md px-1 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70 ${assetLayer === id ? "bg-sky-400/15 text-sky-200" : "text-[var(--text-primary)] hover:bg-white/[.05]"}`}>{label}</button>)}
    </div>
    {enableContextualSearch ? <MarketExplorerContextualSearch asset={assetLayer} onAddToBasket={onAddToBasket} onDirectSelect={onDirectSelect} onPreparedSelect={choose}
      disclosureOpen={open === "search"} onDisclosureChange={(next) => setOpen(next ? "search" : null)} resetKey={resetKey} /> : null}
    {assetLayer === "graded"
      ? <div role="status" data-market-directory-state="graded-unavailable" className="rounded-md border border-[var(--border-subtle)] px-3 py-3 text-xs text-[var(--text-secondary)]"><strong className="block text-[var(--text-primary)]">Graded markets are unavailable</strong><span data-graded-reason>{gradedReason || GRADED_FALLBACK_REASON}</span></div>
      : <div className="relative grid grid-cols-2 gap-2">
      {(assetLayer === "sealed" ? SEALED_CATEGORIES : CARD_CATEGORIES).map(([id, label]) => <button key={id} data-market-directory-category={id} ref={(node) => { if (node) triggerRefs.current.set(id, node); else triggerRefs.current.delete(id); }} type="button" aria-haspopup="listbox" aria-expanded={open === id} aria-controls={open === id ? listboxId : undefined} onClick={() => { setOpen((value) => value === id ? null : id); setSearch(""); setHighlightedIndex(NO_HIGHLIGHT); }} className={`min-h-10 rounded-md border px-2 text-xs font-semibold ${open === id ? "border-sky-400 bg-sky-400/10 text-sky-200" : "border-slate-500/50 bg-slate-400/[.06] text-[var(--text-primary)] hover:border-sky-400/60"}`}>{label} <span aria-hidden="true">▾</span></button>)}
      <button type="button" data-market-explorer-build-trigger onClick={onBuild} className="min-h-10 rounded-md border border-[rgb(45,212,191)] bg-[rgba(45,212,191,.16)] px-2 text-xs font-bold text-[rgb(45,212,191)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(45,212,191)]"><span aria-hidden="true">＋</span> Build Your Market</button>
    </div>}
    {open && open !== "search" ? <div data-market-directory-popover data-market-directory-interaction-boundary
      onPointerDownCapture={(event) => event.stopPropagation()}
      onWheelCapture={(event) => event.stopPropagation()}
      className="absolute left-3 right-3 z-[81] mt-2 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-slate-950 shadow-2xl">
      <>
      <input ref={searchRef} role="combobox" aria-expanded="true" aria-controls={listboxId} aria-activedescendant={highlightedIndex >= 0 && highlightedIndex < rows.length ? `${listboxId}-${highlightedIndex}` : undefined} data-market-browser-search value={search} onChange={(event) => { setSearch(event.target.value); setHighlightedIndex(NO_HIGHLIGHT); }} onKeyDown={(event) => { if (event.key === "ArrowDown") { event.preventDefault(); setHighlightedIndex((i) => (rows.length ? (i < 0 ? 0 : Math.min(i + 1, rows.length - 1)) : NO_HIGHLIGHT)); } if (event.key === "ArrowUp") { event.preventDefault(); setHighlightedIndex((i) => (rows.length ? (i < 0 ? rows.length - 1 : Math.max(i - 1, 0)) : NO_HIGHLIGHT)); } if (event.key === "Enter") { const target = highlightedIndex >= 0 && highlightedIndex < rows.length ? rows[highlightedIndex] : (search.trim() && rows.length === 1 ? rows[0] : null); if (target) { event.preventDefault(); choose(target.market_key); } } if (event.key === "Escape") { event.preventDefault(); close(true); } }} placeholder={`Search ${categoryLabel}…`} aria-label={`Search ${categoryLabel}`} className="w-full border-b border-[var(--border-subtle)] bg-transparent px-3 py-3 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-400/70" />
      <div id={listboxId} role="listbox" aria-label={`${categoryLabel} prepared markets`} data-market-directory-scroll-region className="max-h-[min(25rem,55vh)] overflow-y-auto overscroll-contain p-2">{directoryStatus === "unavailable" ? <div role="alert" data-market-directory-state="unavailable" className="p-3 text-xs text-[var(--text-secondary)]"><p>Market directory is temporarily unavailable.</p><button type="button" onClick={() => globalThis.location?.reload()} className="mt-2 rounded border border-[var(--border-subtle)] px-2 py-1 font-semibold text-[var(--text-primary)]">Retry</button></div> : !rows.length ? <p data-market-directory-state={search ? "no-match" : "empty"} className="p-3 text-xs text-[var(--text-secondary)]">{search ? `No matching ${categoryLabel}.` : open === "quick" && assetLayer === "sealed" ? <span data-sealed-quick-empty className="block"><strong className="block text-[var(--text-primary)]">Quick Markets</strong>{NO_APPROVED_SEALED_QUICK_COPY}</span> : assetLayer === "sealed" && AWAITING_COPY[open] ? <span data-sealed-awaiting={open} className="block">{AWAITING_COPY[open]}</span> : `No canonical ${categoryLabel} are currently published.`}</p> : groups && groups.length ? groups.map((group) => <div key={group.era?.market_key || group.rows[0]?.parent_era_id}><h4 className="sticky top-0 bg-[var(--surface-page)] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-[var(--text-secondary)]">{group.era?.label || "Unknown Era"}</h4><ul>{group.rows.map((market) => row(market, rowIndex++))}</ul></div>) : <ul>{rows.map(row)}</ul>}</div>{!canCompare && open !== "types" ? <p data-compare-upsell className="border-t border-[var(--border-subtle)] px-3 py-2 text-[10px] text-[var(--text-secondary)]">Selecting a market switches the chart to it. Comparing several markets side by side is included with Index+.</p> : null}
      </>
    </div> : null}
  </section>;
}
