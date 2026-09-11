"use client";
import { useMemo, useState } from "react";
import { groupPreparedDirectory } from "@/lib/explore/marketExplorerPrepared.mjs";

function MarketRow({ market, active, canCompare, onSelect, onCompare }) {
  return <li className="flex items-center gap-2 border-b border-[var(--border-subtle)] py-2 last:border-0">
    <button type="button" data-prepared-market={market.market_key} aria-pressed={active} onClick={() => onSelect(market.market_key)} className="min-w-0 flex-1 text-left">
      <strong className="block truncate text-xs text-[var(--text-primary)]">{market.label}</strong>
      <span className="text-[10px] text-[var(--text-secondary)]">{market.current_value == null ? "Value unavailable" : `$${Number(market.current_value).toLocaleString()}`} · as of {market.source_as_of || "unavailable"}{market.history_available ? "" : " · Browse only"}{market.source_status === "failed" ? " · latest refresh failed; using previous good series" : ""}</span>
    </button>
    <button type="button" data-compare-market={market.market_key} onClick={() => onCompare(market.market_key)} className="rounded border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold text-[var(--text-secondary)]">+ Compare{canCompare ? "" : " with Index+"}</button>
  </li>;
}

export default function MarketExplorerBrowse({ directory = [], activeKeys = [], canCompare, onSelect, onCompare }) {
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState("sets");
  const grouped = useMemo(() => groupPreparedDirectory(directory, search), [directory, search]);
  const rows = tab === "eras" ? grouped.eras : tab === "quick" ? grouped.quick : null;
  return <section data-market-explorer-browse aria-labelledby="browse-markets-heading" className="min-w-0 border-b border-[var(--border-subtle)]">
    <div className="px-3 py-3"><h2 id="browse-markets-heading" className="text-sm font-semibold text-[var(--text-primary)]">Browse Markets</h2>
      <p className="text-[11px] text-[var(--text-secondary)]">Explore every published Set, Era, and curated Quick Market.</p></div>
    <div role="tablist" aria-label="Prepared market type" className="flex gap-1 px-3">
      {[['sets','Sets'],['eras','Eras'],['quick','Quick Markets']].map(([id,label]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} className={`rounded-t px-3 py-2 text-xs ${tab === id ? "bg-[rgba(45,212,191,.12)] text-[rgb(45,212,191)]" : "text-[var(--text-secondary)]"}`}>{label}</button>)}
    </div>
    <div className="px-3 pb-3"><input data-market-browser-search value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search markets…" aria-label="Search prepared markets" className="mb-2 w-full rounded-md border border-[var(--border-subtle)] bg-transparent px-3 py-2 text-xs text-[var(--text-primary)]" />
      <div className="max-h-[25rem] overflow-y-auto">
        {rows ? <ul>{rows.map((market) => <MarketRow key={market.market_key} market={market} active={activeKeys.includes(market.market_key)} canCompare={canCompare} onSelect={onSelect} onCompare={onCompare} />)}</ul>
          : grouped.sets.map((group) => <section key={group.era?.market_key || group.rows[0]?.parent_era_id} data-market-era-group={group.era?.market_key}><h3 className="sticky top-0 bg-[var(--surface-page)] py-1 text-[10px] font-bold uppercase tracking-wide text-[var(--text-secondary)]">{group.era?.label || "Unknown Era"}</h3><ul>{group.rows.map((market) => <MarketRow key={market.market_key} market={market} active={activeKeys.includes(market.market_key)} canCompare={canCompare} onSelect={onSelect} onCompare={onCompare} />)}</ul></section>)}
      </div>
    </div>
  </section>;
}
