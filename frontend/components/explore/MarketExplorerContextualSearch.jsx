"use client";
import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  SEARCH_MIN_LENGTH,
  SEARCH_PLACEHOLDER,
  createCatalogSearchController,
  resolveSearchResultAction,
  resultKindLabel,
} from "@/lib/explore/marketExplorerCatalogSearch.mjs";

const NONE = -1;

function Thumb({ url }) {
  const [failed, setFailed] = useState(false);
  // Null / failed image is an intentional neutral placeholder, never a broken icon.
  return url && !failed
    ? <img src={url} alt="" loading="lazy" onError={() => setFailed(true)} className="h-10 w-8 flex-none rounded object-contain" />
    : <span data-search-result-placeholder aria-hidden="true" className="h-10 w-8 flex-none rounded bg-white/5" />;
}

/**
 * ONE contextual search field, scoped by the active BROWSE asset. A market result
 * activates through the same prepared loader as Browse (`onActivateMarket`); an
 * instrument result offers "Open detail" and, secondarily, the existing Exact
 * Basket pathway (`onAddToBasket`) -- it is never presented as an aggregate.
 */
export default function MarketExplorerContextualSearch({
  asset = "cards",
  activeKeys = [],
  pendingKeys = [],
  failedKeys = [],
  onActivateMarket,
  onAddToBasket,
  controllerFactory = createCatalogSearchController,
}) {
  const controller = useMemo(() => controllerFactory(), [controllerFactory]);
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const [text, setText] = useState("");
  const [highlight, setHighlight] = useState(NONE);
  const [open, setOpen] = useState(false);
  const listboxId = useId();
  const inputRef = useRef(null);
  const rootRef = useRef(null);
  useEffect(() => () => controller.dispose(), [controller]);
  // Asset switch: same field, new scope. The previous asset's results never linger.
  useEffect(() => { setHighlight(NONE); controller.search(text, asset); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [asset]);
  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const outside = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);

  const results = snapshot.results;
  const actions = useMemo(() => results.map((result) => resolveSearchResultAction(result)), [results]);
  const showPanel = open && (snapshot.status !== "idle" || text.trim().length >= SEARCH_MIN_LENGTH);

  const invoke = (index) => {
    const result = results[index]; const action = actions[index]?.primary;
    if (!result || !action) return;
    if (action.kind === "activate") onActivateMarket?.(action.marketKey);
    else if (action.kind === "detail") globalThis.open?.(action.href, "_blank", "noopener,noreferrer");
  };
  const clear = () => { setText(""); setHighlight(NONE); controller.clear(); inputRef.current?.focus(); };

  return <div ref={rootRef} data-market-explorer-contextual-search data-search-asset={asset} className="relative mb-2">
    <label htmlFor={`${listboxId}-input`} className="sr-only">{SEARCH_PLACEHOLDER[asset]}</label>
    <div className="flex items-center rounded-md border border-[var(--border-subtle)] focus-within:ring-2 focus-within:ring-sky-400/70">
      <input
        ref={inputRef} id={`${listboxId}-input`} type="text" role="combobox" autoComplete="off"
        aria-autocomplete="list" aria-expanded={showPanel} aria-controls={listboxId}
        aria-activedescendant={highlight >= 0 && highlight < results.length ? `${listboxId}-${highlight}` : undefined}
        data-market-explorer-search-input value={text} placeholder={SEARCH_PLACEHOLDER[asset]}
        onFocus={() => setOpen(true)}
        onChange={(event) => { setText(event.target.value); setHighlight(NONE); setOpen(true); controller.search(event.target.value, asset); }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setHighlight((i) => (results.length ? Math.min(i + 1, results.length - 1) : NONE)); }
          else if (event.key === "ArrowUp") { event.preventDefault(); setHighlight((i) => (results.length ? (i <= 0 ? 0 : i - 1) : NONE)); }
          else if (event.key === "Enter" && highlight >= 0) { event.preventDefault(); invoke(highlight); }
          else if (event.key === "Escape") { event.preventDefault(); if (text) clear(); else setOpen(false); }
        }}
        className="min-h-10 w-full bg-transparent px-3 text-xs text-[var(--text-primary)] focus-visible:outline-none"
      />
      {text ? <button type="button" data-market-explorer-search-clear aria-label="Clear search" onClick={clear} className="px-2 text-sm text-[var(--text-secondary)]">×</button> : null}
    </div>
    {showPanel ? <div data-market-explorer-search-panel className="absolute left-0 right-0 z-40 mt-1 max-h-[min(22rem,55vh)] overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-1 shadow-2xl">
      {snapshot.status === "loading" ? <p role="status" data-market-explorer-search-state="loading" className="px-3 py-2 text-xs text-[var(--text-secondary)]">Searching…</p> : null}
      {snapshot.status === "error" ? <div role="alert" data-market-explorer-search-state="error" className="flex items-center justify-between gap-2 px-3 py-2 text-xs text-[var(--text-secondary)]"><span>Search is temporarily unavailable.</span><button type="button" data-market-explorer-search-retry onClick={() => controller.retry()} className="rounded border border-[var(--border-subtle)] px-2 py-1 font-semibold text-[var(--text-primary)]">Retry</button></div> : null}
      {snapshot.status === "ready" && !results.length ? <p data-market-explorer-search-state="empty" className="px-3 py-2 text-xs text-[var(--text-secondary)]">No matches.</p> : null}
      <ul id={listboxId} role="listbox" aria-label={SEARCH_PLACEHOLDER[asset]}>
        {results.map((result, index) => {
          const { primary, secondary } = actions[index];
          const key = result.market_key || result.instrument_id || `${result.result_kind}:${result.label}:${index}`;
          const active = primary.kind === "activate" && activeKeys.includes(primary.marketKey);
          const loading = primary.kind === "activate" && !active && pendingKeys.includes(primary.marketKey);
          const failed = primary.kind === "activate" && !active && !loading && failedKeys.includes(primary.marketKey);
          const disabled = primary.kind === "unavailable" || primary.kind === "none";
          return <li key={`${key}:${index}`} id={`${listboxId}-${index}`} role="option" aria-selected={active} aria-disabled={disabled || undefined}
            data-search-result-kind={result.result_kind} data-search-highlighted={index === highlight ? "true" : "false"}
            className={`flex items-center gap-2 rounded-md px-2 py-1.5 ${index === highlight ? "bg-white/[.08] ring-1 ring-inset ring-sky-400/70" : "hover:bg-white/[.05]"}`}>
            <Thumb url={result.image_url} />
            <span className="min-w-0 flex-1">
              <strong className="block truncate text-xs text-[var(--text-primary)]">{result.label}</strong>
              <span className="block truncate text-[10px] text-[var(--text-secondary)]"><b data-search-result-type className="mr-1 rounded bg-white/10 px-1 py-px font-semibold">{resultKindLabel(result)}</b>{result.subtitle}</span>
              {disabled && primary.reason ? <span data-search-result-reason className="block text-[10px] text-[var(--text-secondary)]">{primary.reason}</span> : null}
            </span>
            {primary.kind === "activate" ? <button type="button" data-search-primary="activate" data-search-market={primary.marketKey} onClick={() => invoke(index)} className="rounded border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold text-[var(--text-primary)]">{active ? "Remove" : loading ? "Adding…" : failed ? "Retry" : "+ Compare"}</button> : null}
            {primary.kind === "detail" ? <a data-search-primary="detail" href={primary.href} target="_blank" rel="noopener noreferrer" className="rounded border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold text-[var(--text-primary)]">Open detail</a> : null}
            {secondary?.kind === "basket" ? <button type="button" data-search-secondary="basket" onClick={() => onAddToBasket?.(secondary.item)} className="rounded border border-[rgba(45,212,191,.5)] px-2 py-1 text-[10px] font-semibold text-[rgb(45,212,191)]">Add to Exact Basket</button> : null}
          </li>;
        })}
      </ul>
    </div> : null}
  </div>;
}
