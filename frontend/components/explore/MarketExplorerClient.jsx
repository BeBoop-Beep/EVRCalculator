"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import MarketExplorerChart from "./MarketExplorerChart";
import MarketExplorerDetails from "./MarketExplorerDetails";
import MarketExplorerFilters from "./MarketExplorerFilters";
import MarketExplorerSeriesCard from "./MarketExplorerSeriesCard";
import MarketExplorerQueryBuilder from "./MarketExplorerQueryBuilder";
import MarketExplorerDynamicSeries from "./MarketExplorerDynamicSeries";
import {
  buildAssetUniverseModel,
  buildCardSegmentModel,
  buildExplorerTimeframeOptions,
  buildSealedFamilyModel,
  reconcileAssetUniverse,
  reconcileCardSegmentIds,
  reconcileSealedFamilyIds,
  resolveAvailableAssetKeys,
  resolveAvailableCardSegmentIds,
  resolveAvailableSealedFamilyIds,
  resolveExplorerTimeframe,
  resolveSelectedSeriesIds,
  toggleAssetUniverseKey,
  toggleCardSegmentId,
  toggleSealedFamilyId,
} from "@/lib/explore/marketExplorerState.mjs";
import {
  buildComparableSeries,
  isCardSegmentSeriesId,
  isSealedSegmentSeriesId,
} from "@/lib/explore/marketExplorerSeries.mjs";
import styles from "./explore.module.css";
import useMarketExplorerQueries from "@/hooks/explore/useMarketExplorerQueries";

// ---------------------------------------------------------------------------
// Market Explorer — the research workspace.
//
// ONE state owner, so the selector cards, the filter checkboxes, the chart, the
// legend and the detail table can never disagree about which series are on
// screen or over which window. That is the whole reason this is a client
// boundary; it owns NO market data of its own.
//
// The state is shaped as the filter model (assetUniverse, sealedFamilyIds,
// segmentIds, eraIds, timeframe). Three axes are live; Era is declared so a
// later phase populates a field rather than re-plumbing the components.
// ---------------------------------------------------------------------------
const HELP_TRACKED_VALUE = "Tracked Value is the current dollar value of the tracked basket. It moves both because prices move and because constituents enter or leave the tracked universe.";
const HELP_INDEX = "Market Index measures price performance from a base of 100 while neutralizing constituent additions and removals. An index of 106.18 means that market is 6.18% above its own index base — not that every card or product in it rose 6.18%.";
const HELP_WINDOWS = "Since Tracking is measured from each market's own tracking start, so it is not comparable across markets. The timeframe control — including All, the common comparable start — measures every selected market over one shared span.";

export default function MarketExplorerClient({
  overview,
  sealedSegments = [],
  cardSegments = [],
  reconciliation = null,
  cardReconciliation = null,
  topChaseSegmentStatus = null,
  initialState,
}) {
  const availableKeys = useMemo(() => resolveAvailableAssetKeys(overview), [overview]);
  const availableSealedIds = useMemo(
    () => resolveAvailableSealedFamilyIds(sealedSegments),
    [sealedSegments]
  );
  const availableCardIds = useMemo(
    () => resolveAvailableCardSegmentIds(cardSegments),
    [cardSegments]
  );
  const timeframeOptions = useMemo(() => buildExplorerTimeframeOptions(overview), [overview]);

  const [assetUniverse, setAssetUniverse] = useState(
    () => reconcileAssetUniverse(initialState?.assetUniverse, availableKeys)
  );
  const [sealedFamilyIds, setSealedFamilyIds] = useState(
    () => reconcileSealedFamilyIds(initialState?.sealedFamilyIds, availableSealedIds)
  );
  const [segmentIds, setSegmentIds] = useState(
    () => reconcileCardSegmentIds(initialState?.segmentIds, availableCardIds)
  );
  const [eraIds] = useState(() => initialState?.eraIds || []);
  const [requestedTimeframe, setRequestedTimeframe] = useState(() => initialState?.timeframe || null);
  const { querySeries, addQuery, removeQuery } = useMarketExplorerQueries();

  // A re-published snapshot can add or drop a market or a submarket. Selection
  // follows it rather than pointing at a series that no longer exists.
  useEffect(() => {
    setAssetUniverse((current) => {
      const next = reconcileAssetUniverse(current, availableKeys);
      return next.length === current.length && next.every((key, index) => key === current[index]) ? current : next;
    });
  }, [availableKeys]);
  useEffect(() => {
    setSealedFamilyIds((current) => {
      const next = reconcileSealedFamilyIds(current, availableSealedIds);
      return next.length === current.length && next.every((key, index) => key === current[index]) ? current : next;
    });
  }, [availableSealedIds]);
  useEffect(() => {
    setSegmentIds((current) => {
      const next = reconcileCardSegmentIds(current, availableCardIds);
      return next.length === current.length && next.every((key, index) => key === current[index]) ? current : next;
    });
  }, [availableCardIds]);

  const timeframe = resolveExplorerTimeframe(overview, requestedTimeframe);
  const timeframeLabel = timeframeOptions.find((entry) => entry.key === timeframe)?.label || "";

  const selectedSeriesIds = useMemo(
    () => resolveSelectedSeriesIds({ assetUniverse, sealedFamilyIds, segmentIds }),
    [assetUniverse, sealedFamilyIds, segmentIds]
  );

  const toggleSealed = useCallback((seriesId) => {
    // Toggling a submarket can also supply its parent benchmark, so both
    // pieces of state move together in one commit rather than in two renders
    // that would briefly disagree.
    setAssetUniverse((currentAssets) => {
      let nextAssets = currentAssets;
      setSealedFamilyIds((currentSealed) => {
        const result = toggleSealedFamilyId(currentSealed, seriesId, availableSealedIds, {
          assetUniverse: currentAssets,
          availableAssetKeys: availableKeys,
          segmentIds,
        });
        nextAssets = result.assetUniverse;
        return result.sealedFamilyIds;
      });
      return nextAssets;
    });
  }, [availableSealedIds, availableKeys, segmentIds]);

  const toggleCardSegment = useCallback((seriesId) => {
    // Same one-commit rule as Sealed. Which parent gets supplied depends on
    // whether the rarity index measures the Raw or the Chase universe.
    setAssetUniverse((currentAssets) => {
      let nextAssets = currentAssets;
      setSegmentIds((currentSegments) => {
        const result = toggleCardSegmentId(currentSegments, seriesId, availableCardIds, {
          assetUniverse: currentAssets,
          availableAssetKeys: availableKeys,
          sealedFamilyIds,
        });
        nextAssets = result.assetUniverse;
        return result.segmentIds;
      });
      return nextAssets;
    });
  }, [availableCardIds, availableKeys, sealedFamilyIds]);

  const toggleMarket = useCallback((key) => {
    setAssetUniverse((current) => toggleAssetUniverseKey(current, key, availableKeys, {
      sealedFamilyIds, segmentIds,
    }));
  }, [availableKeys, sealedFamilyIds, segmentIds]);

  // One entry point for the chart legend, which does not care which axis a
  // series came from.
  const toggleSeries = useCallback((seriesId) => {
    if (String(seriesId).startsWith("query:")) removeQuery(seriesId);
    else if (isSealedSegmentSeriesId(seriesId)) toggleSealed(seriesId);
    else if (isCardSegmentSeriesId(seriesId)) toggleCardSegment(seriesId);
    else toggleMarket(seriesId);
  }, [toggleSealed, toggleCardSegment, toggleMarket, removeQuery]);

  const assetEntries = useMemo(
    () => buildAssetUniverseModel(overview, assetUniverse).map((entry) => entry.key === "topChase" ? {
      ...entry,
      label: "Per-Set Chase Market",
      definition: "Tracks the combined chase-card baskets from each eligible Set. Explorer Top 10 queries rank the entire filtered universe instead.",
    } : entry),
    [overview, assetUniverse]
  );
  const sealedEntries = useMemo(
    () => buildSealedFamilyModel(sealedSegments, sealedFamilyIds),
    [sealedSegments, sealedFamilyIds]
  );
  const cardGroups = useMemo(
    () => buildCardSegmentModel(cardSegments, segmentIds),
    [cardSegments, segmentIds]
  );
  const comparableSeries = useMemo(
    () => buildComparableSeries(overview, sealedSegments, cardSegments),
    [overview, sealedSegments, cardSegments]
  );
  const selectedSeries = useMemo(() => {
    const byKey = new Map(comparableSeries.map((series) => [series.key, series]));
    return [...selectedSeriesIds.map((id) => byKey.get(id)).filter(Boolean), ...querySeries];
  }, [comparableSeries, selectedSeriesIds, querySeries]);

  // The filter checkboxes need the same "cannot empty the chart" rule the cards
  // have, counted across BOTH axes.
  const filterAssetEntries = useMemo(
    () => assetEntries.map((entry) => ({ ...entry, shortLabel: entry.label })),
    [assetEntries]
  );

  if (!overview || !overview.families?.length) {
    return (
      <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-label="Market Explorer">
        <p role="status" data-market-explorer-unavailable className="px-4 py-10 text-center text-sm text-[var(--text-secondary)]">
          Market Explorer is temporarily unavailable — no published market snapshot.
        </p>
      </section>
    );
  }

  return (
    <div
      data-market-explorer-workspace
      data-market-explorer-selection={assetUniverse.join(",")}
      data-market-explorer-sealed-family-ids={sealedFamilyIds.join(",")}
      data-market-explorer-segment-ids={segmentIds.join(",")}
      data-market-explorer-series={selectedSeriesIds.join(",")}
      data-market-explorer-timeframe={timeframe || ""}
      data-market-explorer-era-ids={eraIds.join(",")}
      className="space-y-3 desk:space-y-4"
    >
      {/* 1 — the three PARENT market selector cards. Submarkets deliberately do
             not become top-level cards: the hierarchy is parent market, then
             submarket filters. */}
      <div data-market-explorer-cards className="grid grid-cols-1 gap-2.5 tab:grid-cols-3 desk:gap-3">
        {assetEntries.map((entry) => (
          <MarketExplorerSeriesCard
            key={entry.key}
            entry={entry}
            timeframe={timeframe}
            timeframeLabel={timeframeLabel}
            onToggle={toggleMarket}
            isOnlySelection={selectedSeriesIds.length <= 1}
          />
        ))}
      </div>

      <section
        data-market-explorer-analysis
        className={`${styles.surfaceQuiet} ${styles.marketExplorerAnalysis} set-glass-surface`}
        aria-label="Market comparison and segment filters"
      >
        <MarketExplorerChart
          overview={overview}
          selectedSeries={selectedSeries}
          timeframe={timeframe}
          timeframeLabel={timeframeLabel}
          timeframeOptions={timeframeOptions}
          onTimeframeChange={setRequestedTimeframe}
          onToggleSeries={toggleSeries}
        />
        <MarketExplorerFilters
          assetEntries={filterAssetEntries}
          sealedEntries={sealedEntries}
          cardGroups={cardGroups}
          reconciliation={reconciliation}
          cardReconciliation={cardReconciliation}
          topChaseSegmentStatus={topChaseSegmentStatus}
          onToggleMarket={toggleMarket}
          onToggleSealedFamily={toggleSealed}
          onToggleCardSegment={toggleCardSegment}
          selectedSeriesCount={selectedSeriesIds.length}
        />
      </section>

      <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-label="Dynamic card market builder">
        <MarketExplorerQueryBuilder onAddQuery={addQuery} />
      </section>

      <MarketExplorerDynamicSeries
        series={querySeries}
        onRemove={removeQuery}
      />

      <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-label="Selected market detail">
        <MarketExplorerDetails series={selectedSeries} />
      </section>

      <div data-market-explorer-methodology className="grid grid-cols-1 gap-2.5 desk:grid-cols-3 desk:gap-3">
        <p className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/25 px-3 py-2.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--text-primary)]">Tracked Value.</span> {HELP_TRACKED_VALUE}
        </p>
        <p className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/25 px-3 py-2.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--text-primary)]">Market Index.</span> {HELP_INDEX}
        </p>
        <p className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/25 px-3 py-2.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--text-primary)]">Time windows.</span> {HELP_WINDOWS}
        </p>
      </div>
    </div>
  );
}
