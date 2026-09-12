"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { MAX_EXPLICIT_INSTRUMENTS } from "@/lib/explore/marketExplorerQuery.mjs";

const identity = (item) => `${item.asset}:${item.instrumentId}`;
export const exactItemLabel = (item) => (item.asset === "sealed"
  ? [item.name, item.setName, item.productFamily || item.productType, item.variantLabel]
  : [item.name, item.setName, item.cardNumber ? `#${item.cardNumber}` : null, item.rarity, item.edition, item.printingType, item.specialType]
).filter(Boolean).join(" · ");

function Artwork({ item, compact = false }) {
  const [failed, setFailed] = useState(false);
  const size = compact ? (item.asset === "sealed" ? "h-12 w-12" : "h-14 w-10") : (item.asset === "sealed" ? "h-24 w-24" : "h-28 w-20");
  return item.imageUrl && !failed ? <img src={item.imageUrl} alt={`${item.name} artwork`} onError={() => setFailed(true)} className={`${size} flex-none rounded object-contain`} /> : <span data-exact-artwork-placeholder className={`${size} flex-none rounded bg-white/5`} />;
}

export default function MarketExplorerExactItemPicker({ selectedItems = [], onChange, open = true, onClose, onCancelEdit, onBuild, onSaveAsNew, executionLocked = false, buildLabel = "Build Basket", buildStatus = "idle", buildMessage = "" }) {
  const [scope, setScope] = useState("all");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const requestId = useRef(0);
  const searchRef = useRef(null);
  const selectedIds = useMemo(() => new Set(selectedItems.map(identity)), [selectedItems]);
  const atMaximum = selectedItems.length >= MAX_EXPLICIT_INSTRUMENTS;
  useEffect(() => { if (open) searchRef.current?.focus(); }, [open]);
  useEffect(() => {
    const needle = query.trim(); const token = ++requestId.current;
    if (needle.length < 2) { setResults([]); setStatus("idle"); setMessage(""); return undefined; }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setStatus("loading"); setMessage("");
      try {
        const response = await fetch(`/api/market/explorer/instruments/search?q=${encodeURIComponent(needle)}&asset=${scope}&limit=20`, { signal: controller.signal, credentials: "include" });
        const payload = await response.json().catch(() => null);
        if (token !== requestId.current) return;
        if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || "Unable to search exact items.");
        setResults(payload?.items || []); setStatus("ready");
      } catch (error) { if (error?.name !== "AbortError" && token === requestId.current) { setResults([]); setStatus("error"); setMessage(error?.message || "Unable to search exact items."); } }
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [scope, query]);
  if (!open) return null;
  const add = (item) => { if (!atMaximum && !selectedIds.has(identity(item))) onChange?.([...selectedItems, item]); };
  const remove = (item) => onChange?.(selectedItems.filter((row) => identity(row) !== identity(item)));
  return <div data-market-explorer-exact-workspace className="fixed inset-0 z-[90] flex bg-slate-950/80 backdrop-blur-sm desk:items-center desk:justify-center desk:p-6"><div role="dialog" aria-modal="true" aria-labelledby="exact-basket-title" className="flex h-[100dvh] w-full flex-col overflow-hidden border border-[var(--border-subtle)] bg-[var(--surface-page)] shadow-2xl desk:h-auto desk:max-h-[86vh] desk:max-w-5xl desk:rounded-2xl">
    <header className="flex items-center gap-4 border-b border-[var(--border-subtle)] px-4 py-3 sm:px-6"><div className="flex-1"><h2 id="exact-basket-title" className="text-lg font-semibold">Exact Basket</h2><p className="text-xs text-[var(--text-secondary)]">One physical unit of every selected Card or Sealed Product.</p><p data-exact-item-count className="text-xs">{selectedItems.length} / 25 selected</p></div><button type="button" aria-label="Close exact basket" onClick={onClose} className="min-h-11 min-w-11 rounded-full border">×</button></header>
    <div className="border-b border-[var(--border-subtle)] px-4 py-3 sm:px-6"><div role="tablist" aria-label="Search scope" className="mb-2 flex gap-2">{["all", "cards", "sealed"].map((value) => <button key={value} type="button" role="tab" aria-selected={scope === value} onClick={() => setScope(value)} className="rounded-md border px-3 py-1 text-xs capitalize">{value}</button>)}</div><label className="text-xs font-semibold" htmlFor="exact-search">Search exact items</label><input ref={searchRef} id="exact-search" type="search" value={query} placeholder="Search Cards and Sealed Products…" onChange={(event) => setQuery(event.target.value)} className="mt-1 min-h-12 w-full rounded-lg border border-[var(--border-subtle)] bg-transparent px-4" /></div>
    <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_minmax(8rem,30vh)] desk:grid-cols-[1.8fr_1fr] desk:grid-rows-1"><section aria-label="Search results" className="overflow-y-auto p-4 sm:p-6">{atMaximum ? <p role="status">25 / 25 selected. Remove an item to add another.</p> : null}{status === "loading" ? <p role="status">Searching…</p> : null}{message ? <p role="alert">{message}</p> : null}{status === "ready" ? <ul role="listbox" className="space-y-2">{results.map((item) => { const selected = selectedIds.has(identity(item)); const disabled = atMaximum && !selected; return <li key={identity(item)}><button type="button" role="option" aria-selected={selected} aria-disabled={disabled} onClick={() => selected || disabled ? undefined : add(item)} className="flex min-h-28 w-full items-center gap-4 rounded-xl border p-3 text-left"><Artwork item={item} /><span className="min-w-0 flex-1"><strong className="block">{item.name}</strong><span className="text-xs">{item.asset === "sealed" ? "Sealed" : "Card"} · {exactItemLabel({ ...item, name: null })}</span></span><b>{selected ? "Added ✓" : disabled ? "Full" : "Add"}</b></button></li>; })}</ul> : null}</section>
      <aside className="overflow-y-auto border-t p-4 desk:border-l desk:border-t-0 sm:p-6"><h3 className="font-semibold">Selected basket</h3>{selectedItems.length ? <ul data-exact-selected-items className="mt-2 space-y-2">{selectedItems.map((item) => <li key={identity(item)} className="flex items-center gap-2 rounded-lg border p-2 text-xs"><Artwork item={item} compact /><span className="min-w-0 flex-1"><strong className="block">{item.asset === "sealed" ? "Sealed" : "Card"}</strong>{exactItemLabel(item)}{item.marketPrice != null ? <span className="block">${Number(item.marketPrice).toFixed(2)}{item.valueSharePercent != null ? ` · ${Number(item.valueSharePercent).toFixed(2)}%` : ""}</span> : null}</span><button type="button" aria-label={`Remove ${exactItemLabel(item)}`} onClick={() => remove(item)}>×</button></li>)}</ul> : <p className="mt-2 text-xs">Search and add 1–25 leaves.</p>}</aside></div>
    <footer className="border-t p-3 sm:px-6">{buildMessage ? <p role={buildStatus === "error" ? "alert" : "status"} className="mb-2 text-xs">{buildMessage}</p> : null}<div className="flex justify-end gap-2">{onCancelEdit ? <button type="button" onClick={onCancelEdit} className="min-h-11 rounded-lg border px-4">Cancel edits</button> : null}<button type="button" onClick={onClose} className="min-h-11 rounded-lg border px-4">Close</button>{onSaveAsNew ? <button type="button" disabled={!selectedItems.length} onClick={onSaveAsNew} className="min-h-11 rounded-lg border px-4">Save as new</button> : null}<button type="button" disabled={!selectedItems.length || buildStatus === "building"} onClick={onBuild} className="min-h-11 rounded-lg border border-[rgb(45,212,191)] px-4">{executionLocked ? "Requires Index Premium 🔒" : buildStatus === "building" ? "Building…" : buildLabel}</button></div></footer>
  </div></div>;
}
