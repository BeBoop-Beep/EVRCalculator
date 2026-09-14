"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import TableSearchInput from "@/components/ui/TableSearchInput";
import { PlanBadge, PlanUpgradeLink } from "@/components/membership/PlanLock";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import { planPresentation } from "@/lib/membership/upgradeFunnel.mjs";
import { buildPokemonCardDetailHref } from "@/lib/pokemon/pokemonCardDetailClient";
import { canonicalCardQueryKey } from "@/lib/rankings/rankingsSessionCache.mjs";
import styles from "./explore.module.css";

const SORTS = [
  ["rank", "Global rank"],
  ["collector_appeal", "Collector Appeal"],
  ["pokemon_appeal", "Pokémon Appeal"],
  ["trainer_appeal", "Trainer Appeal"],
  ["artist_appeal", "Artist Appeal"],
  ["playability", "Playability"],
  ["pull_probability", "Modeled pull rate"],
  ["name", "Alphabetical"],
];
const RARITIES = [
  "Special Illustration Rare",
  "Illustration Rare",
  "Hyper Rare",
  "Mega Hyper Rare",
  "Ultra Rare",
  "Double Rare",
];
const number = (v) =>
  v === null || v === undefined || !Number.isFinite(Number(v))
    ? null
    : Number(v);
const score = (v) => (number(v) === null ? "—" : number(v).toFixed(1));
const pull = (v) =>
  number(v) > 0
    ? `1 in ${(1 / number(v)).toLocaleString("en-US", { maximumFractionDigits: 0 })}`
    : "—";

function Lock() {
  return (
    <section
      data-card-collector-appeal-locked
      className={`${styles.surface} set-glass-surface border ${planPresentation(INDEX_PLAN_PLUS).panelClassName} p-7 text-center`}
    >
      <PlanBadge plan={INDEX_PLAN_PLUS} />
      <h2 className="mt-4 text-xl font-semibold">
        Understand what collectors chase
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-sm text-[var(--text-secondary)]">
        Explore globally ranked card appeal with subject, artist, playability,
        treatment, and modeled scarcity context.
      </p>
      <PlanUpgradeLink
        requiredPlan={INDEX_PLAN_PLUS}
        source="card-collector-appeal"
        className="mt-4"
      />
    </section>
  );
}
function Thumb({ row }) {
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
function cardHref(row) {
  return buildPokemonCardDetailHref({
    setCanonicalKey: row.setCanonicalKey || row.setName || row.setId,
    canonicalCardId: row.canonicalCardId,
  });
}

export default function CardCollectorAppealRankings({
  entitled,
  targets = [],
  sessionCache,
}) {
  const [filters, setFilters] = useState({
    search: "",
    era: "",
    set: "",
    rarity: "",
    sort: "rank",
    direction: "asc",
  });
  const [page, setPage] = useState(1);
  const [result, setResult] = useState({ status: "idle", payload: null });
  const eras = useMemo(
    () =>
      [
        ...new Set(
          targets.map((x) => String(x?.era || "").trim()).filter(Boolean),
        ),
      ].sort(),
    [targets],
  );
  const sets = useMemo(
    () =>
      targets
        .map((x) => ({
          id: String(x?.set_id || x?.target_id || x?.id),
          name: x?.name,
          era: x?.era,
        }))
        .filter((x) => !filters.era || x.era === filters.era)
        .sort((a, b) => String(a.name).localeCompare(String(b.name))),
    [targets, filters.era],
  );
  useEffect(() => {
    if (!entitled) {
      setResult({ status: "idle", payload: null });
      return;
    }
    let active = true;
    const timer = setTimeout(
      () => {
        const params = new URLSearchParams({
          page: String(page),
          page_size: "50",
          sort: filters.sort,
          direction: filters.direction,
        });
        for (const [k, v] of Object.entries({
          search: filters.search,
          era: filters.era,
          set: filters.set,
          rarity: filters.rarity,
        }))
          if (v.trim()) params.set(k, v);
        const key = canonicalCardQueryKey(params, "collector");
        const load = () =>
          fetch(`/api/explore/card-collector-appeal?${params}`, {
            cache: "no-store",
          }).then(async (r) => {
            const p = await r.json();
            if (!r.ok)
              throw new Error(
                p?.detail?.message || p?.message || "Unable to load rankings",
              );
            return p;
          });
        setResult((x) => ({ ...x, status: "loading" }));
        (sessionCache ? sessionCache.request(key, load) : load())
          .then((payload) => active && setResult({ status: "ready", payload }))
          .catch(
            (error) =>
              active &&
              setResult((x) => ({
                status: "error",
                error: error.message,
                payload: x.payload,
              })),
          );
      },
      filters.search ? 250 : 0,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [entitled, page, filters, sessionCache]);
  if (!entitled) return <Lock />;
  const update = (k, v) => {
    setFilters((x) => ({ ...x, [k]: v, ...(k === "era" ? { set: "" } : {}) }));
    setPage(1);
  };
  const rows = result.payload?.rows || [];
  return (
    <section
      data-card-collector-appeal-rankings
      className={`${styles.surface} set-glass-surface overflow-hidden`}
    >
      <header className="border-b border-[var(--border-subtle)] p-5">
        <h2 className="font-semibold">Card Collector Appeal</h2>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          Global prepared ranks from the current price-blind V7 model. Treatment
          and modeled pull rate are context, not headline score inputs.
        </p>
      </header>
      <div className="grid gap-2 border-b border-[var(--border-subtle)] p-3 sm:grid-cols-2 desk:grid-cols-3">
        <TableSearchInput
          value={filters.search}
          onChange={(e) => update("search", e.target.value)}
          placeholder="Search cards"
          ariaLabel="Search Collector Appeal cards"
        />
        <select
          aria-label="Filter by era"
          value={filters.era}
          onChange={(e) => update("era", e.target.value)}
          className={`${styles.setMarketControl} min-h-11 px-2 text-xs`}
        >
          <option value="">All eras</option>
          {eras.map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <select
          aria-label="Filter by set"
          value={filters.set}
          onChange={(e) => update("set", e.target.value)}
          className={`${styles.setMarketControl} min-h-11 px-2 text-xs`}
        >
          <option value="">All sets</option>
          {sets.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by rarity"
          value={filters.rarity}
          onChange={(e) => update("rarity", e.target.value)}
          className={`${styles.setMarketControl} min-h-11 px-2 text-xs`}
        >
          <option value="">All rarities</option>
          {RARITIES.map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <select
          aria-label="Sort cards"
          value={filters.sort}
          onChange={(e) => update("sort", e.target.value)}
          className={`${styles.setMarketControl} min-h-11 px-2 text-xs`}
        >
          {SORTS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <select
          aria-label="Sort direction"
          value={filters.direction}
          onChange={(e) => update("direction", e.target.value)}
          className={`${styles.setMarketControl} min-h-11 px-2 text-xs`}
        >
          <option value="asc">Lowest first</option>
          <option value="desc">Highest first</option>
        </select>
      </div>
      {result.status === "error" ? (
        <p className="p-5 text-rose-300">{result.error}</p>
      ) : null}
      <div className="hidden overflow-x-auto desk:block">
        <table className="w-full text-left text-xs">
          <thead>
            <tr>
              {[
                "Rank",
                "Card / Set",
                "Rarity",
                "Collector Appeal",
                "Pokémon Appeal",
                "Trainer Appeal",
                "Artist Appeal",
                "Playability",
                "Treatment",
                "Modeled Pull Rate",
              ].map((h) => (
                <th key={h} className="px-3 py-3 font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.canonicalCardId}
                className="border-t border-[var(--border-subtle)]"
              >
                <td className="px-3 py-3 font-semibold text-[var(--text-primary)]">
                  #{row.rank}
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-3">
                    <Thumb row={row} />
                    <div>
                      <Link
                        href={cardHref(row) || "#"}
                        className="font-semibold hover:text-[var(--accent)]"
                      >
                        {row.cardName}
                      </Link>
                      <span className="block text-[10px] text-[var(--text-secondary)]">
                        {row.setName}
                      </span>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-3">{row.rarity || "—"}</td>
                <td className="px-3 py-3 font-semibold text-[var(--accent)]">
                  {score(row.collectorAppeal)}
                </td>
                <td className="px-3 py-3">{score(row.pokemonAppeal)}</td>
                <td className="px-3 py-3">{score(row.trainerAppeal)}</td>
                <td className="px-3 py-3">{score(row.artistAppeal)}</td>
                <td className="px-3 py-3">{score(row.playability)}</td>
                <td className="px-3 py-3">{row.treatmentCategory || "—"}</td>
                <td className="px-3 py-3">
                  {pull(row.modeledPullProbability)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="divide-y divide-[var(--border-subtle)] desk:hidden">
        {rows.map((row) => (
          <Link
            key={row.canonicalCardId}
            href={cardHref(row) || "#"}
            className="flex gap-3 p-4"
          >
            <Thumb row={row} />
            <div className="min-w-0 flex-1">
              <div className="flex justify-between gap-2">
                <strong className="truncate">{row.cardName}</strong>
                <span className="text-[var(--accent)]">
                  {score(row.collectorAppeal)}
                </span>
              </div>
              <p className="text-xs text-[var(--text-secondary)]">
                #{row.rank} · {row.setName} · {row.rarity || "—"}
              </p>
              <p className="mt-2 text-xs">
                Pokémon {score(row.pokemonAppeal)} · Trainer{" "}
                {score(row.trainerAppeal)} · Artist {score(row.artistAppeal)} ·
                Play {score(row.playability)}
              </p>
            </div>
          </Link>
        ))}
      </div>
      {result.status === "loading" ? (
        <p className="p-5 text-center text-xs text-[var(--text-secondary)]">
          Loading card rankings…
        </p>
      ) : null}
      <footer className="flex items-center justify-between border-t border-[var(--border-subtle)] p-3 text-xs text-[var(--text-secondary)]">
        <span>{result.payload?.total?.toLocaleString() || 0} ranked cards</span>
        <div className="flex items-center gap-2">
          <button
            disabled={page <= 1}
            onClick={() => setPage((x) => Math.max(1, x - 1))}
          >
            Previous
          </button>
          <span>
            {page} / {result.payload?.totalPages || 1}
          </span>
          <button
            disabled={page >= (result.payload?.totalPages || 1)}
            onClick={() => setPage((x) => x + 1)}
          >
            Next
          </button>
        </div>
      </footer>
    </section>
  );
}
