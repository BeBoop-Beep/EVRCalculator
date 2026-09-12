"use client";

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
  const byLabel = new Map(directory.map((market) => [String(market.label || "").trim().toLowerCase(), market]));
  const markets = RARITY_LABELS.map((label) => byLabel.get(label.toLowerCase())).filter(Boolean);
  if (!markets.length) return null;
  return (
    <section data-market-explorer-rarity-markets className="px-3 py-3" aria-labelledby="rarity-markets-heading">
      <h3 id="rarity-markets-heading" className="text-sm font-semibold text-[var(--text-primary)]">Rarity Markets</h3>
      <p className="text-[11px] text-[var(--text-secondary)]">Open a published rarity market directly.</p>
      <div className="mt-2 space-y-1">
        {markets.map((market) => {
          const active = activeKeys.includes(market.market_key);
          return <button type="button" key={market.market_key} data-rarity-market={market.market_key} aria-pressed={active} onClick={() => onSelect(market.market_key)} className={`w-full rounded-md border-l-2 px-2 py-2 text-left text-xs transition-all hover:-translate-y-px hover:bg-white/[.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,.65)] ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)] font-bold text-[rgb(45,212,191)] shadow-[inset_0_0_0_1px_rgba(45,212,191,.16)]" : "border-transparent text-[var(--text-primary)]"}`}>{market.label}</button>;
        })}
      </div>
    </section>
  );
}
