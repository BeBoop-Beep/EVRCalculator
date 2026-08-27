"use client";

import React from "react";

import SectionErrorBoundary from "@/components/ui/SectionErrorBoundary";
import SetMarketMobileMovers from "./SetMarketMobileMovers.jsx";
import SetMarketMobileSetValue from "./SetMarketMobileSetValue.jsx";
import SetMarketMobileTopChase from "./SetMarketMobileTopChase.jsx";
import usePokemonSetSealedMarket from "@/hooks/pokemon/usePokemonSetSealedMarket";

// ---------------------------------------------------------------------------
// The mobile Set Market tab.
//
// This is the phone expression of the desktop Market composition, NOT a
// narrowed copy of it. Same tab, same routing, same section semantics — but
// the reading order is re-cut for a thumb:
//
//   1. 7D Market Movers  what changed this week? (the headline)
//   2. Market Snapshot   what is the set worth, in which lens, and how has
//                        it moved? (Cards | Sealed | Graded)
//   3. Top Chase Cards   what carries that value?
//
// There is deliberately NO set-identity hero card here. The primary mobile
// set header (logo, name, era) already renders once, above the tab
// navigation, before any tab's content mounts — repeating it as the first
// card inside Market told the reader which set they were looking at twice
// before they reached anything new. Movers leads Market's own content
// because on a phone the first screenful has to answer "is anything
// happening?" before it can afford a chart.
//
// NO STANDALONE SEALED MODULE. A dedicated Sealed Market section (product
// chips, its own chart, its own metrics) used to sit below Top Chase. It is
// gone by design: Market Snapshot's Sealed lens already answers "what is
// unopened product worth right now", and stacking a second, larger sealed
// module under Top Chase was redundant coverage that only added scroll
// length. The deep-link id is preserved as an inert anchor on Market
// Snapshot — the section that now actually answers what that link promised —
// rather than pointing at nothing.
//
// The section ids are the SAME ids the desktop composition uses, so every
// existing `?section=` deep link resolves at both widths. Only one of the two
// compositions is ever mounted (the page picks by width), so the ids stay
// unique in the document.
//
// Each section owns its own controls. There is deliberately no page-level
// master timeframe: Market Snapshot and Top Chase publish different
// supported windows, and one toggle governing both would spend part of its
// life offering options one of them ignores.
// ---------------------------------------------------------------------------

export default function SetMarketMobile({
  setId,
  sectionIds,
  movers,
  setValue,
  topChase,
}) {
  const sealedState = usePokemonSetSealedMarket(setId);

  return (
    <section id={sectionIds.root} data-market-page data-market-mobile className="min-w-0 space-y-3">
      <SectionErrorBoundary sectionName="market-mobile-movers" resetKeys={[setId]} title="7D Market Movers" minHeightClassName="min-h-[10rem]">
        <SetMarketMobileMovers id={sectionIds.movers} {...movers} />
      </SectionErrorBoundary>

      <SectionErrorBoundary sectionName="market-mobile-set-value" resetKeys={[setId]} title="Market Snapshot" minHeightClassName="min-h-[16rem]">
        <span id={sectionIds.sealed} aria-hidden="true" className="block" />
        <SetMarketMobileSetValue id={sectionIds.setValue} setId={setId} sealedState={sealedState} {...setValue} />
      </SectionErrorBoundary>

      <SectionErrorBoundary sectionName="market-mobile-top-chase" resetKeys={[setId]} title="Top Chase Cards" minHeightClassName="min-h-[14rem]">
        <SetMarketMobileTopChase id={sectionIds.topChase} setId={setId} sealedState={sealedState} {...topChase} />
      </SectionErrorBoundary>
    </section>
  );
}
