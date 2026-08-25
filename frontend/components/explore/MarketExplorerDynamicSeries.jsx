"use client";

import { formatBasketValue, formatIndexValue } from "@/lib/explore/marketOverviewPresentation.mjs";

export default function MarketExplorerDynamicSeries({ series = [], onRemove }) {
  if (!series.length) return null;
  return (
    <section data-market-query-series className="space-y-3" aria-label="Custom comparison markets">
      <ul className="flex flex-wrap gap-2">
        {series.map((entry) => (
          <li key={entry.key} data-market-query-chip={entry.key} className="flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-3 py-2 text-xs">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-[3px]" style={{ backgroundColor: entry.color }} />
            <span className="font-semibold text-[var(--text-primary)]">{entry.label}</span>
            <span className="tabular-nums text-[var(--text-secondary)]">Index {formatIndexValue(entry.indexValue)}</span>
            <button type="button" aria-label={`Remove ${entry.label}`} onClick={() => onRemove?.(entry.key)} className="ml-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)]">×</button>
          </li>
        ))}
      </ul>
      {series.filter((entry) => entry.spec?.mode === "chase").map((entry) => {
        const roster = entry.currentConstituents || [];
        const reconciliation = entry.reconciliation || {};
        return (
          <article key={entry.key} data-market-current-constituents={entry.key} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/30">
            <div className="flex flex-wrap items-baseline gap-2 px-3 py-3 sm:px-4">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">Current Constituents</h3>
              <span className="text-[11px] text-[var(--text-secondary)]">{entry.label} · {reconciliation.actualConstituentCount ?? roster.length} eligible cards shown{reconciliation.belowRequestedTopN ? ` (requested Top ${reconciliation.requestedTopN})` : ""}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-left text-xs">
                <thead className="border-y border-[var(--border-subtle)] text-[10px] uppercase tracking-[0.07em] text-[var(--text-secondary)]"><tr><th className="px-3 py-2">Rank</th><th className="px-3 py-2">Card</th><th className="px-3 py-2">Set</th><th className="px-3 py-2">Rarity</th><th className="px-3 py-2 text-right">Price</th></tr></thead>
                <tbody>{roster.map((card) => <tr key={card.canonicalCardId} data-market-constituent={card.canonicalCardId} className="border-b border-[var(--border-subtle)] last:border-0"><td className="px-3 py-2 tabular-nums">{card.rank}</td><td className="px-3 py-2"><span className="flex items-center gap-2">{card.imageUrl ? <img src={card.imageUrl} alt="" loading="lazy" className="h-10 w-7 rounded object-cover" /> : null}<span className="font-medium text-[var(--text-primary)]">{card.cardName}</span></span></td><td className="px-3 py-2">{card.setName}</td><td className="px-3 py-2">{card.rarity}</td><td className="px-3 py-2 text-right font-semibold tabular-nums">{formatBasketValue(card.marketPrice)}</td></tr>)}</tbody>
              </table>
            </div>
          </article>
        );
      })}
    </section>
  );
}
