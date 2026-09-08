"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { MAX_EXPLICIT_INSTRUMENTS } from "@/lib/explore/marketExplorerQuery.mjs";

export function exactItemLabel(item) {
  if (item.asset === "sealed") return [item.name, item.setName, item.productFamily || item.productType, item.variantLabel].filter(Boolean).join(" · ");
  return [item.name, item.setName, item.cardNumber ? `#${item.cardNumber}` : null, item.rarity, item.edition, item.printingType, item.specialType].filter(Boolean).join(" · ");
}

export default function MarketExplorerExactItemPicker({ asset, selectedItems = [], onChange, disabled = false }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const requestId = useRef(0);
  const selectedIds = useMemo(() => new Set(selectedItems.map((item) => item.instrumentId)), [selectedItems]);
  const atMaximum = selectedItems.length >= MAX_EXPLICIT_INSTRUMENTS;

  useEffect(() => {
    const needle = query.trim();
    requestId.current += 1;
    const token = requestId.current;
    if (needle.length < 2) { setResults([]); setStatus("idle"); setMessage(""); return undefined; }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setStatus("loading"); setMessage("");
      try {
        const response = await fetch(`/api/market/explorer/instruments/search?q=${encodeURIComponent(needle)}&asset=${asset}&limit=20`, { signal: controller.signal, credentials: "include" });
        const payload = await response.json().catch(() => null);
        if (token !== requestId.current) return;
        if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || "Unable to search exact items.");
        setResults((payload?.items || []).filter((item) => item.asset === asset));
        setStatus("ready");
      } catch (error) {
        if (error?.name === "AbortError" || token !== requestId.current) return;
        setResults([]); setStatus("error"); setMessage(error?.message || "Unable to search exact items.");
      }
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [asset, query]);

  const add = (item) => {
    if (disabled || atMaximum || selectedIds.has(item.instrumentId) || item.asset !== asset) return;
    onChange?.([...selectedItems, item]);
  };
  return <div data-market-explorer-exact-picker className="space-y-2">
    <label className="block text-[11px] font-semibold text-[var(--text-primary)]" htmlFor={`exact-item-search-${asset}`}>Search exact items</label>
    <input id={`exact-item-search-${asset}`} type="search" value={query} disabled={disabled}
      placeholder={asset === "sealed" ? "Search sealed products…" : "Search cards…"}
      onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") { setQuery(""); setResults([]); } if (event.key === "Enter" && results.length) { event.preventDefault(); add(results[0]); } }}
      className="min-h-11 w-full rounded-md border border-[var(--border-subtle)] bg-transparent px-3 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] desk:min-h-0" />
    <p data-exact-item-count className="text-[10px] text-[var(--text-secondary)]">{selectedItems.length} of {MAX_EXPLICIT_INSTRUMENTS} selected</p>
    {atMaximum ? <p role="status" className="text-[11px] text-[var(--text-secondary)]">Maximum 25 items per custom basket.</p> : null}
    {selectedItems.length ? <ul data-exact-selected-items className="space-y-1">{selectedItems.map((item) => <li key={item.instrumentId} className="flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-2 py-1.5 text-[11px]"><span className="min-w-0 flex-1 text-[var(--text-primary)]">{exactItemLabel(item)}</span><button type="button" aria-label={`Remove ${item.name}`} onClick={() => onChange?.(selectedItems.filter((entry) => entry.instrumentId !== item.instrumentId))} className="min-h-8 px-2 text-[var(--text-secondary)]">×</button></li>)}</ul> : null}
    {status === "loading" ? <p role="status" className="text-[11px] text-[var(--text-secondary)]">Searching…</p> : null}
    {message ? <p role="status" className="text-[11px] text-[var(--text-secondary)]">{message}</p> : null}
    {status === "ready" ? <ul role="listbox" aria-label="Exact item search results" className="max-h-56 space-y-1 overflow-y-auto">{results.length ? results.map((item) => { const selected = selectedIds.has(item.instrumentId); return <li key={`${item.asset}:${item.instrumentId}`}><button type="button" role="option" aria-selected={selected} disabled={disabled || selected || atMaximum} onClick={() => add(item)} className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[11px] hover:bg-white/5 disabled:opacity-45">{item.imageUrl ? <img src={item.imageUrl} alt="" loading="lazy" className="h-9 w-7 flex-none rounded object-cover" /> : null}<span className="min-w-0 flex-1"><span className="block font-medium text-[var(--text-primary)]">{item.name}</span><span className="block text-[10px] text-[var(--text-secondary)]">{exactItemLabel({ ...item, name: null })}{selected ? " · Selected" : ""}</span></span><span className="flex-none text-[10px] font-semibold text-[rgb(45,212,191)]">{selected ? "Added" : "Add"}</span></button></li>; }) : <li className="text-[11px] text-[var(--text-secondary)]">No exact items found.</li>}</ul> : null}
  </div>;
}
