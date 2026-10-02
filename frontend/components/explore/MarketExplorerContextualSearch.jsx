"use client";
import { useCallback, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { SEARCH_MIN_LENGTH, SEARCH_PLACEHOLDER, createCatalogSearchController, leafContext, resolveSearchResultAction } from "@/lib/explore/marketExplorerCatalogSearch.mjs";

const NONE = -1;
function Thumb({ url }) {
  const [failed, setFailed] = useState(false);
  return url && !failed ? <img src={url} alt="" loading="lazy" onError={() => setFailed(true)} className="h-10 w-8 flex-none rounded object-contain" />
    : <span data-search-result-placeholder aria-hidden="true" className="h-10 w-8 flex-none rounded bg-white/5" />;
}

export default function MarketExplorerContextualSearch({ asset = "cards", onAddToBasket, onDirectSelect, onPreparedSelect,
  controllerFactory = createCatalogSearchController, disclosureOpen, onDisclosureChange, resetKey = 0 }) {
  const controller = useMemo(() => controllerFactory(), [controllerFactory]);
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const previousAssetRef = useRef(asset);
  const [text, setText] = useState(""); const [highlight, setHighlight] = useState(NONE); const [localOpen, setLocalOpen] = useState(false);
  const open = disclosureOpen ?? localOpen;
  const setOpen = useCallback((value) => { setLocalOpen(value); onDisclosureChange?.(value); }, [onDisclosureChange]);
  const listboxId = useId(); const inputRef = useRef(null); const rootRef = useRef(null);
  useEffect(() => () => controller.dispose(), [controller]);
  useEffect(() => { setText(""); setHighlight(NONE); setLocalOpen(false); controller.clear(); }, [controller, resetKey]);
  useEffect(() => {
    if (previousAssetRef.current !== asset) {
      previousAssetRef.current = asset;
      setHighlight(NONE);
      controller.search(text, asset);
    }
  }, [asset, controller, text]);
  useEffect(() => {
    // This search and the prepared-directory menus share one disclosure owner.
    // When search is closed it must not interpret pointer activity inside a Set,
    // Era or Quick popover as an instruction to clear that sibling disclosure.
    if (typeof document === "undefined" || !open) return undefined;
    const outside = (event) => {
      const root = rootRef.current;
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      if (root && (path.includes(root) || root.contains(event.target))) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", outside); return () => document.removeEventListener("pointerdown", outside);
  }, [open, setOpen]);
  const results = snapshot.results; const actions = useMemo(() => results.map(resolveSearchResultAction), [results]);
  const showPanel = open && (snapshot.status !== "idle" || text.trim().length >= SEARCH_MIN_LENGTH);
  const invoke = (index) => { const action = actions[index]?.primary; if (action?.kind === "market") onPreparedSelect?.(action.marketKey); else if (action?.kind === "direct") onDirectSelect?.(action.item); else if (action?.kind === "basket") onAddToBasket?.(action.item); };
  const clear = () => { setText(""); setHighlight(NONE); controller.clear(); inputRef.current?.focus(); };
  return <div ref={rootRef} data-market-explorer-contextual-search data-search-asset={asset} className={`relative mb-2 ${open ? "z-[82]" : "z-0"}`}>
    <label htmlFor={`${listboxId}-input`} className="sr-only">{SEARCH_PLACEHOLDER[asset]}</label>
    <div className="flex items-center rounded-md border border-[var(--border-subtle)] focus-within:ring-2 focus-within:ring-sky-400/70">
      <input ref={inputRef} id={`${listboxId}-input`} role="combobox" autoComplete="off" aria-expanded={showPanel} aria-controls={listboxId}
        aria-activedescendant={highlight >= 0 ? `${listboxId}-${highlight}` : undefined} data-market-explorer-search-input value={text}
        placeholder={SEARCH_PLACEHOLDER[asset]} onFocus={() => setOpen(true)}
        onChange={(event) => { setText(event.target.value); setHighlight(NONE); setOpen(true); controller.search(event.target.value, asset); }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setHighlight((i) => results.length ? Math.min(i + 1, results.length - 1) : NONE); }
          else if (event.key === "ArrowUp") { event.preventDefault(); setHighlight((i) => results.length ? Math.max(0, i - 1) : NONE); }
          else if (event.key === "Enter" && highlight >= 0) { event.preventDefault(); invoke(highlight); }
          else if (event.key === "Escape") { event.preventDefault(); setOpen(false); }
        }} className="min-h-10 w-full bg-transparent px-3 text-xs text-[var(--text-primary)] focus-visible:outline-none" />
      {text ? <button type="button" data-market-explorer-search-clear aria-label="Clear search" onClick={clear} className="px-2 text-sm text-[var(--text-secondary)]">×</button> : null}
    </div>
    {showPanel ? <div data-market-explorer-search-panel className="absolute left-0 right-0 z-[83] mt-1 max-h-[min(22rem,55vh)] overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-slate-950 p-1 shadow-2xl">
      {snapshot.status === "loading" ? <p role="status" className="px-3 py-2 text-xs text-[var(--text-secondary)]">Searching…</p> : null}
      {snapshot.status === "error" ? <div role="alert" data-market-explorer-search-state="error" className="flex items-center justify-between px-3 py-2 text-xs"><span>Search is temporarily unavailable.</span><button type="button" data-market-explorer-search-retry onClick={controller.retry}>Retry</button></div> : null}
      {snapshot.status === "ready" && !results.length ? <p className="px-3 py-2 text-xs text-[var(--text-secondary)]">No matches.</p> : null}
      <ul id={listboxId} role="listbox" aria-label={SEARCH_PLACEHOLDER[asset]}>{results.map((result, index) => {
        const primary = actions[index].primary; const disabled = !["basket", "direct", "market"].includes(primary.kind); const context = result.marketKey ? result.subtitle : leafContext(result);
        const startsLeafGroup = !result.marketKey && index > 0 && Boolean(results[index - 1]?.marketKey);
        return <li key={result.instrumentId || result.marketKey || `unavailable:${index}`} id={`${listboxId}-${index}`} role="option" aria-selected={false} aria-disabled={disabled || undefined}
          data-search-result-kind={result.marketKey ? "market" : "leaf"} data-search-highlighted={index === highlight ? "true" : "false"}
          onClick={() => invoke(index)} className={`flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 ${startsLeafGroup ? "mt-2 border-t border-[var(--border-subtle)] pt-3" : ""} ${index === highlight ? "bg-white/[.08] ring-1 ring-sky-400/70" : "hover:bg-white/[.05]"}`}>
          <Thumb url={result.imageUrl} /><span className="min-w-0 flex-1"><strong className="block truncate text-xs">{result.displayName || "Graded cards unavailable"}</strong>
            {context ? <span data-search-result-context className="block truncate text-[10px] text-[var(--text-secondary)]">{context}</span> : null}
            {result.marketPrice != null ? <span data-search-result-price className="block text-[10px] font-semibold tabular-nums">{Number(result.marketPrice).toLocaleString(undefined, { style: "currency", currency: "USD" })}</span> : null}
            {primary.reason ? <span data-search-result-reason className="block text-[10px] text-[var(--text-secondary)]">{primary.reason}</span> : null}</span>
          {primary.kind === "market" ? <button type="button" data-search-primary="market" onClick={(event) => { event.stopPropagation(); invoke(index); }} className="rounded border border-sky-400/50 px-2 py-1 text-[10px] font-semibold text-sky-200">Select market</button> : primary.kind === "direct" ? <button type="button" data-search-primary="direct" onClick={(event) => { event.stopPropagation(); invoke(index); }} className="rounded border border-[rgba(45,212,191,.5)] px-2 py-1 text-[10px] font-semibold text-[rgb(45,212,191)]">View</button> : null}
        </li>;
      })}</ul>
      {snapshot.nextCursor != null ? <button type="button" data-market-explorer-search-more disabled={snapshot.loadingMore}
        onClick={() => controller.loadMore()} className="mt-1 w-full rounded-md border border-[var(--border-subtle)] px-3 py-2 text-xs font-semibold text-[var(--text-primary)] hover:bg-white/[.07] disabled:cursor-wait disabled:opacity-50">
        {snapshot.loadingMore ? "Loading more…" : "Load more results"}
      </button> : null}
    </div> : null}
  </div>;
}
