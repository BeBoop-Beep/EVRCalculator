"use client";

import { useCallback, useMemo, useState } from "react";
import MarketExplorerChart from "./MarketExplorerChart";
import MarketExplorerDetails from "./MarketExplorerDetails";
import MarketExplorerFilters from "./MarketExplorerFilters";
import MarketExplorerSeriesCard from "./MarketExplorerSeriesCard";
import MarketExplorerQueryBuilder from "./MarketExplorerQueryBuilder";
import MarketExplorerDynamicSeries from "./MarketExplorerDynamicSeries";
import MarketExplorerConstituents from "./MarketExplorerConstituents";
import MarketExplorerActiveMarkets from "./MarketExplorerActiveMarkets";
import MarketExplorerMethodology from "./MarketExplorerMethodology";
import ExplorerDisclosure from "./ExplorerDisclosure";
import {
  buildAssetMarketModel,
  buildBenchmarkModel,
  buildCardSegmentModel,
  buildExplorerTimeframeOptions,
  buildSealedFamilyModel,
  resolveExplorerTimeframe,
} from "@/lib/explore/marketExplorerState.mjs";
import { resolveActiveDetailSeriesId } from "@/lib/explore/marketExplorerConstituents.mjs";
import { buildComparableSeries } from "@/lib/explore/marketExplorerSeries.mjs";
import styles from "./explore.module.css";
import useMarketExplorerQueries from "@/hooks/explore/useMarketExplorerQueries";
import useMarketExplorerFilterOptions from "@/hooks/explore/useMarketExplorerFilterOptions";
import useMarketExplorerScope from "@/hooks/explore/useMarketExplorerScope";
import useMarketExplorerSelection from "@/hooks/explore/useMarketExplorerSelection";

// ---------------------------------------------------------------------------
// Market Explorer — the research workspace.
//
// TWO LANES, and the page is organised around the difference.
//
//   EXPLORE SEGMENTS is the fast lane: click a prepared market, it is on the
//   chart. Literal — what you clicked is what you get, with no automatic
//   parent benchmark tagging along.
//
//   BUILD A MARKET is the advanced lane: compose a custom filtered universe
//   and the query engine builds a real market from its own constituents. That
//   lane still adds a same-filter benchmark, because a Top 10 of a narrow
//   custom universe is uninterpretable without the same universe in All mode.
//
// ONE state owner, so the selector cards, the rail, the chart, the legend, the
// Active Markets chips and the detail table can never disagree about what is on
// screen. That is the whole reason this is a client boundary; it owns NO market
// data of its own.
//
// DEFAULT DENSITY IS LOW ON PURPOSE. Everything past the asset classes is a
// collapsed disclosure, including the builder. Complexity appears when asked
// for. Expanding a group is pure client state and issues no request.
// ---------------------------------------------------------------------------
export default function MarketExplorerClient({
  overview,
  sealedSegments = [],
  cardSegments = [],
  reconciliation = null,
  cardReconciliation = null,
  topChaseSegmentStatus = null,
  initialState,
}) {
  const timeframeOptions = useMemo(() => buildExplorerTimeframeOptions(overview), [overview]);
  const {
    selection: { assetUniverse, sealedFamilyIds, segmentIds },
    selectedSeriesIds, toggleMarket, toggleSealed, toggleCardSegment, toggleAny,
  } = useMarketExplorerSelection({ overview, sealedSegments, cardSegments, initialState });
  const [requestedTimeframe, setRequestedTimeframe] = useState(() => initialState?.timeframe || null);
  // ONE detail target at a time. Four selected markets must not produce four
  // constituent tables; the user names the one they are inspecting.
  const [requestedDetailSeriesId, setRequestedDetailSeriesId] = useState(null);
  const { querySeries, addQuery, removeQuery } = useMarketExplorerQueries();

  // Era & Sets and Build a Market read the SAME canonical option payload, in
  // one shared request.
  const { status: optionsStatus, options } = useMarketExplorerFilterOptions();

  // Era & Sets sets a research SCOPE, never a series — see the hook.
  const {
    scope: eraScope, tree: eraTree, handoff: scopeHandoff,
    toggleEra: toggleScopeEraId, toggleSet: toggleScopeSetId,
    reset: resetScope, handOffToBuilder: useScopeInBuilder,
  } = useMarketExplorerScope(options);

  const timeframe = resolveExplorerTimeframe(overview, requestedTimeframe);
  const timeframeLabel = timeframeOptions.find((entry) => entry.key === timeframe)?.label || "";
  const toggleSeries = useCallback(
    (seriesId) => toggleAny(seriesId, removeQuery), [toggleAny, removeQuery]);

  // Asset Market is the ASSET CLASSES only. Per-Set Chase is a ranking mode
  // applied to cards, not a fourth asset, so it moved to Benchmarks.
  const assetEntries = useMemo(
    () => buildAssetMarketModel(overview, assetUniverse),
    [overview, assetUniverse]
  );
  const benchmarkEntries = useMemo(
    () => buildBenchmarkModel(overview, assetUniverse),
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

  // Derived, never stored: the requested target is kept while it is still on
  // the chart, so adding a market cannot yank the panel away from what the user
  // was reading, and removing one cannot leave it pointing at nothing.
  const activeDetailSeriesId = useMemo(
    () => resolveActiveDetailSeriesId(selectedSeries, requestedDetailSeriesId),
    [selectedSeries, requestedDetailSeriesId]
  );

  // Only the PUBLISHED asset-class cards get a top-level card; the graded
  // placeholder is a disabled rail option, not a card with no numbers in it.
  const assetCards = useMemo(
    () => assetEntries.filter((entry) => entry.available === true),
    [assetEntries]
  );
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
      data-market-explorer-era-ids={eraScope.eraIds.join(",")}
      data-market-explorer-set-ids={eraScope.setIds.join(",")}
      data-market-explorer-detail-series={activeDetailSeriesId || ""}
      className="space-y-3 desk:space-y-4"
    >
      {/* 1 — the ASSET CLASS selector cards. Submarkets and benchmarks
             deliberately do not become top-level cards. */}
      <div data-market-explorer-cards className="grid grid-cols-1 gap-2.5 tab:grid-cols-2 desk:gap-3">
        {assetCards.map((entry) => (
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

      {/* 2 — Explore Segments beside the Market Comparison chart. */}
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
          benchmarkEntries={benchmarkEntries}
          sealedEntries={sealedEntries}
          cardGroups={cardGroups}
          reconciliation={reconciliation}
          cardReconciliation={cardReconciliation}
          topChaseSegmentStatus={topChaseSegmentStatus}
          eraTree={eraTree}
          eraScope={eraScope}
          eraOptionsStatus={optionsStatus}
          onToggleMarket={toggleMarket}
          onToggleSealedFamily={toggleSealed}
          onToggleCardSegment={toggleCardSegment}
          onToggleScopeEra={toggleScopeEraId}
          onToggleScopeSet={toggleScopeSetId}
          onClearScope={resetScope}
          onUseScopeInBuilder={useScopeInBuilder}
          selectedSeriesCount={selectedSeriesIds.length}
        />
      </section>

      {/* 3 — the advanced lane, collapsed and sitting directly beneath the
             workspace it feeds rather than stranded below unrelated content. */}
      <section className={`${styles.surfaceQuiet} set-glass-surface px-3 py-3 sm:px-4`} aria-label="Build a market">
        {/* `openSignal` opens this group when the Era & Sets hand-off fires:
            the user asked for their scope to be used, so the controls it lands
            in have to be visible. Nothing else may open or close it. */}
        <ExplorerDisclosure
          id="buildAMarket"
          title="Build a Market"
          summary="Create a custom filtered market."
          openSignal={scopeHandoff?.token || null}
        >
          <MarketExplorerQueryBuilder onAddQuery={addQuery} scopeHandoff={scopeHandoff} />
        </ExplorerDisclosure>
      </section>

      {/* 4 — everything currently charted, from either lane, in one row. */}
      <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-label="Active markets">
        <MarketExplorerActiveMarkets
          series={selectedSeries}
          activeSeriesId={activeDetailSeriesId}
          onInspect={setRequestedDetailSeriesId}
          onRemove={toggleSeries}
          canRemove={selectedSeries.length > 1}
        />
      </section>

      <MarketExplorerDynamicSeries
        series={querySeries}
        onRemove={removeQuery}
        activeSeriesId={activeDetailSeriesId}
        onInspect={setRequestedDetailSeriesId}
      />

      <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-label="Current market constituents">
        <MarketExplorerConstituents
          selectedSeries={selectedSeries}
          activeSeriesId={activeDetailSeriesId}
          onSelectSeries={setRequestedDetailSeriesId}
        />
      </section>

      <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-label="Selected market detail">
        <MarketExplorerDetails
          series={selectedSeries}
          activeSeriesId={activeDetailSeriesId}
          onInspect={setRequestedDetailSeriesId}
        />
      </section>

      <MarketExplorerMethodology />
    </div>
  );
}
