"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { buildPokemonCardHref } from "@/lib/pokemon/pokemonCardDetailClient";
import {
  getPokemonSetCardsPage,
  prefetchPokemonSetCardsPage,
} from "@/lib/pokemon/pokemonSetCardsClient";
import {
  ALL_CARDS_SORT_OPTIONS,
  CARD_TIMEFRAMES,
  DEFAULT_MARKET_MOVER_METRIC,
  MARKET_MOVER_METRIC_OPTIONS,
  getAllCardsDirectionLabel,
  resolveCardsRequest,
} from "@/components/pokemon/set-page/Cards/cardsControls.mjs";
import { buildCardsRequestKey, buildCardsScopeKey } from "./cardsRequestKey.mjs";

const PAGE_SIZE = 60;
const CACHE_LIMIT = 24;
const successfulScopes = new Map();

function readSection(searchParams) {
  return searchParams?.get?.("section") === "market-movers" ? "market-movers" : "all-cards";
}

function rememberScope(key, value) {
  successfulScopes.delete(key);
  successfulScopes.set(key, value);
  while (successfulScopes.size > CACHE_LIMIT) successfulScopes.delete(successfulScopes.keys().next().value);
}

function cardImage(card) {
  return card?.imageSmallUrl || card?.imageUrl || card?.image_small_url || card?.images?.small || null;
}

function movement(card, timeframe) {
  const source = timeframe === "30D" ? card?.movement30d : card?.movement7d;
  return source || { changeAmount: timeframe === "30D" ? card?.change30dAmount : card?.change7dAmount, changePercent: timeframe === "30D" ? card?.change30dPercent : card?.change7dPercent };
}

function money(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("en-US", { style: "currency", currency: "USD" }) : "—";
}

function CardTile({ card, setSlug, timeframe }) {
  const delta = movement(card, timeframe);
  const percent = Number(delta?.changePercent);
  const href = buildPokemonCardHref(setSlug, card);
  return (
    <Link href={href} className="set-glass-surface group min-w-0 overflow-hidden rounded-xl border p-2 transition-transform hover:-translate-y-0.5">
      <div className="aspect-[2.5/3.5] overflow-hidden rounded-lg bg-[var(--surface-panel)]">
        {cardImage(card) ? <img src={cardImage(card)} alt={card?.name || "Pokemon card"} loading="lazy" decoding="async" className="h-full w-full object-contain" /> : <div className="flex h-full items-center justify-center px-2 text-center text-xs text-[var(--text-secondary)]">{card?.name}</div>}
      </div>
      <p className="mt-2 truncate text-sm font-semibold text-[var(--text-primary)]">{card?.name || "Unknown card"}</p>
      <div className="mt-1 flex items-center justify-between gap-2 text-xs">
        <span className="font-semibold text-[var(--text-primary)]">{money(card?.currentPrice ?? card?.marketPrice)}</span>
        {Number.isFinite(percent) ? <span className={percent >= 0 ? "text-emerald-400" : "text-red-400"}>{percent >= 0 ? "+" : ""}{percent.toFixed(1)}%</span> : null}
      </div>
    </Link>
  );
}

function defaultRequest(setId) {
  return { setId, page: 1, pageSize: PAGE_SIZE, section: "all-cards", sort: "set-number", sortDirection: "asc", query: null, rarity: null, movementFilter: "all", movementSort: null, movementMetric: null };
}

export function prefetchCardsSetTab(setId) {
  const request = defaultRequest(setId);
  return prefetchPokemonSetCardsPage(setId, request);
}

export default function CardsSetTab({ setId, setSlug }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [cardsSection, setCardsSection] = useState(() => readSection(searchParams));
  const [selectedTimeframe, setSelectedTimeframe] = useState("7D");
  const [cardSortMode, setCardSortMode] = useState("set-number");
  const [cardSortDirection, setCardSortDirection] = useState("asc");
  const [cardMovementMetric, setCardMovementMetric] = useState(DEFAULT_MARKET_MOVER_METRIC);
  const [cardSearchQuery, setCardSearchQuery] = useState("");
  const [cardRarityFilter, setCardRarityFilter] = useState("");
  const [cardsPage, setCardsPage] = useState(1);
  const [retryNonce, setRetryNonce] = useState(0);
  const [state, setState] = useState({ status: "idle", setId, scopeKey: null, cards: [], pagination: null, filters: null, error: null });
  const sentinelRef = useRef(null);
  const activeRequestRef = useRef(null);

  useEffect(() => {
    const next = readSection(searchParams);
    setCardsSection(next);
    setCardSortDirection(next === "market-movers" ? "gainers" : "asc");
  }, [searchParams]);

  const resolved = resolveCardsRequest({ selectedSubTab: cardsSection, selectedTimeframe, activeSortMode: cardSortMode, activeSortDirection: cardSortDirection, activeMovementMetric: cardMovementMetric });
  const request = useMemo(() => ({
    setId,
    page: cardsPage,
    pageSize: PAGE_SIZE,
    section: cardsSection,
    sort: resolved.sort,
    sortDirection: resolved.sortDirection,
    query: cardSearchQuery.trim() || null,
    rarity: cardsSection === "all-cards" ? cardRarityFilter || null : null,
    movementFilter: resolved.movementFilter,
    movementSort: resolved.movementSort,
    movementMetric: resolved.movementMetric,
  }), [setId, cardsPage, cardsSection, resolved.sort, resolved.sortDirection, resolved.movementFilter, resolved.movementSort, resolved.movementMetric, cardSearchQuery, cardRarityFilter]);
  const scopeKey = buildCardsScopeKey(request);
  const requestKey = buildCardsRequestKey(request);

  useEffect(() => { setCardsPage(1); }, [setId, cardsSection, selectedTimeframe, cardSortMode, cardSortDirection, cardMovementMetric, cardSearchQuery, cardRarityFilter]);

  useEffect(() => {
    if (!setId) return;
    let cancelled = false;
    activeRequestRef.current = requestKey;
    const cached = successfulScopes.get(scopeKey);
    if (cached && cardsPage === 1) {
      setState(cached);
      return;
    }
    setState((previous) => ({ ...previous, status: cardsPage > 1 && previous.scopeKey === scopeKey ? "loading_more" : "loading", setId, scopeKey, error: null, cards: previous.scopeKey === scopeKey ? previous.cards : [] }));
    getPokemonSetCardsPage(setId, request).then((payload) => {
      if (cancelled || activeRequestRef.current !== requestKey) return;
      setState((previous) => {
        const append = cardsPage > 1 && previous.scopeKey === scopeKey;
        const seen = new Set();
        const cards = [...(append ? previous.cards : []), ...payload.cards].filter((card) => {
          const key = String(card?.id || card?.cardId || `${card?.name}:${card?.printedNumber}`);
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        const next = { status: cards.length ? "success" : "empty", setId, scopeKey, cards, pagination: payload.pagination, filters: payload.filters, error: null };
        rememberScope(scopeKey, next);
        return next;
      });
    }).catch((error) => {
      if (!cancelled && activeRequestRef.current === requestKey) setState((previous) => ({ ...previous, status: "error", error: error?.message || "Unable to load cards." }));
    });
    return () => { cancelled = true; };
  }, [setId, scopeKey, requestKey, cardsPage, retryNonce]);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !state.pagination?.hasNextPage || state.status === "loading_more") return;
    const observer = new IntersectionObserver((entries) => { if (entries.some((entry) => entry.isIntersecting)) setCardsPage((page) => page + 1); }, { rootMargin: "500px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, [state.pagination?.hasNextPage, state.status, state.cards.length]);

  const changeSection = (section) => {
    const params = new URLSearchParams(searchParams?.toString?.() || "");
    params.set("tab", "cards");
    if (section === "market-movers") params.set("section", section); else params.delete("section");
    setCardsSection(section);
    router.push(`${pathname}?${params}`, { scroll: false });
  };
  const active = state.setId === setId && state.scopeKey === scopeKey ? state : { ...state, status: "loading", cards: [] };
  const rarities = active.filters?.availableRarities || [];

  return (
    <section id="set-detail-cards" data-cards-section className="space-y-4">
      <div data-cards-toolbar className="set-glass-surface space-y-3 rounded-2xl border p-3 md:p-4">
        <div className="flex gap-2">
          {[['all-cards','All Cards'],['market-movers','Market Movers']].map(([value,label]) => <button key={value} type="button" onClick={() => changeSection(value)} aria-pressed={cardsSection === value} className={`rounded-lg px-3 py-2 text-sm font-semibold ${cardsSection === value ? 'bg-[var(--surface-hover)] text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}>{label}</button>)}
        </div>
        <input aria-label="Search cards by name" value={cardSearchQuery} onChange={(event) => setCardSearchQuery(event.target.value)} placeholder="Search cards by name" className="w-full max-w-sm rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm" />
        <div className="flex flex-wrap items-center gap-2">
          {cardsSection === "all-cards" ? <><select aria-label="Sort cards by" value={cardSortMode} onChange={(event) => setCardSortMode(event.target.value)} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm">{ALL_CARDS_SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select><button type="button" onClick={() => setCardSortDirection((value) => value === "asc" ? "desc" : "asc")} className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm font-semibold">{getAllCardsDirectionLabel(cardSortMode, cardSortDirection)}</button><select aria-label="Filter by rarity" value={cardRarityFilter} onChange={(event) => setCardRarityFilter(event.target.value)} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm"><option value="">All Rarities</option>{rarities.map((rarity) => <option key={rarity} value={rarity}>{rarity}</option>)}</select></> : <><button type="button" onClick={() => setCardSortDirection("gainers")} aria-pressed={cardSortDirection === "gainers"} className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm">Gainers</button><button type="button" onClick={() => setCardSortDirection("losers")} aria-pressed={cardSortDirection === "losers"} className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm">Losers</button>{MARKET_MOVER_METRIC_OPTIONS.map((option) => <button key={option.value} type="button" onClick={() => setCardMovementMetric(option.value)} aria-pressed={cardMovementMetric === option.value} className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm">{option.accessibleLabel}</button>)}</>}
          {CARD_TIMEFRAMES.map((timeframe) => <button key={timeframe} type="button" onClick={() => setSelectedTimeframe(timeframe)} aria-pressed={selectedTimeframe === timeframe} className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm">{timeframe}</button>)}
          <span className="ml-auto text-xs text-[var(--text-secondary)]">{active.cards.length.toLocaleString()} of {(active.pagination?.totalCards || active.cards.length).toLocaleString()} cards</span>
        </div>
      </div>
      {active.status === "loading" && active.cards.length === 0 ? <p className="py-12 text-center text-sm text-[var(--text-secondary)]">Loading cards…</p> : null}
      {active.status === "error" ? <div className="text-center"><p className="text-sm text-red-300">{active.error}</p><button type="button" onClick={() => setRetryNonce((value) => value + 1)} className="mt-2 rounded-lg border px-3 py-2 text-sm">Retry</button></div> : null}
      {active.status === "empty" ? <p className="py-12 text-center text-sm text-[var(--text-secondary)]">No cards found for this set.</p> : null}
      {active.cards.length ? <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">{active.cards.map((card) => <CardTile key={card?.id || card?.cardId || `${card?.name}:${card?.printedNumber}`} card={card} setSlug={setSlug} timeframe={selectedTimeframe} />)}</div> : null}
      <div ref={sentinelRef} data-cards-load-more-sentinel="true" aria-hidden="true" className="h-px" />
      {active.status === "loading_more" ? <p className="py-3 text-center text-sm text-[var(--text-secondary)]">Loading more cards…</p> : null}
    </section>
  );
}
