"use client";

import { useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import ExplorerDisclosure from "./ExplorerDisclosure";
import MarketExplorerEraSets from "./MarketExplorerEraSets";
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
// INFORMATION DENSITY IS THE OTHER HALF OF THE JOB. Everything except the three
// asset classes is collapsed on first load, so the opening rail is one short
// list plus four headers rather than twenty-five checkboxes and two paragraphs
// of methodology. The methodology did not go away — it moved into each group's
// ⓘ, where it is one click from the control it describes instead of standing
// between the controls.
//
// NO OPTION IS HARDCODED HERE. Every rarity, family, era and set is whatever
// the backend published; a segment the backend cannot build never appears.
// ---------------------------------------------------------------------------
function SegmentOption({ entry, onToggle, isLocked }) {
  const disabled = entry.available !== true || isLocked;
  return (
    <label
      data-market-explorer-filter-option={entry.key}
      data-market-explorer-filter-option-available={entry.available === true ? "true" : "false"}
      className={[
        "flex items-center gap-2 text-xs",
        entry.available === true ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]",
        disabled ? "cursor-default" : "cursor-pointer",
      ].join(" ")}
    >
      <input
        type="checkbox"
        checked={entry.selected === true}
        disabled={disabled}
        onChange={() => onToggle?.(entry.key)}
        className="h-3.5 w-3.5 flex-none rounded-[3px] border-[var(--border-subtle)] bg-transparent accent-[var(--accent)] disabled:opacity-40"
      />
      <span aria-hidden="true" className="inline-block h-2.5 w-2.5 flex-none rounded-[3px]" style={{ backgroundColor: entry.color }} />
      <span className="min-w-0 truncate">{entry.shortLabel || entry.label}</span>
      {entry.available === true
        ? (entry.definition ? <InfoPopover text={entry.definition} /> : null)
        : (
          // Never a bare disabled checkbox: an option the user can see but
          // cannot select has to say why, in the snapshot's own words.
          <span className="ml-auto flex items-center gap-1 flex-none text-[10px] text-[var(--text-secondary)]">
            Unavailable
            {entry.unavailableReason ? <InfoPopover text={entry.unavailableReason} /> : null}
          </span>
        )}
    </label>
  );
}

function OptionList({ entries, onToggle, isLocked }) {
  return (
    <ul className="mt-1 space-y-1.5">
      {entries.map((entry) => (
        <li key={entry.key}>
          <SegmentOption entry={entry} onToggle={onToggle} isLocked={isLocked(entry)} />
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

  const body = (
    <div className="space-y-2 px-3 pb-4 sm:px-4">
      {/* ALWAYS VISIBLE. The three asset classes are the page's premise. */}
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
        badge={hasCards ? null : "Unavailable"}
        summary={countSummary(cardSelected)}
      >
        {hasCards ? (
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
        badge={hasSealed ? null : "Unavailable"}
        summary={countSummary(selectedCount(sealedEntries))}
      >
        {hasSealed ? (
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
        summary={scopeSummary || null}
      >
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
      </ExplorerDisclosure>

      <ExplorerDisclosure
        id="benchmarks"
        title="Benchmarks"
        info={BENCHMARKS_INFO}
        summary={countSummary(selectedCount(benchmarkEntries))}
      >
        <div data-market-explorer-filter-axis="benchmark" data-market-explorer-filter-available="true">
          {benchmarkEntries.length ? (
            <OptionList entries={benchmarkEntries} onToggle={onToggleMarket} isLocked={isLocked} />
          ) : (
            <p className="mt-1 text-[11px] text-[var(--text-secondary)]">No benchmark markets are published in this snapshot.</p>
          )}
        </div>
      </ExplorerDisclosure>
    </div>
  );

  return (
    <section data-market-explorer-filters className="flex min-w-0 flex-col" aria-labelledby="market-explorer-filters-heading">
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
            className="ml-auto rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65 desk:hidden"
          >
            {isMobileOpen ? "Hide" : "Segments"}
          </button>
        </div>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          Add prepared market segments to the chart.
        </p>
      </div>
      <div id="market-explorer-filters-body" className={isMobileOpen ? "" : "hidden desk:block"}>
        {body}
      </div>
    </section>
  );
}
