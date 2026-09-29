"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import SegmentedControl from "@/components/ui/SegmentedControl";
import InfoPopover from "@/components/ui/InfoPopover";
import { PlanBadge, PlanUpgradeLink } from "@/components/membership/PlanLock";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import { planPresentation } from "@/lib/membership/upgradeFunnel.mjs";
import { buildPokemonCardDetailHref } from "@/lib/pokemon/pokemonCardDetailClient";
import { canonicalCardQueryKey } from "@/lib/rankings/rankingsSessionCache.mjs";
import { buildCardRowsParams, fetchCardRankingFacets, fetchCollectorRows } from "@/lib/rankings/cardRankingsClient.mjs";
import CardRankingsFilterBar from "./CardRankingsFilterBar";
import styles from "./explore.module.css";

export const COLLECTOR_LENSES = [
  { value: "overall", label: "Overall", score: "collectorAppeal", heading: "Collector Appeal" },
  { value: "pokemon", label: "Pokémon", score: "componentScore", heading: "Pokémon Appeal" },
  { value: "trainer", label: "Trainer", score: "componentScore", heading: "Trainer Appeal" },
  { value: "artist", label: "Artist", score: "componentScore", heading: "Artist Appeal" },
  { value: "playability", label: "Playability", score: "componentScore", heading: "Playability" },
];
const INITIAL_FILTERS = { search: "", era: "", set: "", rarity: "", sort: "rank", direction: "asc" };

function Lock() {
  return <section data-card-collector-appeal-locked className={`${styles.surface} set-glass-surface border ${planPresentation(INDEX_PLAN_PLUS).panelClassName} p-7 text-center`}>
    <PlanBadge plan={INDEX_PLAN_PLUS} /><h2 className="mt-4 text-xl font-semibold">Understand what collectors chase</h2>
    <p className="mx-auto mt-2 max-w-xl text-sm text-[var(--text-secondary)]">Explore globally ranked card appeal with synthetic preview rows kept behind the Plus boundary.</p>
    <PlanUpgradeLink requiredPlan={INDEX_PLAN_PLUS} source="card-collector-appeal" className="mt-4" />
  </section>;
}
function Thumb({ row }) {
  return <span className="relative block h-16 w-11 shrink-0 overflow-hidden rounded bg-white/[.06]">{row.imageSmallUrl ? <Image src={row.imageSmallUrl} alt="" fill sizes="44px" className="object-contain" /> : null}</span>;
}
function href(row) {
  return buildPokemonCardDetailHref({ setCanonicalKey: row.setCanonicalKey || row.setName || row.setId, canonicalCardId: row.canonicalCardId });
}
function score(value) {
  const numeric = Number(value);
  return value === null || value === undefined || !Number.isFinite(numeric) ? "—" : numeric.toFixed(1);
}

export default function CardCollectorAppealRankings({ entitled, authStatus = "resolved", sessionCache }) {
  const [lens, setLens] = useState("overall");
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [page, setPage] = useState(1);
  const [facets, setFacets] = useState(null);
  const [facetError, setFacetError] = useState("");
  const [results, setResults] = useState({});
  const active = COLLECTOR_LENSES.find((item) => item.value === lens);
  const result = results[lens] || { status: "idle", payload: null };

  useEffect(() => {
    if (authStatus === "resolving" || !entitled) return undefined;
    let current = true;
    const key = "cards:facets:collector";
    const load = () => fetchCardRankingFacets("collector");
    (sessionCache ? sessionCache.request(key, load) : load()).then((payload) => { if (current) setFacets(payload); }).catch((error) => { if (current) setFacetError(error.message); });
    return () => { current = false; };
  }, [authStatus, entitled, sessionCache]);

  useEffect(() => {
    if (authStatus === "resolving" || !entitled) return undefined;
    let current = true;
    const timer = setTimeout(() => {
      const params = buildCardRowsParams({ lens, page, filters });
      const key = canonicalCardQueryKey(params, `collector:${lens}`);
      setResults((state) => ({ ...state, [lens]: { ...state[lens], status: "loading" } }));
      const load = () => fetchCollectorRows(params);
      (sessionCache ? sessionCache.request(key, load) : load()).then((payload) => {
        if (current) setResults((state) => ({ ...state, [lens]: { status: "ready", payload } }));
      }).catch((error) => {
        if (current) setResults((state) => ({ ...state, [lens]: { status: "error", error: error.message, payload: state[lens]?.payload || null } }));
      });
    }, filters.search ? 250 : 0);
    return () => { current = false; clearTimeout(timer); };
  }, [authStatus, entitled, lens, page, filters, sessionCache]);

  const setMap = useMemo(() => new Map((facets?.sets || []).map((item) => [String(item.setId), item])), [facets]);
  if (!entitled) return <Lock />;
  const update = (key, value) => {
    setFilters((current) => {
      const next = { ...current, [key]: value };
      if (key === "era" && current.set) {
        const selected = setMap.get(current.set);
        if (!value || String(selected?.eraId) !== value) next.set = "";
      }
      return next;
    });
    setPage(1);
  };
  const rows = result.payload?.rows || [];
  return <section data-card-collector-appeal-rankings data-collector-lens={lens} className={`${styles.surface} set-glass-surface overflow-hidden`}>
    <header className="border-b border-[var(--border-subtle)] p-4 sm:p-5">
      <div className="flex items-center gap-2"><h2 className="font-semibold">Card Collector Appeal</h2><InfoPopover text={lens === "overall" ? "Overall Collector Appeal combines multiple card subject types under the current production model. Cross-domain calibration is still under evaluation." : "Ranks are global within the selected Collector component."} /></div>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">Component tabs rank only cards with that component available. Ranks stay global within the component even when you filter by Era, Set, rarity, or search.</p>
      <SegmentedControl options={COLLECTOR_LENSES} value={lens} onChange={(value) => { setLens(value); setPage(1); }} ariaLabel="Collector component" compact mobileScroll className="mt-3" />
    </header>
    <CardRankingsFilterBar filters={filters} facets={facets} onChange={update} onClear={() => { setFilters(INITIAL_FILTERS); setPage(1); }} />
    {facetError ? <p className="px-5 pt-4 text-sm text-rose-300">{facetError}</p> : null}
    {result.status === "error" ? <p className="px-5 pt-4 text-sm text-rose-300">{result.error}</p> : null}
    <div className="hidden desk:block">
      <table className="w-full table-fixed text-left text-xs"><colgroup><col className="w-[4.5rem]" /><col /><col className="w-[14rem]" /><col className="w-[9rem]" /></colgroup>
        <thead className="text-[10px] uppercase tracking-wider text-[var(--text-secondary)]"><tr><th className="px-3 py-3">Rank</th><th className="px-3 py-3">Card</th><th className="px-3 py-3">Set</th><th className="px-3 py-3">{active.heading}</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.canonicalCardId} className="border-t border-[var(--border-subtle)] hover:bg-[rgba(45,212,191,.04)]"><td className="px-3 py-3 font-bold">#{row.rank}</td><td className="px-3 py-2"><div className="flex items-center gap-3"><Thumb row={row} /><div className="min-w-0"><Link href={href(row) || "#"} className="font-semibold hover:text-[var(--accent)]">{row.cardName}</Link><span className="block text-[10px] text-[var(--text-secondary)]">{row.cardNumber || row.number || row.rarity || ""}</span>{lens === "artist" && row.artistNames?.length ? <span className="block text-[10px] text-[var(--text-secondary)]">{row.artistNames.join(", ")}</span> : null}</div></div></td><td className="px-3 py-3 text-[var(--text-secondary)]">{row.setName || "—"}</td><td className="px-3 py-3 text-base font-semibold text-[var(--accent)]">{score(row[active.score])}</td></tr>)}</tbody>
      </table>
    </div>
    <div className="divide-y divide-[var(--border-subtle)] desk:hidden">{rows.map((row) => <Link key={row.canonicalCardId} href={href(row) || "#"} className="flex gap-3 p-4"><Thumb row={row} /><div className="min-w-0 flex-1"><span className="text-[10px] font-bold">#{row.rank}</span><div className="flex items-start justify-between gap-2"><div className="min-w-0"><strong className="block truncate">{row.cardName}</strong><span className="text-xs text-[var(--text-secondary)]">{row.setName}{row.cardNumber ? ` · ${row.cardNumber}` : ""}</span></div><div className="shrink-0 text-right"><span className="block text-[10px] text-[var(--text-secondary)]">{active.heading}</span><strong className="text-base text-[var(--accent)]">{score(row[active.score])}</strong></div></div></div></Link>)}</div>
    {result.status === "loading" ? <div data-card-rankings-loading className="space-y-2 p-5"><span className="block h-12 animate-pulse rounded bg-white/[.04]" /><span className="block h-12 animate-pulse rounded bg-white/[.04]" /></div> : null}
    <footer className="flex items-center justify-between border-t border-[var(--border-subtle)] p-3 text-xs text-[var(--text-secondary)]"><span>{result.payload?.total?.toLocaleString() || 0} ranked cards</span><div className="flex items-center gap-2"><button type="button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button><span>Page {page} of {result.payload?.totalPages || 1}</span><button type="button" disabled={page >= (result.payload?.totalPages || 1)} onClick={() => setPage((value) => value + 1)}>Next</button></div></footer>
  </section>;
}
