"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import TableSearchInput from "@/components/ui/TableSearchInput";
import { buildPokemonCardDetailHref } from "@/lib/pokemon/pokemonCardDetailClient";
import styles from "./explore.module.css";

const SORTS = [
  ["chase_efficiency", "Chase Efficiency"], ["price", "Market Price"],
  ["pull_probability", "Pull Odds"], ["chase_spend_50", "50% Chase Spend"],
  ["cost_multiple_50", "Cost Multiple"], ["name", "Alphabetical"],
];
const RARITIES = ["Special Illustration Rare", "Illustration Rare", "Hyper Rare", "Mega Hyper Rare", "Ultra Rare", "Double Rare"];
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const decimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });
const value = (input) => Number.isFinite(Number(input)) ? Number(input) : null;

function LockedCards() {
  return (
    <section data-card-chase-efficiency-locked className={`${styles.surface} set-glass-surface overflow-hidden p-5 sm:p-7`}>
      <div className="mx-auto max-w-2xl py-7 text-center">
        <span className="inline-flex rounded-full border border-[rgba(45,212,191,.35)] bg-[rgba(45,212,191,.08)] px-3 py-1 text-[10px] font-bold uppercase tracking-[.16em] text-[var(--accent)]">Index Premium</span>
        <h2 className="mt-4 text-xl font-semibold text-[var(--text-primary)]">Rank every chase by opening efficiency</h2>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[var(--text-secondary)]">Compare exact card printings using current Near Mint value, modeled pull odds, and the cheapest verified pack-equivalent route.</p>
        <div aria-hidden="true" className="mx-auto mt-6 grid max-w-lg grid-cols-3 gap-2 opacity-55 blur-[2px]">
          {["#1 · Chase card", "$700 market", "1 in 400 packs", "#2 · Chase card", "$965 market", "$1,400 to 50%", "#3 · Chase card", "2.7× vs buy", "CE 0.0864"].map((item) => <span key={item} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2 py-3 text-[10px] text-[var(--text-secondary)]">{item}</span>)}
        </div>
        <p className="mt-5 text-xs font-medium text-[var(--text-secondary)]">Upgrade to Index Premium to unlock rankings, filters, and exact-card chase routes.</p>
      </div>
    </section>
  );
}

function cardHref(row, sets) {
  const set = sets.get(String(row?.setId || ""));
  return buildPokemonCardDetailHref({ setCanonicalKey: set?.canonicalKey || set?.name || row?.setId,
    canonicalCardId: row?.canonicalCardId, cardVariantId: row?.cardVariantId });
}
function odds(row) { const p = value(row?.exactPullProbability); return p && p > 0 ? `1 in ${decimal.format(1 / p)}` : "—"; }
function spend50(row) { return value(row?.chaseSpend50 ?? row?.milestones?.["50"]?.spend); }
function multiple50(row) { const direct = value(row?.costMultiple50); const spend = spend50(row), price = value(row?.currentNearMintMarketPrice); return direct ?? (spend !== null && price ? spend / price : null); }

export default function CardChaseEfficiencyRankings({ entitled, targets = [] }) {
  const [filters, setFilters] = useState({ search: "", era: "", set: "", rarity: "", min_price: "", max_price: "", sort: "chase_efficiency", direction: "desc" });
  const [page, setPage] = useState(1); const [result, setResult] = useState({ status: "idle", payload: null });
  const sets = useMemo(() => new Map(targets.map((target) => [String(target?.set_id || target?.target_id || target?.id), {
    name: target?.name, canonicalKey: target?.canonical_key, era: target?.era,
  }])), [targets]);
  const eras = useMemo(() => [...new Set(targets.map((target) => String(target?.era || "").trim()).filter(Boolean))].sort(), [targets]);
  const setOptions = useMemo(() => [...sets.entries()].map(([id, item]) => ({ id, ...item })).filter((item) => !filters.era || item.era === filters.era).sort((a,b) => String(a.name).localeCompare(String(b.name))), [sets, filters.era]);
  const { search, era, set: selectedSet, rarity, min_price: minPrice, max_price: maxPrice, sort, direction } = filters;
  useEffect(() => {
    if (!entitled) return undefined;
    const controller = new AbortController(); const timer = setTimeout(() => {
      const params = new URLSearchParams({ page: String(page), page_size: "50", sort, direction });
      for (const [key, input] of Object.entries({ search, era, set: selectedSet, rarity, min_price: minPrice, max_price: maxPrice })) if (String(input || "").trim()) params.set(key, input);
      setResult((current) => ({ ...current, status: "loading" }));
      fetch(`/api/explore/card-chase-efficiency?${params}`, { cache: "no-store", signal: controller.signal })
        .then(async (response) => { const payload = await response.json(); if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || "Unable to load rankings"); return payload; })
        .then((payload) => setResult({ status: "ready", payload })).catch((error) => { if (error.name !== "AbortError") setResult({ status: "error", error: error.message, payload: null }); });
    }, search ? 250 : 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [entitled, page, search, era, selectedSet, rarity, minPrice, maxPrice, sort, direction]);
  if (!entitled) return <LockedCards />;
  const update = (key, next) => { setFilters((current) => ({ ...current, [key]: next, ...(key === "era" ? { set: "" } : {}) })); setPage(1); };
  const rows = result.payload?.rows || [];
  return (
    <section data-card-chase-efficiency-rankings className={`${styles.surface} set-glass-surface overflow-hidden`}>
      <header className="border-b border-[var(--border-subtle)] px-4 py-4 sm:px-5"><h2 className="text-base font-semibold text-[var(--text-primary)]">Best Cards to Chase</h2><p className="mt-1 text-xs text-[var(--text-secondary)]">Official ranks use exact printings and the best verified pack-equivalent cost.</p></header>
      <div className="grid gap-2 border-b border-[var(--border-subtle)] p-3 sm:grid-cols-2 desk:grid-cols-4">
        <TableSearchInput value={filters.search} onChange={(e) => update("search", e.target.value)} placeholder="Search cards" ariaLabel="Search Chase Efficiency cards" containerClassName="desk:max-w-none" />
        <select aria-label="Filter by era" value={filters.era} onChange={(e) => update("era", e.target.value)} className={`${styles.setMarketControl} min-h-11 px-2 text-xs`}><option value="">All eras</option>{eras.map((era) => <option key={era}>{era}</option>)}</select>
        <select aria-label="Filter by set" value={filters.set} onChange={(e) => update("set", e.target.value)} className={`${styles.setMarketControl} min-h-11 px-2 text-xs`}><option value="">All sets</option>{setOptions.map((set) => <option key={set.id} value={set.id}>{set.name}</option>)}</select>
        <select aria-label="Filter by rarity" value={filters.rarity} onChange={(e) => update("rarity", e.target.value)} className={`${styles.setMarketControl} min-h-11 px-2 text-xs`}><option value="">All rarities</option>{RARITIES.map((rarity) => <option key={rarity}>{rarity}</option>)}</select>
        <input aria-label="Minimum market price" type="number" min="0" placeholder="Min price" value={filters.min_price} onChange={(e) => update("min_price", e.target.value)} className={`${styles.setMarketControl} min-h-11 px-2 text-xs`} />
        <input aria-label="Maximum market price" type="number" min="0" placeholder="Max price" value={filters.max_price} onChange={(e) => update("max_price", e.target.value)} className={`${styles.setMarketControl} min-h-11 px-2 text-xs`} />
        <select aria-label="Sort cards" value={filters.sort} onChange={(e) => update("sort", e.target.value)} className={`${styles.setMarketControl} min-h-11 px-2 text-xs`}>{SORTS.map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select>
        <select aria-label="Sort direction" value={filters.direction} onChange={(e) => update("direction", e.target.value)} className={`${styles.setMarketControl} min-h-11 px-2 text-xs`}><option value="desc">Highest first</option><option value="asc">Lowest first</option></select>
      </div>
      {result.status === "error" ? <p className="p-6 text-sm text-rose-300">{result.error}</p> : null}
      <div className="hidden overflow-x-auto desk:block"><table className="w-full text-left text-xs"><thead className="text-[10px] uppercase tracking-wider text-[var(--text-secondary)]"><tr>{["Rank","Card / Set","Rarity","Market Price","Pull Odds","50% Chase Cost","Cost vs Buy","Chase Efficiency"].map((h) => <th key={h} className="px-3 py-3 font-semibold">{h}</th>)}</tr></thead><tbody>{rows.map((row) => { const href=cardHref(row,sets), set=sets.get(String(row.setId)); return <tr key={row.cardVariantId} className="border-t border-[var(--border-subtle)] hover:bg-[rgba(45,212,191,.04)]"><td className="px-3 py-3 font-bold text-[var(--accent)]">#{row.ranks?.overall?.rank}</td><td className="px-3 py-3"><Link href={href || "#"} className="font-semibold text-[var(--text-primary)] hover:text-[var(--accent)]">{row.cardName}</Link><span className="mt-0.5 block text-[10px] text-[var(--text-secondary)]">{set?.name || row.setId}</span></td><td className="px-3 py-3 text-[var(--text-secondary)]">{row.rarity}</td><td className="px-3 py-3">{money.format(value(row.currentNearMintMarketPrice) || 0)}</td><td className="px-3 py-3">{odds(row)}</td><td className="px-3 py-3">{spend50(row) === null ? "—" : money.format(spend50(row))}</td><td className="px-3 py-3">{multiple50(row) === null ? "—" : `${multiple50(row).toFixed(1)}×`}</td><td className="px-3 py-3 font-semibold text-[var(--accent)]">{decimal.format(value(row.chaseEfficiency) || 0)}</td></tr>; })}</tbody></table></div>
      <div className="divide-y divide-[var(--border-subtle)] desk:hidden">{rows.map((row) => { const href=cardHref(row,sets), set=sets.get(String(row.setId)); return <Link key={row.cardVariantId} href={href || "#"} className="block p-4 hover:bg-[rgba(45,212,191,.04)]"><div className="flex items-start justify-between gap-3"><div><span className="text-[10px] font-bold text-[var(--accent)]">#{row.ranks?.overall?.rank}</span><h3 className="mt-1 font-semibold text-[var(--text-primary)]">{row.cardName}</h3><p className="text-xs text-[var(--text-secondary)]">{set?.name || row.setId} · {row.rarity}</p></div><div className="text-right"><strong className="text-sm text-[var(--accent)]">CE {decimal.format(value(row.chaseEfficiency)||0)}</strong><span className="mt-1 block text-xs text-[var(--text-secondary)]">{money.format(value(row.currentNearMintMarketPrice)||0)}</span></div></div><dl className="mt-3 grid grid-cols-3 gap-2 text-xs"><div><dt className="text-[10px] text-[var(--text-secondary)]">Pull odds</dt><dd>{odds(row)}</dd></div><div><dt className="text-[10px] text-[var(--text-secondary)]">50% cost</dt><dd>{spend50(row)===null?"—":money.format(spend50(row))}</dd></div><div><dt className="text-[10px] text-[var(--text-secondary)]">Vs buy</dt><dd>{multiple50(row)===null?"—":`${multiple50(row).toFixed(1)}×`}</dd></div></dl></Link>; })}</div>
      {result.status === "loading" ? <p className="p-5 text-center text-xs text-[var(--text-secondary)]">Loading card rankings…</p> : null}
      <footer className="flex items-center justify-between border-t border-[var(--border-subtle)] px-4 py-3 text-xs text-[var(--text-secondary)]"><span>{result.payload?.total ? `${result.payload.total.toLocaleString()} ranked printings` : "No ranked cards"}</span><div className="flex items-center gap-2"><button type="button" disabled={page<=1} onClick={()=>setPage((p)=>Math.max(1,p-1))} className="rounded border border-[var(--border-subtle)] px-3 py-2 disabled:opacity-40">Previous</button><span>Page {page} of {result.payload?.totalPages || 1}</span><button type="button" disabled={page >= (result.payload?.totalPages || 1)} onClick={()=>setPage((p)=>p+1)} className="rounded border border-[var(--border-subtle)] px-3 py-2 disabled:opacity-40">Next</button></div></footer>
    </section>
  );
}
