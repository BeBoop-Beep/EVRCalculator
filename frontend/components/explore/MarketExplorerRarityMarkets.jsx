"use client";
import { useMemo, useState } from "react";

function isRarityMarket(market) {
  return market?.market_type === "prepared_rarity" || String(market?.market_key || "").startsWith("rarity:");
}

export default function MarketExplorerRarityMarkets({
  directory = [],
  activeKeys = [],
  canCompare = false,
  onSelect,
  onCompare,
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  const markets = useMemo(
    () => directory
      .filter(isRarityMarket)
      .sort((a, b) => String(a.label || "").localeCompare(String(b.label || ""))),
    [directory],
  );
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return needle
      ? markets.filter((market) => String(market.label || "").toLowerCase().includes(needle))
      : markets;
  }, [markets, search]);

  if (!markets.length) return null;

  const activeCount = markets.filter((market) => activeKeys.includes(market.market_key)).length;

  const toggle = (market) => {
    const active = activeKeys.includes(market.market_key);
    if (active) {
      onSelect?.(market.market_key);
      return;
    }
    if (canCompare) onCompare?.(market.market_key);
    else onSelect?.(market.market_key);
  };

  return (
    <section data-market-explorer-rarity-markets className="py-2" aria-labelledby="rarity-markets-heading">
      <div className="flex items-center justify-between gap-2">
        <h3 id="rarity-markets-heading" className="text-xs font-semibold text-[var(--text-primary)]">Rarity Markets</h3>
        <span className="text-[10px] tabular-nums text-[var(--text-secondary)]">{markets.length} available</span>
      </div>

      <button
        type="button"
        data-rarity-market-trigger
        aria-expanded={open}
        aria-controls="rarity-market-options"
        onClick={() => setOpen((value) => !value)}
        className={`mt-2 flex min-h-10 w-full items-center justify-between rounded-md border px-3 text-left text-xs ${activeCount ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.10)] font-semibold text-[rgb(45,212,191)]" : "border-[var(--border-subtle)] text-[var(--text-primary)]"}`}
      >
        <span>{activeCount ? `${activeCount} rarit${activeCount === 1 ? "y" : "ies"} active` : "Browse all rarity markets"}</span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>

      <div id="rarity-market-options" hidden={!open} className="mt-1 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]">
        <label className="sr-only" htmlFor="rarity-market-search">Search rarity markets</label>
        <input
          id="rarity-market-search"
          data-rarity-market-search
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search rarities…"
          className="min-h-10 w-full border-b border-[var(--border-subtle)] bg-transparent px-3 text-xs text-[var(--text-primary)] outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[rgb(45,212,191)]"
        />

        <div className="max-h-72 overflow-y-auto p-1" role="listbox" aria-label="Rarity Markets">
          {!visible.length ? (
            <p className="px-2 py-3 text-xs text-[var(--text-secondary)]">No matching rarity.</p>
          ) : visible.map((market) => {
            const active = activeKeys.includes(market.market_key);
            return (
              <div
                key={market.market_key}
                className={`flex items-center gap-1 rounded-md border-l-2 ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)]" : "border-transparent hover:bg-white/[.035]"}`}
              >
                <button
                  type="button"
                  role="option"
                  data-rarity-market={market.market_key}
                  aria-selected={active}
                  onClick={() => toggle(market)}
                  className={`min-w-0 flex-1 px-2 py-2 text-left text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,.65)] ${active ? "font-bold text-[rgb(45,212,191)]" : "text-[var(--text-primary)]"}`}
                >
                  {market.label}
                  {active ? <span aria-label="Active market"> ✓</span> : null}
                </button>
                <button
                  type="button"
                  data-rarity-market-compare={market.market_key}
                  onClick={() => toggle(market)}
                  className={`mr-1 rounded-md border px-2 py-1 text-[10px] font-semibold ${active ? "border-red-300/30 text-red-200 hover:bg-red-400/10" : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}
                >
                  {active ? "Remove" : canCompare ? "+ Compare" : "Select"}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
