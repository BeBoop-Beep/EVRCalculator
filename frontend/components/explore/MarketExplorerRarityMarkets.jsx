"use client";
import { useState } from "react";

const RARITY_LABELS = [
  "Special Illustration Rare",
  "Illustration Rare",
  "Ultra Rare",
  "Hyper Rare",
  "Double Rare",
  "Rare Ultra",
  "Rare Secret",
  "Rare Rainbow",
  "Rare Holo",
];

export default function MarketExplorerRarityMarkets({ directory = [], activeKeys = [], onSelect }) {
  const [open, setOpen] = useState(false);
  const byLabel = new Map(directory.map((market) => [String(market.label || "").trim().toLowerCase(), market]));
  const markets = RARITY_LABELS.map((label) => byLabel.get(label.toLowerCase())).filter(Boolean);
  if (!markets.length) return null;
  const activeMarket = markets.find((market) => activeKeys.includes(market.market_key));
  return (
    <section data-market-explorer-rarity-markets className="py-2" aria-labelledby="rarity-markets-heading">
      <h3 id="rarity-markets-heading" className="text-xs font-semibold text-[var(--text-primary)]">Rarity Markets</h3>
      <button type="button" data-rarity-market-trigger aria-expanded={open} aria-controls="rarity-market-options" onClick={() => setOpen((value) => !value)} className={`mt-2 flex min-h-10 w-full items-center justify-between rounded-md border px-3 text-left text-xs ${activeMarket ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)] font-semibold text-[rgb(45,212,191)]" : "border-[var(--border-subtle)] text-[var(--text-primary)]"}`}>
        <span>{activeMarket?.label || "Choose a rarity market"}</span><span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      <div id="rarity-market-options" hidden={!open} className="mt-1 space-y-1" role="listbox" aria-label="Rarity Markets">
        {markets.map((market) => {
          const active = activeKeys.includes(market.market_key);
          return <button type="button" role="option" key={market.market_key} data-rarity-market={market.market_key} aria-selected={active} onClick={() => { onSelect(market.market_key); setOpen(false); }} className={`w-full rounded-md border-l-2 px-2 py-2 text-left text-xs transition-colors hover:bg-white/[.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,.65)] ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)] font-bold text-[rgb(45,212,191)]" : "border-transparent text-[var(--text-primary)]"}`}>{market.label}</button>;
        })}
      </div>
    </section>
  );
}
