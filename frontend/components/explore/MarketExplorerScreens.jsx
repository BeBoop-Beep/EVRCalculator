"use client";
import { useRef, useState } from "react";
import { MARKET_EXPLORER_SCREENS } from "@/lib/explore/marketExplorerScreens.mjs";

export default function MarketExplorerScreens({ canUse, activeKeys = [], onUpgrade, onSelect, onCompare }) {
  const [selected, setSelected] = useState(null);
  const [screenStates, setScreenStates] = useState({});
  const cache = useRef(new Map());

  const run = async (screen, { refresh = false } = {}) => {
    if (!canUse) { onUpgrade?.(); return; }
    setSelected(screen.id);
    if (!refresh && cache.current.has(screen.id)) {
      setScreenStates((current) => ({ ...current, [screen.id]: { status: "ready", results: cache.current.get(screen.id) } }));
      return;
    }
    setScreenStates((current) => ({ ...current, [screen.id]: { status: "loading", results: current[screen.id]?.results || [] } }));
    const query = new URLSearchParams({ kind: "screen", screen: screen.id, limit: String(screen.limit || 10) });
    if (screen.asset) query.set("asset", screen.asset);
    try {
      const response = await fetch(`/api/market/explorer/prepared?${query}`, { credentials: "include", cache: "no-store" });
      const payload = await response.json();
      const results = response.ok && Array.isArray(payload.results) ? payload.results : [];
      if (response.ok) cache.current.set(screen.id, results);
      if (!response.ok && process.env.NODE_ENV !== "production") console.error("Market Explorer Screen request failed", { httpStatus: response.status, errorCode: typeof payload?.code === "string" ? payload.code : "PREPARED_SCREEN_REQUEST_FAILED" });
      setScreenStates((current) => ({ ...current, [screen.id]: { status: response.ok ? "ready" : "error", results } }));
    } catch (error) {
      if (process.env.NODE_ENV !== "production") console.error("Market Explorer Screen transport failure", { errorCode: "PREPARED_SCREEN_TRANSPORT_FAILED", errorName: error?.name || "Error" });
      setScreenStates((current) => ({ ...current, [screen.id]: { status: "error", results: [] } }));
    }
  };

  const selectedScreen = MARKET_EXPLORER_SCREENS.find((screen) => screen.id === selected);
  const selectedState = selected ? (screenStates[selected] || { status: "idle", results: [] }) : null;
  return <section data-market-explorer-screens className="px-3 py-3 sm:px-4" aria-labelledby="market-screens-heading">
    <h2 id="market-screens-heading" className="text-sm font-semibold text-[var(--text-primary)]">Screens</h2>
    <p className="text-[11px] text-[var(--text-secondary)]">Prepared analytical discovery. Momentum is canonical 30D index return.</p>
    <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">{MARKET_EXPLORER_SCREENS.map((screen) => { const active = selected === screen.id; return <button type="button" key={screen.id} data-market-screen={screen.id} data-market-screen-locked={!canUse ? "true" : "false"} aria-disabled={!canUse} aria-pressed={active} onClick={() => run(screen)} className={`rounded-md border px-3 py-2 text-left text-xs transition-colors ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.16)] text-[rgb(45,212,191)] shadow-[inset_0_0_0_1px_rgba(45,212,191,.18)]" : "border-[var(--border-subtle)]"} ${!canUse ? "opacity-60" : "hover:bg-white/[.035]"}`}><strong className="block">{screen.label}{!canUse ? " · Locked" : ""}</strong><span className={`text-[10px] ${active ? "text-[rgb(153,246,228)]" : "text-[var(--text-secondary)]"}`}>{screen.description}</span></button>; })}</div>
    {selectedState ? <div data-market-screen-results data-market-screen-results-for={selected} className="mt-3 rounded-md border border-[var(--border-subtle)] px-2 py-2"><div className="flex items-center justify-between gap-2"><p role="status" className="text-[11px] text-[var(--text-secondary)]">{selectedState.status === "loading" ? "Loading prepared Screen…" : selectedState.status === "error" ? "Screen temporarily unavailable." : `${selectedState.results.length} prepared results`}</p>{selectedState.status === "error" ? <button type="button" data-market-screen-retry onClick={() => run(selectedScreen, { refresh: true })} className="rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold text-[var(--text-primary)]">Retry</button> : null}</div><ol>{selectedState.results.map((row) => { const active = activeKeys.includes(row.market_key); return <li key={row.market_key} className="flex items-center gap-2 border-b border-[var(--border-subtle)] py-1 text-xs"><span className="w-5 text-[var(--text-secondary)]">{row.rank}</span><button type="button" data-market-screen-result={row.market_key} aria-pressed={active} onClick={() => onSelect(row.market_key)} className={`min-w-0 flex-1 rounded-md border-l-2 px-2 py-2 text-left ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)] font-bold text-[rgb(45,212,191)]" : "border-transparent text-[var(--text-primary)] hover:bg-white/[.035]"}`}>{row.label}{active ? <span aria-label="Active market"> ✓</span> : null}</button><span className="tabular-nums text-[var(--text-secondary)]">{Number(row.metric_value).toFixed(1)}%</span><button type="button" data-market-screen-compare={row.market_key} onClick={() => onCompare?.(row.market_key)} className={`rounded border px-2 py-1 text-[10px] font-semibold ${active ? "border-red-300/30 text-red-200" : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[rgba(45,212,191,.45)] hover:text-[rgb(45,212,191)]"}`}>{active ? "Remove" : "+ Compare"}</button></li>; })}</ol></div> : null}
  </section>;
}
