"use client";

import React from "react";

import SectionErrorBoundary from "@/components/ui/SectionErrorBoundary";
import SetMarketMobileMovers from "./SetMarketMobileMovers.jsx";
import SetMarketMobileSetValue from "./SetMarketMobileSetValue.jsx";
import SetMarketMobileTopChase from "./SetMarketMobileTopChase.jsx";
import SetMarketMobileSealed from "./SetMarketMobileSealed.jsx";

// ---------------------------------------------------------------------------
// The mobile Set Market tab.
//
// This is the phone expression of the desktop Market composition, NOT a
// narrowed copy of it. Same tab, same routing, same four data owners, same
// section semantics — but the reading order is re-cut for a thumb:
//
//   1. 7D Market Movers  what changed this week? (the headline)
//   2. Set Value         what is the set worth, and how has it moved?
//   3. Top Chase Cards   what carries that value?
//   4. Sealed Market     what does unopened product cost?
//
// There is deliberately NO set-identity hero card here. The primary mobile
// set header (logo, name, era) already renders once, above the tab
// navigation, before any tab's content mounts — repeating it as the first
// card inside Market told the reader which set they were looking at twice
// before they reached anything new. Movers leads Market's own content
// because on a phone the first screenful has to answer "is anything
// happening?" before it can afford a chart.
//
// The section ids are the SAME ids the desktop composition uses, so every
// existing `?section=` deep link resolves at both widths. Only one of the two
// compositions is ever mounted (the page picks by width), so the ids stay
// unique in the document.
//
// Each section owns its own controls. There is deliberately no page-level
// master timeframe: Set Value, Top Chase and each sealed product publish
// different supported windows, and one toggle governing all three would spend
// most of its life offering options two of them ignore.
// ---------------------------------------------------------------------------

export default function SetMarketMobile({
  setId,
  sectionIds,
  movers,
  setValue,
  topChase,
  sealed,
}) {
  return (
    <section id={sectionIds.root} data-market-page data-market-mobile className="min-w-0 space-y-3">
      <SectionErrorBoundary sectionName="market-mobile-movers" resetKeys={[setId]} title="7D Market Movers" minHeightClassName="min-h-[10rem]">
        <SetMarketMobileMovers id={sectionIds.movers} {...movers} />
      </SectionErrorBoundary>

      <SectionErrorBoundary sectionName="market-mobile-set-value" resetKeys={[setId]} title="Set Value" minHeightClassName="min-h-[16rem]">
        <SetMarketMobileSetValue id={sectionIds.setValue} setId={setId} {...setValue} />
      </SectionErrorBoundary>

      <SectionErrorBoundary sectionName="market-mobile-top-chase" resetKeys={[setId]} title="Top Chase Cards" minHeightClassName="min-h-[14rem]">
        <SetMarketMobileTopChase id={sectionIds.topChase} {...topChase} />
      </SectionErrorBoundary>

      <SectionErrorBoundary sectionName="market-mobile-sealed" resetKeys={[setId]} title="Sealed Market" minHeightClassName="min-h-[11rem]">
        <SetMarketMobileSealed id={sectionIds.sealed} setId={setId} {...sealed} />
      </SectionErrorBoundary>
    </section>
  );
}
