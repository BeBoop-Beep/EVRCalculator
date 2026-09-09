"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { MAX_EXPLICIT_INSTRUMENTS } from "@/lib/explore/marketExplorerQuery.mjs";

const FOCUSABLE_SELECTOR = [
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "a[href]",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

export function exactItemLabel(item) {
  const parts = item.asset === "sealed"
    ? [item.name, item.setName, item.productFamily || item.productType, item.variantLabel]
    : [item.name, item.setName, item.cardNumber ? `#${item.cardNumber}` : null, item.rarity, item.edition, item.printingType, item.specialType];
  return parts.filter(Boolean).join(" · ");
}

function ItemArtwork({ item, asset, compact = false }) {
  const [failed, setFailed] = useState(false);
  const size = compact
    ? (asset === "sealed" ? "h-12 w-12" : "h-14 w-10")
    : (asset === "sealed" ? "h-24 w-24" : "h-28 w-20");
  if (!item.imageUrl || failed) {
    return <span data-exact-artwork-placeholder aria-hidden="true" className={`${size} flex-none rounded bg-white/5`} />;
  }
  return <img src={item.imageUrl} alt={`${item.name} artwork`} onError={() => setFailed(true)} className={`${size} flex-none rounded object-contain`} />;
}

export default function MarketExplorerExactItemPicker({
  asset,
  selectedItems = [],
  onChange,
  open = true,
  onClose,
  onCancelEdit,
  onBuild,
  onSaveAsNew,
  executionLocked = false,
  buildLabel = "Build Market",
  buildStatus = "idle",
  buildMessage = "",
  narrowingSummary = [],
  onClearNarrowing,
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const requestId = useRef(0);
  const dialogRef = useRef(null);
  const searchRef = useRef(null);
  const selectedIds = useMemo(() => new Set(selectedItems.map((item) => item.instrumentId)), [selectedItems]);
  const atMaximum = selectedItems.length >= MAX_EXPLICIT_INSTRUMENTS;

  useEffect(() => {
    if (!open || typeof document === "undefined") return undefined;
    searchRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const key = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose?.();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const nodes = [...dialogRef.current.querySelectorAll(FOCUSABLE_SELECTOR)];
      if (!nodes.length) return;
      if (event.shiftKey && document.activeElement === nodes[0]) {
        event.preventDefault();
        nodes.at(-1)?.focus();
      } else if (!event.shiftKey && document.activeElement === nodes.at(-1)) {
        event.preventDefault();
        nodes[0]?.focus();
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose, open]);

  useEffect(() => {
    const needle = query.trim();
    requestId.current += 1;
    const token = requestId.current;
    if (needle.length < 2) {
      setResults([]);
      setStatus("idle");
      setMessage("");
      return undefined;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setStatus("loading");
      setMessage("");
      try {
        const response = await fetch(`/api/market/explorer/instruments/search?q=${encodeURIComponent(needle)}&asset=${asset}&limit=20`, { signal: controller.signal, credentials: "include" });
        const payload = await response.json().catch(() => null);
        if (token !== requestId.current) return;
        if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || "Unable to search exact items.");
        setResults((payload?.items || []).filter((item) => item.asset === asset));
        setStatus("ready");
      } catch (error) {
        if (error?.name !== "AbortError" && token === requestId.current) {
          setResults([]);
          setStatus("error");
          setMessage(error?.message || "Unable to search exact items.");
        }
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [asset, query]);

  const add = (item) => {
    if (!atMaximum && !selectedIds.has(item.instrumentId) && item.asset === asset) onChange?.([...selectedItems, item]);
  };
  if (!open) return null;

  return (
    <div data-market-explorer-exact-workspace className="fixed inset-0 z-[90] flex bg-slate-950/80 backdrop-blur-sm desk:items-center desk:justify-center desk:p-6">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={`exact-title-${asset}`} className="flex h-[100dvh] w-full flex-col overflow-hidden border border-[var(--border-subtle)] bg-[var(--surface-page)] shadow-2xl desk:h-auto desk:max-h-[86vh] desk:max-w-5xl desk:rounded-2xl">
        <header className="flex flex-none items-center gap-4 border-b border-[var(--border-subtle)] px-4 py-3 sm:px-6">
          <div className="flex-1"><h2 id={`exact-title-${asset}`} className="text-lg font-semibold text-[var(--text-primary)]">Select Exact {asset === "sealed" ? "Sealed Products" : "Cards"}</h2><p data-exact-item-count className="text-xs text-[var(--text-secondary)]">{selectedItems.length} / 25 selected</p></div>
          <button type="button" aria-label="Close exact item workspace" onClick={onClose} className="min-h-11 min-w-11 rounded-full border border-[var(--border-subtle)] text-xl">×</button>
        </header>
        <div className="flex-none border-b border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-3 sm:px-6">
          <label className="text-xs font-semibold" htmlFor={`exact-search-${asset}`}>Search exact items</label>
          <input ref={searchRef} id={`exact-search-${asset}`} type="search" value={query} placeholder={asset === "sealed" ? "Search sealed products…" : "Search cards…"} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && results.length) { event.preventDefault(); add(results[0]); } }} className="mt-1 min-h-12 w-full rounded-lg border border-[var(--border-subtle)] bg-transparent px-4 text-base" />
          {narrowingSummary.length ? <div data-exact-narrowing className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-400/30 p-2 text-xs"><span><strong>Additional Builder filters:</strong> {narrowingSummary.join(" · ")}</span><button type="button" onClick={onClearNarrowing} className="text-[rgb(45,212,191)]">Clear narrowing filters</button></div> : null}
        </div>
        <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_minmax(8rem,30vh)] desk:grid-cols-[1.8fr_1fr] desk:grid-rows-1">
          <section aria-label="Search results" className="min-h-0 overflow-y-auto p-4 sm:p-6">
            {atMaximum ? <p id="exact-maximum" role="status">25 / 25 selected. Remove an item to add another.</p> : null}
            {status === "loading" ? <p role="status">Searching…</p> : null}
            {message ? <p role="alert" className="text-red-200">{message}</p> : null}
            {status === "ready" ? <ul role="listbox" aria-label="Exact item search results" className="space-y-2">{results.length ? results.map((item) => {
              const selected = selectedIds.has(item.instrumentId);
              const unavailable = atMaximum && !selected;
              return <li key={item.instrumentId}><button type="button" role="option" aria-selected={selected} aria-disabled={unavailable} aria-describedby={unavailable ? "exact-maximum" : undefined} onClick={() => selected || unavailable ? undefined : add(item)} className={`flex min-h-28 w-full items-center gap-4 rounded-xl border p-3 text-left ${selected ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.10)]" : "border-[var(--border-subtle)]"}`}><ItemArtwork item={item} asset={asset} /><span className="min-w-0 flex-1"><strong className="block">{item.name}</strong><span className="mt-1 block text-xs text-[var(--text-secondary)]">{exactItemLabel({ ...item, name: null })}</span></span><b className="text-xs text-[rgb(45,212,191)]">{selected ? "Added ✓" : unavailable ? "25 / 25 selected" : "Add"}</b></button></li>;
            }) : <li className="py-10 text-center text-sm">No exact items found.</li>}</ul> : null}
          </section>
          <aside className="min-h-0 overflow-y-auto border-t border-[var(--border-subtle)] p-4 desk:border-l desk:border-t-0 sm:p-6">
            <h3 className="font-semibold">Selected basket</h3>
            {selectedItems.length ? <ul data-exact-selected-items className="mt-2 space-y-2">{selectedItems.map((item) => <li key={item.instrumentId} className="flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] p-2 text-xs"><ItemArtwork item={item} asset={asset} compact /><span className="min-w-0 flex-1">{exactItemLabel(item)}</span><button type="button" aria-label={`Remove ${exactItemLabel(item)}`} onClick={() => onChange?.(selectedItems.filter((row) => row.instrumentId !== item.instrumentId))} className="min-h-9 px-2">×</button></li>)}</ul> : <p className="mt-2 text-xs text-[var(--text-secondary)]">Search and add 1–25 items.</p>}
          </aside>
        </div>
        <footer className="flex-none border-t border-[var(--border-subtle)] bg-[var(--surface-page)] p-3 pb-[max(.75rem,env(safe-area-inset-bottom))] sm:px-6">
          {buildMessage ? <p role={buildStatus === "error" ? "alert" : "status"} className={`mb-2 rounded-lg border p-2 text-xs ${buildStatus === "error" ? "border-red-400/40 text-red-200" : "border-[var(--border-subtle)]"}`}>{buildStatus === "error" ? <strong className="block uppercase">Could not build market</strong> : null}{buildMessage}</p> : null}
          <div className="flex flex-wrap justify-end gap-2">
            {onCancelEdit ? <button type="button" onClick={onCancelEdit} className="min-h-11 rounded-lg border px-4">Cancel edits</button> : null}
            <button type="button" onClick={onClose} className="min-h-11 rounded-lg border px-5">Close</button>
            {onSaveAsNew ? <button type="button" disabled={!selectedItems.length || buildStatus === "building"} onClick={onSaveAsNew} className="min-h-11 rounded-lg border px-5">Save as new{executionLocked ? " 🔒" : ""}</button> : null}
            <button type="button" disabled={!selectedItems.length || buildStatus === "building"} onClick={onBuild} className="min-h-11 rounded-lg border border-[rgb(45,212,191)] bg-[rgba(45,212,191,.16)] px-5 font-semibold text-[rgb(45,212,191)] disabled:opacity-45">{buildStatus === "building" ? "Building…" : executionLocked ? "Requires Index Premium 🔒" : buildLabel}</button>
          </div>
        </footer>
      </div>
    </div>
  );
}
