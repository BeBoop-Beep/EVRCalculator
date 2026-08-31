"use client";

import { useEffect, useRef, useState } from "react";
import SetTabLoadingPanel from "@/components/explore/SetTabLoadingPanel";
import InDexLogoLoader from "@/components/brand/InDexLogoLoader";
import DeltaTrendIcon from "@/components/ui/DeltaTrendIcon";
import {
  ALL_CARDS_SORT_OPTIONS,
  CARD_TIMEFRAMES,
  MARKET_MOVER_METRIC_OPTIONS,
  DEFAULT_MARKET_MOVER_METRIC,
  getAllCardsDirectionLabel,
  getEffectiveRarityFilter,
  resolveCardsRequest,
} from "@/components/pokemon/set-page/Cards/cardsControls.mjs";
import useSetCardsController from "@/hooks/pokemon/useSetCardsController";
import RichChecklistCardTile from "./RichChecklistCardTile";
import RichSetSectionTabs from "./RichSetSectionTabs";

export default function RichCardsSetTab({
  cardsSection,
  handleSetDetailNavSelect,
  setId,
  canFetch,
  activeSetSlug,
}) {
  const CardTile = RichChecklistCardTile;
  const SectionTabs = RichSetSectionTabs;
  const cardsSubTab = "checklist";
  const [selectedTimeframe, setSelectedTimeframe] = useState("7D");
  const [cardSortMode, setCardSortMode] = useState("set-number");
  const [cardSortDirection, setCardSortDirection] = useState(() => cardsSection === "market-movers" ? "gainers" : "asc");
  const [cardMovementMetric, setCardMovementMetric] = useState(DEFAULT_MARKET_MOVER_METRIC);
  const [cardSearchQuery, setCardSearchQuery] = useState("");
  const [cardRarityFilter, setCardRarityFilter] = useState("");
  useEffect(() => {
    setCardSortMode("set-number");
    setCardSortDirection(cardsSection === "market-movers" ? "gainers" : "asc");
  }, [cardsSection]);
  const cardsRequest = resolveCardsRequest({ selectedSubTab: cardsSection, selectedTimeframe, activeSortMode: cardSortMode, activeSortDirection: cardSortDirection, activeMovementMetric: cardMovementMetric });
  const { state: activeCardsPageState, page: cardsPage, setPage: setCardsPage, retry: retryCardsPage } = useSetCardsController({
    enabled: cardsSubTab === "checklist", canFetch, setId,
    section: cardsSection === "market-movers" ? "market-movers" : "all-cards",
    sort: cardsRequest.sort, sortDirection: cardsRequest.sortDirection, query: cardSearchQuery,
    rarity: getEffectiveRarityFilter(cardsSection, cardRarityFilter), movementFilter: cardsRequest.movementFilter,
    movementSort: cardsRequest.movementSort, movementMetric: cardsRequest.movementMetric, pageSize: 60,
  });
  const effectiveCardsPageCards = activeCardsPageState.cards;
  const effectiveCardsPageStatus = activeCardsPageState.status;
  const displayedChecklistCards = effectiveCardsPageCards;
  const hasCardMovementData = activeCardsPageState.filters?.availableSorts?.includes("7d-movers") ?? true;
  const availableCardRarities = activeCardsPageState.filters?.availableRarities || [];
  const cardsPageIsLoadingMore = activeCardsPageState.status === "loading_more";
  const cardsPageIsFetching = activeCardsPageState.status === "loading" || cardsPageIsLoadingMore;
  const cardsPageLoadMoreError = Boolean(activeCardsPageState.error && activeCardsPageState.cards.length > 0 && activeCardsPageState.pagination?.hasNextPage);
  const cardsPageFullyLoaded = Boolean(activeCardsPageState.pagination && !activeCardsPageState.pagination.hasNextPage && activeCardsPageState.pagination.totalPages > 1);
  const loadMoreGateRef = useRef({ canLoadMore: false, nextPage: 1 });
  loadMoreGateRef.current = { canLoadMore: Boolean(activeCardsPageState.pagination?.hasNextPage && !cardsPageIsFetching && !activeCardsPageState.error && cardsPage === activeCardsPageState.page), nextPage: (activeCardsPageState.pagination?.page || activeCardsPageState.page || 1) + 1 };
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return undefined;
    const sentinels = Array.from(document.querySelectorAll("[data-cards-load-more-sentinel]"));
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting) || !loadMoreGateRef.current.canLoadMore) return;
      const nextPage = loadMoreGateRef.current.nextPage;
      setCardsPage((page) => page >= nextPage ? page : nextPage);
    }, { rootMargin: "1000px 0px" });
    sentinels.forEach((sentinel) => observer.observe(sentinel));
    return () => observer.disconnect();
  }, [setId, setCardsPage, effectiveCardsPageCards.length]);
  return (
    <section id="set-detail-cards" data-cards-section className="scroll-mt-24 space-y-4 md:scroll-mt-28">
    {/* One compact controls panel: sub-tabs, search, sort/rarity
    or direction, timeframe, movement metric, and the count. */}
    <div data-cards-toolbar className="set-glass-surface space-y-3 rounded-2xl border p-3 md:p-4">
    <SectionTabs
    value={cardsSection}
    onChange={(nextSection) =>
    handleSetDetailNavSelect({
    tab: "cards",
    section: nextSection,
    cardsSubTab: "checklist",
    targetId: "set-detail-cards",
    })
    }
    variant="secondary"
    options={[
    { value: "all-cards", label: "All Cards" },
    { value: "market-movers", label: "Market Movers" },
    ]}
    />
    
    {cardsSubTab === "checklist" ? (
    <label className="block min-w-0 max-w-sm text-xs font-semibold text-[var(--text-secondary)]">
    <span className="mb-1 block uppercase tracking-[0.08em]">Search</span>
    <input
    type="text"
    value={cardSearchQuery}
    onChange={(event) => setCardSearchQuery(event.target.value)}
    placeholder="Search cards by name"
    className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
    />
    </label>
    ) : null}
    
    {cardsSubTab === "checklist" && effectiveCardsPageCards.length > 0 && hasCardMovementData ? (
    <div className="flex flex-wrap items-end gap-3">
    {cardsSection === "all-cards" ? (
    <>
    <div className="min-w-0 text-xs font-semibold text-[var(--text-secondary)]">
    <span className="mb-1 block uppercase tracking-[0.08em]">Sort</span>
    <div className="flex flex-wrap gap-2">
    <select
    aria-label="Sort cards by"
    value={cardSortMode}
    onChange={(event) => setCardSortMode(event.target.value)}
    className="min-w-[10rem] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
    >
    {ALL_CARDS_SORT_OPTIONS.map((option) => (
    <option key={option.value} value={option.value}>{option.label}</option>
    ))}
    </select>
    <button
    type="button"
    onClick={() => setCardSortDirection((direction) => direction === "asc" ? "desc" : "asc")}
    aria-label={`Sort ${ALL_CARDS_SORT_OPTIONS.find((option) => option.value === cardSortMode)?.label || "cards"} ${cardSortDirection === "asc" ? "ascending" : "descending"}. Activate to reverse order.`}
    aria-pressed={cardSortDirection === "desc"}
    className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
    >
    {getAllCardsDirectionLabel(cardSortMode, cardSortDirection)}
    </button>
    </div>
    </div>
    <label className="min-w-0 text-xs font-semibold text-[var(--text-secondary)]">
    <span className="mb-1 block uppercase tracking-[0.08em]">Rarity</span>
    <select
    value={cardRarityFilter}
    onChange={(event) => setCardRarityFilter(event.target.value)}
    className="min-w-[10rem] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
    >
    <option value="">All Rarities</option>
    {availableCardRarities.map((rarityOption) => (
    <option key={rarityOption} value={rarityOption}>{rarityOption}</option>
    ))}
    </select>
    </label>
    </>
    ) : (
    <div className="flex rounded-lg border border-[var(--border-subtle)] p-0.5" role="group" aria-label="Movement direction">
    {["gainers", "losers"].map((direction) => (
    <button
    key={direction}
    type="button"
    onClick={() => setCardSortDirection(direction)}
    aria-pressed={cardSortDirection === direction}
    aria-label={direction === "gainers" ? "Gainers" : "Losers"}
    className={`rounded-md px-3 py-1.5 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
    cardSortDirection === direction ? "bg-[var(--surface-hover)] text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
    }`}
    >
    {/* Button padding and label size are unchanged — only the
    triangle shrinks, via the shared DeltaTrendIcon's own
    "sm" size (em-relative, so it stays proportional) inside
    a fixed, identical box for both directions. The buttons'
    own aria-labels keep the icon's internal label out of the
    accessible name. Per-card movement triangles are a
    separate surface and stay as they are. */}
    <span className="inline-flex items-center gap-1.5">
    <DeltaTrendIcon
    direction={direction === "gainers" ? "up" : "down"}
    size="sm"
    className="h-3 w-3 justify-center"
    />
    <span>{direction === "gainers" ? "Gainers" : "Losers"}</span>
    </span>
    </button>
    ))}
    </div>
    )}
    <div className="flex rounded-lg border border-[var(--border-subtle)] p-0.5" role="group" aria-label="Movement timeframe">
    {CARD_TIMEFRAMES.map((timeframe) => (
    <button
    key={timeframe}
    type="button"
    onClick={() => setSelectedTimeframe(timeframe)}
    aria-pressed={selectedTimeframe === timeframe}
    className={`rounded-md px-3 py-1.5 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
    selectedTimeframe === timeframe ? "bg-[var(--surface-hover)] text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
    }`}
    >
    {timeframe}
    </button>
    ))}
    </div>
    {cardsSection === "market-movers" ? (
    // Third independent Market Movers control: which
    // magnitude the ranking compares. Direction and
    // timeframe are untouched by it. The visible labels are
    // symbol-led for compactness, so each button carries a
    // spelled-out accessible name.
    <div className="flex rounded-lg border border-[var(--border-subtle)] p-0.5" role="group" aria-label="Rank movement by">
    {MARKET_MOVER_METRIC_OPTIONS.map((option) => (
    <button
    key={option.value}
    type="button"
    onClick={() => setCardMovementMetric(option.value)}
    aria-pressed={cardMovementMetric === option.value}
    title={option.accessibleLabel}
    className={`rounded-md px-3 py-1.5 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
    cardMovementMetric === option.value ? "bg-[var(--surface-hover)] text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
    }`}
    >
    <span aria-hidden="true">{option.label}</span>
    <span className="sr-only">{option.accessibleLabel}</span>
    </button>
    ))}
    </div>
    ) : null}
    <p className="ml-auto text-xs text-[var(--text-secondary)]">
    {displayedChecklistCards.length.toLocaleString("en-US")} of {(activeCardsPageState.pagination?.totalCards ?? effectiveCardsPageCards.length).toLocaleString("en-US")} cards
    </p>
    </div>
    ) : null}
    </div>
    
    {cardsSubTab === "checklist" ? (
    <div className="min-w-0">
    {(effectiveCardsPageStatus === "idle" || effectiveCardsPageStatus === "loading") &&
    effectiveCardsPageCards.length === 0 ? (
    // Branded tab loader only while the card page
    // payload itself is loading and no card rows exist
    // yet. Once rows render, lazy card images keep
    // their card-shaped placeholders (ChecklistCardTile
    // → CardImagePlaceholder) — individual image loads
    // must never re-block the whole tab.
    <SetTabLoadingPanel
    title="Loading cards…"
    helper="Pulling the checklist page and card market fields for this set."
    />
    ) : null}
    
    {effectiveCardsPageStatus === "error" ? (
    <p className="text-sm text-red-300">{activeCardsPageState.error || "Unable to load cards for this set."}</p>
    ) : null}
    
    {effectiveCardsPageStatus === "empty" ? (
    <p className="text-sm text-[var(--text-secondary)]">No cards found for this set.</p>
    ) : null}
    
    {effectiveCardsPageCards.length > 0 ? (
    <>
    {displayedChecklistCards.length > 0 ? (
    // Never dim or overlay the grid while more
    // cards load — appended chunks render below and
    // the already-visible cards must stay stable.
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
    {displayedChecklistCards.map((card) => (
    <CardTile
    key={`${card.id || card.cardNumber || card.name}`}
    card={{ ...card, detailSetSlug: activeSetSlug }}
    movementWindow={selectedTimeframe}
    />
    ))}
    </div>
    ) : (
    <p className="text-sm text-[var(--text-secondary)]">No cards match this movement filter yet.</p>
    )}
    
    {/* Infinite scroll: the sentinel sits below the
    grid and advances cardsPage via
    IntersectionObserver (generous rootMargin) —
    no user-facing Previous/Next buttons. Located
    by data attribute because the scaffold mounts
    this tree twice (desktop + mobile copies). */}
    <div data-cards-load-more-sentinel="true" aria-hidden="true" className="h-px w-full" />
    
    {cardsPageIsLoadingMore ? (
    <div aria-live="polite" className="pt-1">
    <InDexLogoLoader
    fullScreen={false}
    label="Loading more cards"
    shouldDelay={false}
    isLoading={true}
    className="index-loader-shell--compact"
    />
    </div>
    ) : null}
    
    {cardsPageLoadMoreError ? (
    <div className="mt-3 flex flex-col items-center gap-2 text-center">
    <p className="text-xs text-[var(--text-secondary)]">Couldn&apos;t load more cards.</p>
    <button
    type="button"
    onClick={retryCardsPage}
    className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/50 px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
    >
    Retry
    </button>
    </div>
    ) : null}
    
    {cardsPageFullyLoaded && !cardsPageIsLoadingMore ? (
    <p className="mt-4 text-center text-xs text-[var(--text-secondary)]/80">
    All {(activeCardsPageState.pagination?.totalCards ?? activeCardsPageState.cards.length).toLocaleString("en-US")} cards loaded
    </p>
    ) : null}
    </>
    ) : null}
    </div>
    ) : null}
    </section>
  );
}
