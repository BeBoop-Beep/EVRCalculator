"use client";
import { useState } from "react";
import { MARKET_EXPLORER_SCREENS } from "@/lib/explore/marketExplorerScreens.mjs";

export default function MarketExplorerScreens({ canUse, activeKeys = [], onUpgrade, onSelect }) {
  const [selected, setSelected] = useState(null);
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("idle");
  const run = async (screen) => {
    if (!canUse) return onUpgrade();
    setSelected(screen.id); setStatus("loading");
    const query = new URLSearchParams({ kind: "screen", screen: screen.id, limit: String(screen.limit || 10) });
    if (screen.asset) query.set("asset", screen.asset);
    try {
      const response = await fetch(`/api/market/explorer/prepared?${query}`, { credentials: "include", cache: "no-store" });
      const payload = await response.json();
      setResults(response.ok && Array.isArray(payload.results) ? payload.results : []);
      setStatus(response.ok ? "ready" : "error");
    } catch { setResults([]); setStatus("error"); }
  };
  return <section data-market-explorer-screens className="px-3 py-3 sm:px-4" aria-labelledby="market-screens-heading">
    <h2 id="market-screens-heading" className="text-sm font-semibold text-[var(--text-primary)]">Screens</h2>
    <p className="text-[11px] text-[var(--text-secondary)]">Prepared analytical discovery. Momentum is canonical 30D index return.</p>
    <div className="mt-2 flex flex-wrap gap-2">{MARKET_EXPLORER_SCREENS.map((screen) => <button type="button" key={screen.id} data-market-screen={screen.id} onClick={() => run(screen)} className="rounded-md border border-[var(--border-subtle)] px-3 py-2 text-left text-xs"><strong className="block text-[var(--text-primary)]">{screen.label}</strong><span className="text-[10px] text-[var(--text-secondary)]">{screen.description}</span></button>)}</div>
    {selected ? <div data-market-screen-results className="mt-3"><p role="status" className="text-[11px] text-[var(--text-secondary)]">{status === "loading" ? "Loading prepared Screen…" : status === "error" ? "Screen temporarily unavailable." : `${results.length} prepared results`}</p><ol>{results.map((row) => { const active = activeKeys.includes(row.market_key); return <li key={row.market_key} className="flex items-center gap-2 border-b border-[var(--border-subtle)] py-1 text-xs"><span className="w-5 text-[var(--text-secondary)]">{row.rank}</span><button type="button" data-market-screen-result={row.market_key} aria-pressed={active} onClick={() => onSelect(row.market_key)} className={`flex-1 rounded-md border-l-2 px-2 py-2 text-left ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)] font-bold text-[rgb(45,212,191)]" : "border-transparent text-[var(--text-primary)] hover:bg-white/[.035]"}`}>{row.label}</button><span className="tabular-nums text-[var(--text-secondary)]">{Number(row.metric_value).toFixed(1)}%</span></li>; })}</ol></div> : null}
  </section>;
}
