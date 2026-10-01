"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
import { buildPokemonCardDetailHref } from "@/lib/pokemon/pokemonCardDetailClient";
import { canonicalCardQueryKey } from "@/lib/rankings/rankingsSessionCache.mjs";
import { markRankingsLens } from "@/lib/rankings/rankingsLensPerf.mjs";
import styles from "./explore.module.css";
import { PlanBadge, PlanUpgradeLink } from "@/components/membership/PlanLock";
import { planPresentation } from "@/lib/membership/upgradeFunnel.mjs";
import { INDEX_PLAN_PREMIUM } from "@/lib/access/indexPlanAccess.mjs";
import { buildCardRowsParams, fetchCardRankingFacets, fetchChaseRows } from "@/lib/rankings/cardRankingsClient.mjs";
import CardRankingsFilterBar from "./CardRankingsFilterBar";

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});
const decimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });
const value = (input) =>
  Number.isFinite(Number(input)) ? Number(input) : null;

function LockedCards() {
  return (
    <section
      data-card-chase-efficiency-locked
      className={`${styles.surface} set-glass-surface overflow-hidden border ${planPresentation(INDEX_PLAN_PREMIUM).panelClassName} p-5 sm:p-7`}
    >
      <div className="mx-auto max-w-2xl py-7 text-center">
        <PlanBadge plan={INDEX_PLAN_PREMIUM} />
        <h2 className="mt-4 text-xl font-semibold text-[var(--text-primary)]">
          Rank every chase by opening efficiency
        </h2>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[var(--text-secondary)]">
          Compare exact card printings using current Near Mint value, modeled
          pull odds, and the cheapest verified pack-equivalent route.
        </p>
        <div
          data-card-chase-efficiency-locked-preview
          aria-hidden="true"
          className="mx-auto mt-6 grid max-w-lg grid-cols-3 gap-2 opacity-55"
        >
          {["medium", "short", "long"].map((shape) => (
            <div
              key={shape}
              className="space-y-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-3"
            >
              <span className="block h-2 w-2/3 rounded-full bg-[var(--surface-hover)]" />
              <span className="block h-2 w-1/2 rounded-full bg-[var(--surface-hover)]" />
              <span className="block h-2 w-full rounded-full bg-[var(--surface-hover)]" />
            </div>
          ))}
        </div>
        <p className="mt-5 text-xs font-medium text-[var(--text-secondary)]">
          Unlock rankings, filters, and exact-card chase routes.
        </p>
        <PlanUpgradeLink
          requiredPlan={INDEX_PLAN_PREMIUM}
          source="chase-efficiency"
          className="mt-4"
        />
      </div>
    </section>
  );
}

function cardHref(row, sets) {
  const set = sets.get(String(row?.setId || ""));
  return buildPokemonCardDetailHref({
    setCanonicalKey: set?.canonicalKey || set?.name || row?.setId,
    canonicalCardId: row?.canonicalCardId,
    cardVariantId: row?.cardVariantId,
  });
}
function CardThumb({ row }) {
  return (
    <span className="relative block h-14 w-10 shrink-0 overflow-hidden rounded bg-white/[.06]">
      {row.imageSmallUrl ? (
        <Image
          src={row.imageSmallUrl}
          alt=""
          fill
          sizes="40px"
          className="object-contain"
        />
      ) : null}
    </span>
  );
}
function odds(row) {
  const p = value(row?.exactPullProbability);
  return p && p > 0 ? `1 in ${decimal.format(1 / p)}` : "—";
}
function spend50(row) {
  return value(row?.chaseSpend50 ?? row?.milestones?.["50"]?.spend);
}
function multiple50(row) {
  const direct = value(row?.costMultiple50);
  const spend = spend50(row),
    price = value(row?.currentNearMintMarketPrice);
  return direct ?? (spend !== null && price ? spend / price : null);
}

export default function CardChaseEfficiencyRankings({
  entitled,
  authStatus = "resolved",
  sessionCache,
}) {
  const [filters, setFilters] = useState({
    search: "",
    era: "",
    set: "",
    rarity: "",
    min_price: "",
    max_price: "",
    sort: "rank", direction: "asc",
  });
  const [page, setPage] = useState(1);
  const [result, setResult] = useState({ status: "idle", payload: null });
  const [facets, setFacets] = useState(null);
  const [facetError, setFacetError] = useState("");
  const [facetRetry, setFacetRetry] = useState(0);
  const [retry, setRetry] = useState(0);
  const forceRetry = useRef(false);
  const requestGeneration = useRef(0);
  const sets = useMemo(
    () =>
      new Map(
        (facets?.sets || []).map((target) => [
          String(target?.setId),
          {
            name: target?.setName,
            canonicalKey: target?.canonicalKey,
            era: target?.eraId,
          },
        ]),
      ),
    [facets],
  );
  const {
    search,
    era,
    set: selectedSet,
    rarity,
    min_price: minPrice,
    max_price: maxPrice,
    sort,
    direction,
  } = filters;
  useEffect(() => {
    if (authStatus === "resolving" || !entitled) return undefined;
    let active = true;
    const key = "cards:facets:chase";
    const load = () => fetchCardRankingFacets("chase");
    (sessionCache ? sessionCache.request(key, load, { force: facetRetry > 0 }) : load())
      .then((payload) => { if (active) { setFacets(payload); setFacetError(""); } })
      .catch((error) => { if (active) setFacetError(error.message); });
    return () => { active = false; };
  }, [authStatus, entitled, sessionCache, facetRetry]);
  useEffect(() => {
    if (authStatus === "resolving") return undefined;
    if (!entitled) {
      requestGeneration.current += 1;
      setResult({ status: "idle", payload: null });
      setFacets(null);
      setFacetError("");
      return undefined;
    }
    let active = true;
    const generation = ++requestGeneration.current;
    const forced = forceRetry.current;
    forceRetry.current = false;
    const timer = setTimeout(
      () => {
        const params = buildCardRowsParams({ page, filters });
        const cacheKey = canonicalCardQueryKey(params);
        const cached = !forced && sessionCache?.peek(cacheKey);
        if (cached) {
          markRankingsLens("cards", "render-ready");
          setResult({ status: "ready", payload: cached });
          return;
        }
        setResult((current) => ({ ...current, status: "loading" }));
        markRankingsLens("cards", "request-start");
        const load = () => fetchChaseRows(params);
        const request = sessionCache
          ? sessionCache.request(cacheKey, load, { force: forced })
          : load();
        request
          .then((payload) => {
            if (active && generation === requestGeneration.current) {
              markRankingsLens("cards", "response-received");
              setResult({ status: "ready", payload });
              requestAnimationFrame(() =>
                markRankingsLens("cards", "render-ready"),
              );
            }
          })
          .catch((error) => {
            if (active && generation === requestGeneration.current && error.name !== "AbortError")
              setResult((current) => ({
                status: "error",
                error: error.message,
                payload: current.payload,
              }));
          });
      },
      search ? 250 : 0,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [
    authStatus,
    entitled,
    page,
    search,
    era,
    selectedSet,
    rarity,
    minPrice,
    maxPrice,
    sort,
    direction,
    filters,
    sessionCache,
    retry,
  ]);
  if (!entitled) return <LockedCards />;
  const update = (key, next) => {
    setResult({ status: "loading", payload: null });
    setFilters((current) => {
      const changed = { ...current, [key]: next };
      if (key === "era" && current.set) {
        const selected = sets.get(current.set);
        if (!next || String(selected?.era) !== next) changed.set = "";
      }
      return changed;
    });
    setPage(1);
  };
  const rows = result.payload?.rows || [];
  return (
    <section
      data-card-chase-efficiency-rankings
      className={`${styles.surface} set-glass-surface overflow-hidden`}
    >
      <header className="border-b border-[var(--border-subtle)] px-4 py-4 sm:px-5">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          Best Cards to Chase
        </h2>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          Official ranks use exact printings and the best verified
          pack-equivalent cost.
        </p>
      </header>
      <CardRankingsFilterBar filters={filters} facets={facets} onChange={update} onClear={() => { setResult({ status: "loading", payload: null }); setFilters({ search: "", era: "", set: "", rarity: "", min_price: "", max_price: "", sort: "rank", direction: "asc" }); setPage(1); }} />
      {facetError ? <p className="px-5 pt-4 text-sm text-rose-300">Filters could not be refreshed. <button type="button" className="underline" onClick={() => setFacetRetry((value) => value + 1)}>Retry filters</button></p> : null}
      {result.status === "error" ? (
        <p className="p-6 text-sm text-rose-300">{result.payload ? "Refresh failed; showing the last successful result. " : `${result.error} `}<button type="button" className="underline" onClick={() => { forceRetry.current = true; setRetry((value) => value + 1); }}>Retry</button></p>
      ) : null}
      <div className="hidden overflow-x-auto desk:block">
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase tracking-wider text-[var(--text-secondary)]">
            <tr>
              {[
                "Rank",
                "Card / Set",
                "Rarity",
                "Market Price",
                "Pull Odds",
                "50% Chase Cost",
                "Cost vs Buy",
                "Chase Efficiency",
              ].map((h) => (
                <th key={h} className="px-3 py-3 font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const href = cardHref(row, sets),
                set = sets.get(String(row.setId));
              return (
                <tr
                  key={row.cardVariantId}
                  className="border-t border-[var(--border-subtle)] hover:bg-[rgba(45,212,191,.04)]"
                >
                  <td className="px-3 py-3 font-bold text-[var(--text-primary)]">
                    #{row.ranks?.overall?.rank}
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-3">
                      <CardThumb row={row} />
                      <div>
                        <Link href={href || "#"} className="font-semibold text-[var(--text-primary)] hover:text-[var(--accent)]">{row.cardName}</Link>
                        <span className="mt-0.5 block text-[10px] text-[var(--text-secondary)]">{set?.name || row.setId}</span>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-3 text-[var(--text-secondary)]">
                    {row.rarity}
                  </td>
                  <td className="px-3 py-3">
                    {money.format(value(row.currentNearMintMarketPrice) || 0)}
                  </td>
                  <td className="px-3 py-3">{odds(row)}</td>
                  <td className="px-3 py-3">
                    {spend50(row) === null ? "—" : money.format(spend50(row))}
                  </td>
                  <td className="px-3 py-3">
                    {multiple50(row) === null
                      ? "—"
                      : `${multiple50(row).toFixed(1)}×`}
                  </td>
                  <td className="px-3 py-3 font-semibold text-[var(--accent)]">
                    {decimal.format(value(row.chaseEfficiency) || 0)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="divide-y divide-[var(--border-subtle)] desk:hidden">
        {rows.map((row) => {
          const href = cardHref(row, sets),
            set = sets.get(String(row.setId));
          return (
            <Link
              key={row.cardVariantId}
              href={href || "#"}
              className="block p-4 hover:bg-[rgba(45,212,191,.04)]"
            >
              <div className="flex items-start justify-between gap-3">
                <CardThumb row={row} />
                <div className="min-w-0 flex-1">
                  <span className="text-[10px] font-bold text-[var(--text-primary)]">
                    #{row.ranks?.overall?.rank}
                  </span>
                  <h3 className="mt-1 font-semibold text-[var(--text-primary)]">
                    {row.cardName}
                  </h3>
                  <p className="text-xs text-[var(--text-secondary)]">
                    {set?.name || row.setId} · {row.rarity}
                  </p>
                </div>
                <div className="text-right">
                  <strong className="text-sm text-[var(--accent)]">
                    CE {decimal.format(value(row.chaseEfficiency) || 0)}
                  </strong>
                  <span className="mt-1 block text-xs text-[var(--text-secondary)]">
                    {money.format(value(row.currentNearMintMarketPrice) || 0)}
                  </span>
                </div>
              </div>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
                <div>
                  <dt className="text-[10px] text-[var(--text-secondary)]">
                    Pull odds
                  </dt>
                  <dd>{odds(row)}</dd>
                </div>
                <div>
                  <dt className="text-[10px] text-[var(--text-secondary)]">
                    50% cost
                  </dt>
                  <dd>
                    {spend50(row) === null ? "—" : money.format(spend50(row))}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] text-[var(--text-secondary)]">
                    Vs buy
                  </dt>
                  <dd>
                    {multiple50(row) === null
                      ? "—"
                      : `${multiple50(row).toFixed(1)}×`}
                  </dd>
                </div>
              </dl>
            </Link>
          );
        })}
      </div>
      {result.status === "loading" ? (
        <p className="p-5 text-center text-xs text-[var(--text-secondary)]">
          Loading card rankings…
        </p>
      ) : null}
      <footer className="flex items-center justify-between border-t border-[var(--border-subtle)] px-4 py-3 text-xs text-[var(--text-secondary)]">
        <span>
          {result.status === "idle" || (result.status === "loading" && !result.payload)
            ? "Loading card rankingsâ€¦"
            : result.payload?.total
              ? `${result.payload.total.toLocaleString()} ranked printings`
              : "No ranked cards"}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => { setResult({ status: "loading", payload: null }); setPage((p) => Math.max(1, p - 1)); }}
            className="rounded border border-[var(--border-subtle)] px-3 py-2 disabled:opacity-40"
          >
            Previous
          </button>
          {result.payload ? <span>Page {page} of {result.payload.totalPages || 0}</span> : null}
          <button
            type="button"
            disabled={page >= (result.payload?.totalPages || 1)}
            onClick={() => { setResult({ status: "loading", payload: null }); setPage((p) => p + 1); }}
            className="rounded border border-[var(--border-subtle)] px-3 py-2 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </footer>
    </section>
  );
}
