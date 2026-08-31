"use client";

import { useMemo, useState } from "react";
import SetMarketMobile from "@/components/pokemon/set-page/Market/SetMarketMobile";
import SectionErrorBoundary from "@/components/ui/SectionErrorBoundary";
import SevenDayMarketMoversTicker from "@/components/explore/SevenDayMarketMoversTicker";
import useSetMarketController from "@/hooks/pokemon/useSetMarketController";
import usePokemonSetSealedMarket from "@/hooks/pokemon/usePokemonSetSealedMarket";
import usePokemonSetSealedSummary from "@/hooks/pokemon/usePokemonSetSealedSummary";
import { buildMarketDashboardStateFromPayload, createMarketDashboardState } from "@/components/explore/marketDashboardState.mjs";
import { selectMoversTickerItems } from "@/components/explore/moversTickerSelector.mjs";
import { getMarketDateSourceFromPayload, resolveMarketAsOfDate } from "@/components/explore/marketAsOfDate.mjs";
import RichMarketOverviewSection from "./market/RichMarketOverviewSection";
import RichTopChaseCardsPanel from "./market/RichTopChaseCardsPanel";

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function getCardMarketPrice(card) {
  const price =
    toNumber(card?.marketPrice) ?? toNumber(card?.market_price) ??
    toNumber(card?.currentPrice) ?? toNumber(card?.current_price) ??
    toNumber(card?.price) ?? toNumber(card?.estimatedMarketPrice) ??
    toNumber(card?.estimated_market_price) ?? toNumber(card?.current_near_mint_price) ??
    toNumber(card?.currentNearMintPrice) ?? toNumber(card?.price_used) ??
    toNumber(card?.priceUsed) ?? toNumber(card?.card_price) ??
    toNumber(card?.cardPrice) ?? toNumber(card?.card_market_price) ??
    toNumber(card?.cardMarketPrice) ?? toNumber(card?.tcgplayer?.prices?.holofoil?.market) ??
    toNumber(card?.tcgplayer?.prices?.reverseHolofoil?.market) ??
    toNumber(card?.tcgplayer?.prices?.normal?.market) ??
    toNumber(card?.cardmarket?.prices?.averageSellPrice);
  return price !== null && price > 0 ? price : null;
}

function normalizeTopPricedCard(card) {
  if (!card || typeof card !== "object") return null;
  const marketPrice = getCardMarketPrice(card);
  if (marketPrice === null) return null;
  const setNumber = card?.setNumber ?? card?.set_number ?? card?.cardNumber ?? card?.card_number ?? card?.printedNumber ?? card?.printed_number ?? card?.number ?? null;
  const priceHistory = Array.isArray(card?.priceHistory) ? card.priceHistory : Array.isArray(card?.price_history) ? card.price_history : [];
  return {
    id: card?.id ?? card?.cardId ?? card?.card_id ?? card?.pokemonTcgApiCardId ?? card?.pokemon_tcg_api_card_id ?? null,
    cardId: card?.cardId ?? card?.card_id ?? card?.id ?? null,
    cardVariantId: card?.cardVariantId ?? card?.card_variant_id ?? null,
    name: card?.name ?? card?.cardName ?? card?.card_name ?? "Unknown card",
    imageUrl: card?.imageUrl ?? card?.image_url ?? card?.imageSmallUrl ?? card?.image_small_url ?? card?.imageLargeUrl ?? card?.image_large_url ?? null,
    imageSmallUrl: card?.imageSmallUrl ?? card?.image_small_url ?? null,
    imageLargeUrl: card?.imageLargeUrl ?? card?.image_large_url ?? null,
    rarity: card?.rarity ?? null,
    setNumber,
    cardNumber: card?.cardNumber ?? card?.card_number ?? setNumber,
    marketPrice,
    estimatedMarketPrice: toNumber(card?.estimatedMarketPrice ?? card?.estimated_market_price),
    priceUsed: toNumber(card?.priceUsed ?? card?.price_used),
    priceHistory,
    price_history: priceHistory,
    historyPointCount: toNumber(card?.historyPointCount ?? card?.history_point_count),
    historyStartDate: card?.historyStartDate ?? card?.history_start_date ?? null,
    historyEndDate: card?.historyEndDate ?? card?.history_end_date ?? null,
    conditionIdUsed: card?.conditionIdUsed ?? card?.condition_id_used ?? null,
    matchingConditionObservationCount: toNumber(card?.matchingConditionObservationCount ?? card?.matching_condition_observation_count),
    historyDiagnostics: card?.historyDiagnostics && typeof card.historyDiagnostics === "object" ? card.historyDiagnostics : card?.history_diagnostics && typeof card.history_diagnostics === "object" ? card.history_diagnostics : null,
    deltas: card?.deltas && typeof card.deltas === "object" ? card.deltas : null,
    source: "topMarketCards",
  };
}

export default function RichMarketSetTab({
  isDesktopHeroComposition,
  resolvedSetResourceId,
  activeSetSlug,
  canFetch,
  destinationSeedPending,
  overviewSeed,
  moversSeed,
  topChaseSeed,
  moversTickerHref,
  authoritativeSetCardCount,
  topChaseRowHref,
}) {
  const { activeOverviewState, activeMarketMoversState, activeTopChaseState, retryMarketMovers: retryMarketMoversModule, retryTopChase: retryTopChaseModule } = useSetMarketController({
    setId: resolvedSetResourceId, enabled: true, canFetch, destinationSeedPending,
    overviewSeed, moversSeed, topChaseSeed,
  });
  const effectiveSetValueDerivedState = useMemo(() => buildMarketDashboardStateFromPayload(activeOverviewState.payload || overviewSeed), [activeOverviewState.payload, overviewSeed]);
  const setValue = effectiveSetValueDerivedState.setValue;
  const activeSetValueHistory = { status: activeOverviewState.status, history: setValue.history || [], historiesByScope: setValue.historiesByScope || {}, error: activeOverviewState.error };
  const marketMoversByWindow = activeMarketMoversState.payload?.marketMoversByWindow || null;
  const moversTickerEntry = activeMarketMoversState.payload || moversSeed || null;
  const moversTickerItems = useMemo(() => selectMoversTickerItems(moversTickerEntry), [moversTickerEntry]);
  const moversTickerStatus = moversTickerItems.length ? "success" : ["idle", "loading"].includes(activeMarketMoversState.status) ? "loading" : activeMarketMoversState.status === "error" ? "error" : "empty";
  const topPricedCards = useMemo(() => (activeTopChaseState.payload?.cards || [])
    .map(normalizeTopPricedCard)
    .filter(Boolean)
    .sort((a, b) => b.marketPrice - a.marketPrice)
    .slice(0, 10), [activeTopChaseState.payload?.cards]);
  // Desktop's approved Top 10 derives row movement from the rendered history
  // series; mobile's approved model consumes the compact endpoint windows.
  const desktopTopPricedCards = useMemo(
    () => topPricedCards.map((card) => ({ ...card, deltas: null })),
    [topPricedCards]
  );
  const topPricedCardsStatus = topPricedCards.length ? "success" : ["idle", "loading"].includes(activeTopChaseState.status) ? "loading" : activeTopChaseState.status;
  const activeTopMarketCardsState = { ...createMarketDashboardState({ setId: resolvedSetResourceId }), ...activeTopChaseState, cards: topPricedCards };
  const [topMarketCardsWindowKey, setTopMarketCardsWindowKey] = useState("7D");
  const marketAsOfDate = useMemo(() => resolveMarketAsOfDate([
    getMarketDateSourceFromPayload("overview", activeOverviewState.payload || null),
    getMarketDateSourceFromPayload("topChase", activeTopChaseState.payload || null),
    getMarketDateSourceFromPayload("marketMovers", moversTickerEntry),
  ]).marketAsOfDate, [activeOverviewState.payload, activeTopChaseState.payload, moversTickerEntry]);
  const latestValue = (points) => { for (let index = (points || []).length - 1; index >= 0; index -= 1) { const value = Number(points[index]?.setValue ?? points[index]?.set_value ?? points[index]?.value); if (Number.isFinite(value)) return value; } return null; };
  const setValueTop10CurrentValue = latestValue(activeSetValueHistory.historiesByScope.top10) ?? overviewSeed?.chaseConcentration?.top10?.setValue ?? null;
  const setValueStandardCurrentValue = latestValue(activeSetValueHistory.historiesByScope.standard || activeSetValueHistory.history) ?? overviewSeed?.chaseConcentration?.standard?.setValue ?? null;
  const desktopSealedSummaryState = usePokemonSetSealedSummary(isDesktopHeroComposition ? resolvedSetResourceId : null, { enabled: isDesktopHeroComposition });
  const desktopSealedMarketState = usePokemonSetSealedMarket(isDesktopHeroComposition ? resolvedSetResourceId : null, { enabled: false });
  const setDetailTab = "market";
  return (
    <>
      {setDetailTab === "market" ? (
      isDesktopHeroComposition ? null : (
      <SetMarketMobile
      setId={resolvedSetResourceId}
      setSlug={activeSetSlug}
      sectionIds={{
      root: "set-detail-market",
      movers: "set-detail-market-movers",
      setValue: "set-detail-market-set-value",
      topChase: "set-detail-market-top-chase",
      sealed: "set-detail-market-sealed",
      }}
      movers={{
      entry: moversTickerEntry,
      status: moversTickerStatus,
      error: activeMarketMoversState.error,
      viewAllHref: moversTickerHref,
      onRetry: retryMarketMoversModule,
      }}
      setValue={{
      history: activeSetValueHistory.history,
      historiesByScope: activeSetValueHistory.historiesByScope,
      status: activeSetValueHistory.status,
      error: activeSetValueHistory.error,
      cardsTrackedCount: authoritativeSetCardCount,
      top10Value: setValueTop10CurrentValue,
      standardValue: setValueStandardCurrentValue,
      moversByWindow: marketMoversByWindow,
      cardsMarket: effectiveSetValueDerivedState.setValue.cardsMarket,
      }}
      topChase={{
      cards: desktopTopPricedCards,
      status: topPricedCardsStatus,
      error: activeTopMarketCardsState.error,
      selectedWindowKey: topMarketCardsWindowKey,
      onWindowChange: setTopMarketCardsWindowKey,
      marketAsOfDate,
      viewAllHref: topChaseRowHref,
      onRetry: retryTopChaseModule,
      }}
      />
      )
      ) : null}
      
      {setDetailTab === "market" && isDesktopHeroComposition ? (
      <section id="set-detail-market" data-market-page className="scroll-mt-24 space-y-5 md:scroll-mt-28">
      {/* SECTION 1 — 7D Movers, directly under the set header.
      Fixed 7D, independent of every other selector on the
      page, and the ONLY movers strip on this tab. */}
      <div id="set-detail-market-movers" data-market-section="movers" data-mobile-section className="min-w-0 scroll-mt-24 md:scroll-mt-28">
      <SectionErrorBoundary sectionName="market-movers-ticker" resetKeys={[resolvedSetResourceId]} title="7D Movers" minHeightClassName="min-h-[3rem]">
      <SevenDayMarketMoversTicker
      entry={moversTickerEntry}
      maxItems={10}
      scope="set"
      status={moversTickerStatus}
      error={activeMarketMoversState.error}
      viewAllHref={moversTickerHref}
      onRetry={retryMarketMoversModule}
      />
      </SectionErrorBoundary>
      </div>
      
      {/* SECTION 2 — Main Market Overview. The dominant analytics
      surface: Market Value Trend on the left, Set Signals on
      the right. The retired Set Value and Sealed Market cards
      are folded in here as the Cards and Sealed lenses, which
      is why #set-detail-market-sealed now resolves to this
      section rather than to a card of its own. */}
      <div
      id="set-detail-market-set-value"
      data-market-section="overview"
      data-mobile-section
      className="min-w-0 scroll-mt-24 md:scroll-mt-28"
      >
      <span id="set-detail-market-sealed" aria-hidden="true" className="block scroll-mt-24 md:scroll-mt-28" />
      <SectionErrorBoundary sectionName="market-overview" resetKeys={[resolvedSetResourceId]} title="Market Value Trend" minHeightClassName="min-h-[28rem]">
      <RichMarketOverviewSection
      setId={resolvedSetResourceId}
      cardsHistory={activeSetValueHistory.historiesByScope?.standard || activeSetValueHistory.history}
      // THE LIVE SOURCE. `activeMarketDashboardDerivedState` is
      // built from the retired monolithic /market/dashboard
      // fetch, which nothing on this page calls live any more
      // (Top Chase Cards and Market Movers moved to their own
      // slim endpoints — see the effect above) — so this prop
      // was permanently null except from a stale cache entry
      // or an SSR seed that never carries it either.
      // `effectiveSetValueDerivedState` is the payload the
      // Market tab actually fetches (the slim /overview
      // endpoint), which now also serves cardsMarket.
      cardsMarket={effectiveSetValueDerivedState.setValue.cardsMarket}
      cardsTrackedCount={authoritativeSetCardCount}
      top10Value={setValueTop10CurrentValue}
      standardValue={setValueStandardCurrentValue}
      sealedSummaryState={desktopSealedSummaryState}
      />
      </SectionErrorBoundary>
      </div>
      
      {/* SECTION 3 — Top 10 Chase Cards. A dedicated module, not
      part of Section 2's card. */}
      <div id="set-detail-market-top-chase" data-market-section="top-chase" data-mobile-section className="min-w-0 scroll-mt-24 md:scroll-mt-28">
      <SectionErrorBoundary sectionName="market-top-chase" resetKeys={[resolvedSetResourceId]} title="Top 10 Chase Cards" minHeightClassName="min-h-[24rem]">
      <RichTopChaseCardsPanel
      setId={resolvedSetResourceId}
      setSlug={activeSetSlug}
      cards={desktopTopPricedCards}
      status={topPricedCardsStatus}
      error={activeTopMarketCardsState.error}
      selectedWindowKey={topMarketCardsWindowKey}
      onWindowChange={setTopMarketCardsWindowKey}
      marketAsOfDate={marketAsOfDate}
      onRetry={retryTopChaseModule}
      sealedState={desktopSealedMarketState}
      />
      </SectionErrorBoundary>
      </div>
      </section>
      ) : null}
      
      
    </>
  );
}
