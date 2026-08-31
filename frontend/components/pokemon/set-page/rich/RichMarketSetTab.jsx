"use client";

import SetMarketMobile from "@/components/pokemon/set-page/Market/SetMarketMobile";
import SectionErrorBoundary from "@/components/ui/SectionErrorBoundary";
import SevenDayMarketMoversTicker from "@/components/explore/SevenDayMarketMoversTicker";

export default function RichMarketSetTab({
  isDesktopHeroComposition,
  resolvedSetResourceId,
  activeSetSlug,
  moversTickerEntry,
  moversTickerStatus,
  activeMarketMoversState,
  moversTickerHref,
  retryMarketMoversModule,
  activeSetValueHistory,
  authoritativeSetCardCount,
  setValueTop10CurrentValue,
  setValueStandardCurrentValue,
  marketMoversByWindow,
  activeMarketDashboardDerivedState,
  topPricedCards,
  topPricedCardsStatus,
  activeTopMarketCardsState,
  topMarketCardsWindowKey,
  setTopMarketCardsWindowKey,
  marketAsOfDate,
  topChaseRowHref,
  retryTopChaseModule,
  effectiveSetValueDerivedState,
  desktopSealedSummaryState,
  desktopSealedMarketState,
  MarketOverviewSection,
  ChaseCardsPanel,
}) {
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
      cardsMarket: activeMarketDashboardDerivedState.setValue.cardsMarket,
      }}
      topChase={{
      cards: topPricedCards,
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
      <MarketOverviewSection
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
      <ChaseCardsPanel
      setId={resolvedSetResourceId}
      setSlug={activeSetSlug}
      cards={topPricedCards}
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
