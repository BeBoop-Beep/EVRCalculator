"use client";
import { useState } from "react";

const MODES = [["value", "Top 10 by Value"], ["risers", "Biggest Risers"], ["fallers", "Biggest Fallers"]];
export default function MarketExplorerContextRanking({ market, timeframe, canUse, onUpgrade }) {
  const [result, setResult] = useState(null);
  if (market?.marketType !== "set") return null;
  const run = async (ranking) => {
    if (!canUse) return onUpgrade();
    if (ranking !== "value" && !["7D", "30D", "90D"].includes(timeframe)) {
      setResult({ available: false, reason: `${timeframe} is not a supported mover window.` }); return;
    }
    const query = new URLSearchParams({ kind: "ranking", set_id: market.setId, ranking, timeframe, limit: "10", as_of: market.comparisonAsOf });
    const response = await fetch(`/api/market/explorer/prepared?${query}`, { credentials: "include", cache: "no-store" });
    setResult(await response.json());
  };
  return <section data-market-context-ranking className="border-t border-[var(--border-subtle)] px-3 py-3 sm:px-4">
    <h3 className="text-xs font-semibold text-[var(--text-primary)]">Analyze {market.label}</h3>
    <p className="text-[10px] text-[var(--text-secondary)]">All Cards remains in Constituents. Rankings are read-only analysis and never change market membership.</p>
    <div className="mt-2 flex flex-wrap gap-2">{MODES.map(([id, label]) => <button type="button" key={id} onClick={() => run(id)} className="rounded border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-secondary)]">{label}</button>)}</div>
    {result ? result.available ? <ol className="mt-2">{(result.items || []).map((item) => <li key={item.cardVariantId} className="flex gap-2 border-b border-[var(--border-subtle)] py-1 text-[11px]"><span>{item.rank}</span><span className="flex-1 text-[var(--text-primary)]">{item.name || item.cardVariantId}</span><span>{item.changePercent == null ? `$${Number(item.marketPrice).toFixed(2)}` : `${Number(item.changePercent).toFixed(1)}%`}</span></li>)}</ol> : <p className="mt-2 text-[11px] text-[var(--text-secondary)]">Unavailable: {result.reason}</p> : null}
  </section>;
}
