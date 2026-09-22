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

const SCOPES = [
  { value: "all", label: "All" },
  { value: "cards", label: "Cards" },
  { value: "sealed", label: "Products" },
  { value: "filters", label: "Custom Filters" },
];

export default function MarketExplorerExactItemPicker({ selectedItems = [], onChange, open = true, initialScope = "all", customFilters = null, onClose, onCancelEdit, onBuild, onSaveAsNew, executionLocked = false, buildLabel = "Build Market", buildStatus = "idle", buildMessage = "" }) {
  const [scope, setScope] = useState(() => SCOPES.some((entry) => entry.value === initialScope) ? initialScope : "all");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const requestId = useRef(0);
  const searchRef = useRef(null);
  const selectedIds = useMemo(() => new Set(selectedItems.map(identity)), [selectedItems]);
  const atMaximum = selectedItems.length >= MAX_EXPLICIT_INSTRUMENTS;
  useEffect(() => {
    if (!open) return;
    const next = SCOPES.some((entry) => entry.value === initialScope) ? initialScope : "all";
    setScope(next);
    if (next !== "filters") requestAnimationFrame(() => searchRef.current?.focus());
  }, [open, initialScope]);
  useEffect(() => {
    const needle = query.trim(); const token = ++requestId.current;
    if (scope === "filters") { setResults([]); setStatus("idle"); setMessage(""); return undefined; }
    if (needle.length < 2) { setResults([]); setStatus("idle"); setMessage(""); return undefined; }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setStatus("loading"); setMessage("");
      try {
        const response = await fetch(`/api/market/explorer/instruments/search?q=${encodeURIComponent(needle)}&asset=${scope}&limit=20`, { signal: controller.signal, credentials: "include" });
        const payload = await response.json().catch(() => null);
        if (token !== requestId.current) return;
        if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || "Unable to search Cards and Products.");
        setResults(payload?.items || []); setStatus("ready");
      } catch (error) { if (error?.name !== "AbortError" && token === requestId.current) { setResults([]); setStatus("error"); setMessage(error?.message || "Unable to search Cards and Products."); } }
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [scope, query]);
  if (!open) return null;
  const add = (item) => { if (!atMaximum && !selectedIds.has(identity(item))) onChange?.([...selectedItems, item]); };
  const remove = (item) => onChange?.(selectedItems.filter((row) => identity(row) !== identity(item)));
  return <div data-market-explorer-exact-workspace className="flex min-h-0 flex-1 flex-col overflow-hidden">
    <header className="flex flex-none items-start gap-4 border-b border-[var(--border-subtle)] px-4 py-3 sm:px-6 sm:py-4"><div className="min-w-0 flex-1"><h2 id="build-markets-zone-heading" className="text-lg font-semibold text-[var(--text-primary)] sm:text-xl">Build Your Market</h2><p className="mt-0.5 text-xs text-[var(--text-secondary)] sm:text-sm">Choose the exact Cards and Products you want to track together.</p><p data-exact-item-count className="mt-1 text-xs font-semibold text-[var(--text-primary)]">{selectedItems.length} / 25 selected</p></div><button type="button" aria-label="Close Build Your Market" onClick={onClose} className="min-h-11 min-w-11 rounded-full border border-white/20 bg-white/[.04] text-xl font-semibold text-[var(--text-primary)] transition-colors hover:border-[rgb(45,212,191)] hover:bg-[rgba(45,212,191,.10)] hover:text-[rgb(94,234,212)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(45,212,191)]">×</button></header>
    <div className="flex-none border-b border-[var(--border-subtle)] px-4 py-3 sm:px-6">
      <div role="tablist" aria-label="Build market method" className="flex flex-wrap gap-2">
        {SCOPES.map(({ value, label }) => {
          const disabled = value === "filters" && !customFilters;
          return <button key={value} type="button" role="tab" aria-selected={scope === value} disabled={disabled} onClick={() => setScope(value)} className={`min-h-9 rounded-md border px-4 text-xs font-semibold transition-colors ${scope === value ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.14)] text-[rgb(45,212,191)]" : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"} disabled:opacity-40`}>{label}</button>;
        })}
      </div>
      {scope !== "filters" ? (
        <>
          <label className="sr-only" htmlFor="exact-search">Search Cards and Products</label>
          <input ref={searchRef} data-market-exact-search id="exact-search" type="search" value={query} placeholder="Search Cards and Products..." onChange={(event) => setQuery(event.target.value)} className="mt-2 min-h-12 w-full rounded-lg border border-[var(--border-subtle)] bg-transparent px-4 text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(45,212,191)]" />
        </>
      ) : (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">Build a market from Era, Set, Rarity, Pokémon, price, and release-age filters.</p>
      )}
    </div>
    {scope === "filters" ? (
      <div data-market-explorer-custom-filter-workspace className="min-h-0 flex-1 overflow-y-auto px-4 py-3 sm:px-6 sm:py-4">
        {customFilters}
      </div>
    ) : (
      <>
    <div className="grid min-h-0 flex-1 grid-rows-[minmax(12rem,1fr)_minmax(8rem,35vh)] overflow-hidden desk:grid-cols-[minmax(0,1.85fr)_minmax(18rem,1fr)] desk:grid-rows-1"><section aria-label="Search results" className="min-w-0 overflow-y-auto p-4 sm:p-6"><h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Search Results</h3>{atMaximum ? <p role="status" className="mb-3 rounded-md border border-[rgb(45,212,191)] bg-[rgba(45,212,191,.10)] px-3 py-2 text-xs text-[rgb(153,246,228)]">25 / 25 selected — remove an item to add another.</p> : null}{status === "loading" ? <p role="status" className="text-sm text-[var(--text-secondary)]">Searching…</p> : null}{message ? <p role="alert" className="text-sm text-red-200">{message}</p> : null}{status === "idle" ? <p className="text-sm text-[var(--text-secondary)]">Search for a Card or Product to begin.</p> : null}{status === "ready" ? <ul role="listbox" className="space-y-2">{results.map((item) => { const selected = selectedIds.has(identity(item)); const disabled = atMaximum && !selected; return <li key={identity(item)}><button type="button" role="option" aria-selected={selected} aria-disabled={disabled} onClick={() => selected || disabled ? undefined : add(item)} className={`flex min-h-28 w-full items-center gap-4 rounded-xl border p-3 text-left transition-colors ${selected ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.14)] text-[rgb(153,246,228)]" : "border-[var(--border-subtle)] hover:bg-white/[.035]"} ${disabled ? "cursor-not-allowed opacity-50" : ""}`}><Artwork item={item} /><span className="min-w-0 flex-1"><strong className="block text-[var(--text-primary)]">{item.name}</strong><span className="text-xs text-[var(--text-secondary)]">{item.asset === "sealed" ? "Product" : "Card"} · {exactItemLabel({ ...item, name: null })}</span></span><b className={`rounded-full border px-3 py-1 text-xs ${selected ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)] text-[rgb(94,234,212)]" : disabled ? "border-[var(--border-subtle)] text-[var(--text-secondary)]" : "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.16)] text-[rgb(94,234,212)]"}`}>{selected ? "Selected ✓" : disabled ? "Limit reached" : "Add"}</b></button></li>; })}</ul> : null}</section>
      <aside className="min-w-0 overflow-y-auto border-t border-[var(--border-subtle)] p-4 desk:border-l desk:border-t-0 sm:p-6"><h3 className="font-semibold text-[var(--text-primary)]">Your Market</h3>{selectedItems.length ? <ul data-exact-selected-items className="mt-2 space-y-2">{selectedItems.map((item) => <li key={identity(item)} className="flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] p-2 text-xs"><Artwork item={item} compact /><span className="min-w-0 flex-1"><strong className="block text-[var(--text-primary)]">{item.asset === "sealed" ? "Product" : "Card"}</strong><span className="text-[var(--text-secondary)]">{exactItemLabel(item)}</span>{item.marketPrice != null ? <span className="block text-[var(--text-secondary)]">${Number(item.marketPrice).toFixed(2)}{item.valueSharePercent != null ? ` · ${Number(item.valueSharePercent).toFixed(2)}%` : ""}</span> : null}</span><button type="button" aria-label={`Remove ${exactItemLabel(item)}`} onClick={() => remove(item)} className="min-h-9 min-w-9 rounded-full border border-[var(--border-subtle)]">×</button></li>)}</ul> : <p className="mt-2 text-xs text-[var(--text-secondary)]">Search and add 1–25 Cards or Products.</p>}</aside></div>
    <footer className="flex-none border-t border-[var(--border-subtle)] bg-[var(--surface-page)] p-3 sm:px-6 sm:py-4">{buildMessage ? <p role={buildStatus === "error" ? "alert" : "status"} className="mb-2 text-xs text-[var(--text-secondary)]">{buildMessage}</p> : null}<div className="flex flex-wrap items-center justify-end gap-2"><span className="mr-auto text-xs font-semibold text-[var(--text-secondary)]">{selectedItems.length} / 25 selected</span>{onCancelEdit ? <button type="button" onClick={onCancelEdit} className="min-h-11 rounded-lg border border-[var(--border-subtle)] px-4 text-sm font-semibold">Cancel Edits</button> : null}{onSaveAsNew ? <button type="button" disabled={!selectedItems.length || buildStatus === "building"} onClick={onSaveAsNew} className="min-h-11 rounded-lg border border-[var(--border-subtle)] px-4 text-sm font-semibold disabled:opacity-50">Save as New</button> : null}<button type="button" disabled={!selectedItems.length || buildStatus === "building"} onClick={onBuild} className="min-h-12 rounded-lg border border-[rgb(45,212,191)] bg-[rgba(45,212,191,.18)] px-6 text-sm font-bold text-[rgb(45,212,191)] disabled:cursor-not-allowed disabled:opacity-50">{executionLocked ? "Requires Index Premium 🔒" : buildStatus === "building" ? "Building..." : buildLabel}</button></div></footer>
      </>
    )}
  </div>;
}
