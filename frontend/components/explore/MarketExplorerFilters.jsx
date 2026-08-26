"use client";

import { useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import ExplorerDisclosure from "./ExplorerDisclosure";
import ExplorerMarketOption from "./ExplorerMarketOption";
import ExplorerPlanLockPanel from "./ExplorerPlanLockPanel";
import MarketExplorerEraSets from "./MarketExplorerEraSets";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import { MARKET_EXPLORER_FILTER_AXES } from "@/lib/explore/marketExplorerState.mjs";
import {
  ASSET_MARKET_INFO,
  BENCHMARKS_INFO,
  ERA_SETS_INFO,
  buildCardRaritiesInfo,
  buildSealedFamiliesInfo,
} from "@/lib/explore/marketExplorerDisclosureCopy.mjs";
import { describeScope } from "@/lib/explore/marketExplorerScope.mjs";

// ---------------------------------------------------------------------------
// EXPLORE SEGMENTS — the fast lane.
//
// One purpose: put an already-prepared market on the chart, immediately. Click
// SIR and SIR appears; click it again and it is gone. No builder step, no "Add
// to comparison", and — deliberately — NO automatic parent line. A selection
// means exactly what was clicked. (Build a Market, the advanced lane, is
// different and still supplies a same-filter benchmark; that distinction is
// documented at toggleSealedFamilyId.)
//
// EVERY ROW IS THE SAME COMPONENT. Asset Market, Card Rarities, Sealed Families
// and Benchmarks all render ExplorerMarketOption, so the selected state is
// designed once and the rail stops looking like four different products. Green
// is interaction; the small square beside the label is series identity. Those
// two vocabularies never swap.
//
// INFORMATION DENSITY IS THE OTHER HALF OF THE JOB. Everything except the three
// asset classes is collapsed on first load, so the opening rail is one short
// list plus four headers rather than twenty-five checkboxes and two paragraphs
// of methodology. The methodology did not go away — it moved into each group's
// ⓘ, where it is one click from the control it describes.
//
// PLAN ACCESS. Asset Market is open to everyone. The four groups below it are
// Index Plus. A basic visitor SEES those headers — the point is to show that
// depth exists — but opening one reveals a lock panel, never the gated rows in
// a disabled state, which would leak the published taxonomy the gate exists to
// sell. Nothing here is security; the server decides what it will serve.
//
// NO OPTION IS HARDCODED HERE. Every rarity, family, era and set is whatever
// the backend published; a segment the backend cannot build never appears.
// ---------------------------------------------------------------------------

/** Why a group is locked, in the group's own terms. */
const PLUS_LOCK_COPY = {
  cardRarities: "Compare Special Illustration Rare, Illustration Rare, Ultra Rare and the other published rarity markets against each other and against the Raw Card Market.",
  sealedFamilies: "Compare Booster Boxes, Elite Trainer Boxes, Pokémon Center ETBs, Booster Bundles and Packs as separate markets.",
  eraSets: "Browse the canonical Era and Set hierarchy to scope your research.",
  benchmarks: "Chart the Per-Set Chase Market and the other prepared benchmark markets.",
};

function OptionList({ entries, onToggle, isLocked }) {
  return (
    <ul className="mt-1 space-y-1">
      {entries.map((entry) => (
        <li key={entry.key}>
          <ExplorerMarketOption
            entry={entry}
            onToggle={onToggle}
            isLocked={isLocked(entry)}
            // The chart may never be emptied, so the final remaining series is
            // held. Said out loud rather than left as a dead checkbox.
            lockReason={isLocked(entry) ? "Only market" : null}
          />
        </li>
      ))}
    </ul>
  );
}

export default function MarketExplorerFilters({
  assetEntries = [],
  benchmarkEntries = [],
  sealedEntries = [],
  cardGroups = [],
  reconciliation = null,
  cardReconciliation = null,
  topChaseSegmentStatus = null,
  eraTree = [],
  eraScope = { eraIds: [], setIds: [] },
  eraOptionsStatus = "loading",
  onToggleMarket,
  onToggleSealedFamily,
  onToggleCardSegment,
  onToggleScopeEra,
  onToggleScopeSet,
  onClearScope,
  onUseScopeInBuilder,
  selectedSeriesCount = 0,
  // Presentation gate. Defaults OPEN so a caller that forgets to pass access
  // cannot accidentally hide published markets; the server-side gate is what
  // actually protects anything.
  canUsePreparedMarketIntelligence = true,
  isAuthenticated = false,
  currentPlan = null,
}) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const axisById = new Map(MARKET_EXPLORER_FILTER_AXES.map((axis) => [axis.id, axis]));
  const hasSealed = sealedEntries.length > 0;
  const hasCards = cardGroups.some((group) => group.entries.length > 0);
  // The chart may never be emptied by selection, so the final remaining series
  // is locked wherever it appears.
  const isLocked = (entry) => entry.selected === true && selectedSeriesCount <= 1;
  const selectedCount = (entries) => entries.filter((entry) => entry.selected === true).length;
  const countSummary = (count) => (count > 0 ? `${count} selected` : null);
  const cardSelected = cardGroups.reduce((total, group) => total + selectedCount(group.entries), 0);
  const scopeSummary = describeScope(eraScope, eraTree);
  const locked = !canUsePreparedMarketIntelligence;

  const planLock = (groupId) => (
    <ExplorerPlanLockPanel
      requiredPlan={INDEX_PLAN_PLUS}
      isAuthenticated={isAuthenticated}
      currentPlan={currentPlan}
      description={PLUS_LOCK_COPY[groupId]}
    />
  );

  // A locked group shows the lock badge instead of a selection count: a basic
  // visitor has no selections, and an "Unavailable" badge would misdescribe a
  // market that is published and simply not theirs yet.
  const groupBadge = (unlockedBadge) => (locked ? "🔒" : unlockedBadge);
  const groupSummary = (unlockedSummary) => (locked ? "Index Plus" : unlockedSummary);

  const body = (
    <div className="space-y-2 px-3 pb-4 sm:px-4">
      {/* ALWAYS VISIBLE, ALWAYS OPEN TO EVERYONE. The asset classes are the
          page's premise and the whole of basic access. */}
      <fieldset data-market-explorer-filter-axis="assetMarket" data-market-explorer-filter-available="true" className="min-w-0">
        <div className="flex items-center gap-1.5">
          <legend className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            {axisById.get("assetMarket").label}
          </legend>
          <InfoPopover text={ASSET_MARKET_INFO} />
        </div>
        <OptionList entries={assetEntries} onToggle={onToggleMarket} isLocked={isLocked} />
      </fieldset>

      <ExplorerDisclosure
        id="cardRarities"
        title="Card Rarities"
        info={buildCardRaritiesInfo(cardReconciliation, topChaseSegmentStatus)}
        badge={groupBadge(hasCards ? null : "Unavailable")}
        summary={groupSummary(countSummary(cardSelected))}
      >
        {locked ? planLock("cardRarities") : hasCards ? (
          <div data-market-explorer-filter-axis="cardSegment" data-market-explorer-filter-available="true">
            {cardGroups.map((group) => (
              <div key={group.parentMarket} data-market-explorer-filter-group={group.parentMarket} className="mt-1.5">
                <p className="text-[10px] font-medium text-[var(--text-secondary)]">{group.label}</p>
                <OptionList entries={group.entries} onToggle={onToggleCardSegment} isLocked={isLocked} />
              </div>
            ))}
          </div>
        ) : (
          <p data-market-explorer-filter-axis="cardSegment" data-market-explorer-filter-available="false" className="mt-1 text-[11px] text-[var(--text-secondary)]">
            No card rarity submarkets are published in this snapshot.
          </p>
        )}
      </ExplorerDisclosure>

      <ExplorerDisclosure
        id="sealedFamilies"
        title="Sealed Product Families"
        info={buildSealedFamiliesInfo(reconciliation)}
        badge={groupBadge(hasSealed ? null : "Unavailable")}
        summary={groupSummary(countSummary(selectedCount(sealedEntries)))}
      >
        {locked ? planLock("sealedFamilies") : hasSealed ? (
          <div data-market-explorer-filter-axis="sealedFamily" data-market-explorer-filter-available="true">
            <OptionList entries={sealedEntries} onToggle={onToggleSealedFamily} isLocked={isLocked} />
          </div>
        ) : (
          <p data-market-explorer-filter-axis="sealedFamily" data-market-explorer-filter-available="false" className="mt-1 text-[11px] text-[var(--text-secondary)]">
            No sealed product-family submarkets are published in this snapshot.
          </p>
        )}
      </ExplorerDisclosure>

      <ExplorerDisclosure
        id="eraSets"
        title={axisById.get("era").label}
        info={ERA_SETS_INFO}
        badge={groupBadge(null)}
        summary={groupSummary(scopeSummary || null)}
      >
        {locked ? planLock("eraSets") : (
          <div data-market-explorer-filter-axis="era" data-market-explorer-filter-available="true">
            <MarketExplorerEraSets
              tree={eraTree}
              scope={eraScope}
              status={eraOptionsStatus}
              onToggleEra={onToggleScopeEra}
              onToggleSet={onToggleScopeSet}
              onClear={onClearScope}
              onUseInBuilder={onUseScopeInBuilder}
            />
          </div>
        )}
      </ExplorerDisclosure>

      <ExplorerDisclosure
        id="benchmarks"
        title="Benchmarks"
        info={BENCHMARKS_INFO}
        badge={groupBadge(null)}
        summary={groupSummary(countSummary(selectedCount(benchmarkEntries)))}
      >
        {locked ? planLock("benchmarks") : (
          <div data-market-explorer-filter-axis="benchmark" data-market-explorer-filter-available="true">
            {benchmarkEntries.length ? (
              <OptionList entries={benchmarkEntries} onToggle={onToggleMarket} isLocked={isLocked} />
            ) : (
              <p className="mt-1 text-[11px] text-[var(--text-secondary)]">No benchmark markets are published in this snapshot.</p>
            )}
          </div>
        )}
      </ExplorerDisclosure>
    </div>
  );

  return (
    <section
      data-market-explorer-filters
      data-market-explorer-filters-plan-locked={locked ? "true" : "false"}
      className="flex min-w-0 flex-col"
      aria-labelledby="market-explorer-filters-heading"
    >
      <div className="px-3 py-3 sm:px-4">
        <div className="flex items-center gap-2">
          <h2 id="market-explorer-filters-heading" className="text-[16px] font-semibold text-[var(--text-primary)]">
            Explore Segments
          </h2>
          {/* Mobile keeps the workspace compact: the rail collapses so the
              chart above it is not pushed off-screen. */}
          <button
            type="button"
            data-market-explorer-filters-toggle
            aria-expanded={isMobileOpen}
            aria-controls="market-explorer-filters-body"
            onClick={() => setIsMobileOpen((current) => !current)}
            className="ml-auto rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] desk:hidden"
          >
            {isMobileOpen ? "Hide" : "Segments"}
          </button>
        </div>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          {locked
            ? "Add Raw Card and Sealed markets to the chart. Deeper segments are available with Index Plus."
            : "Add prepared market segments to the chart."}
        </p>
      </div>
      <div id="market-explorer-filters-body" className={isMobileOpen ? "" : "hidden desk:block"}>
        {body}
      </div>
    </section>
  );
}
