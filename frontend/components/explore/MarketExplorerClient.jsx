"use client";

import { useCallback, useMemo, useState } from "react";
import MarketExplorerChart from "./MarketExplorerChart";
import MarketExplorerDetails from "./MarketExplorerDetails";
import MarketExplorerSeriesCard from "./MarketExplorerSeriesCard";
import MarketExplorerQueryBuilder from "./MarketExplorerQueryBuilder";
import MarketExplorerConstituents from "./MarketExplorerConstituents";
import MarketExplorerActiveMarkets from "./MarketExplorerActiveMarkets";
import MarketExplorerMethodology from "./MarketExplorerMethodology";
import {
  buildAssetMarketModel,
  buildBenchmarkModel,
  buildExplorerTimeframeOptions,
  resolveExplorerTimeframe,
} from "@/lib/explore/marketExplorerState.mjs";
import { resolveActiveDetailSeriesId } from "@/lib/explore/marketExplorerConstituents.mjs";
import { buildComparableSeries } from "@/lib/explore/marketExplorerSeries.mjs";
import styles from "./explore.module.css";
import useMarketExplorerQueries from "@/hooks/explore/useMarketExplorerQueries";
import useMarketExplorerFilterOptions from "@/hooks/explore/useMarketExplorerFilterOptions";
import useMarketExplorerSelection from "@/hooks/explore/useMarketExplorerSelection";
import { resolveMarketExplorerPlanAccess } from "@/lib/access/indexPlanAccess.mjs";

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
//
// THREE ACCESS LEVELS, resolved once here and passed down, so no child invents
// its own reading of the same plan:
//
//   basic   — Asset Market. Raw and Sealed, the chart, the timeframes.
//   plus    — the prepared research layers, and their constituents.
//   premium — Build a Market, the custom-query lane.
//
// Signing in is NOT one of the levels. An authenticated account with no paid
// plan gets basic, exactly like an anonymous visitor. Everything below is
// PRESENTATION; the API enforces the same boundary server-side from the
// profile row, and an unentitled caller hitting the endpoint directly is
// refused there rather than here.
// ---------------------------------------------------------------------------
export default function MarketExplorerClient({
  overview,
  sealedSegments = [],
  cardSegments = [],
  reconciliation = null,
  cardReconciliation = null,
  topChaseSegmentStatus = null,
  initialState,
  /** The canonical session user, or null. Server-resolved; never a client flag. */
  user = null,
  coverageSummary = [],
}) {
  const timeframeOptions = useMemo(() => buildExplorerTimeframeOptions(overview), [overview]);
  // ACCESS ARRIVES AS A PROP, RESOLVED ON THE SERVER from the session cookie.
  // Deliberately not read from a client auth context here: the server already
  // knows the plan when it renders this page, so passing it down means the
  // first paint is already correct instead of flashing the basic rail and then
  // unlocking. It also keeps the workspace a pure function of its props, which
  // is what makes it renderable in a test.
  //
  // It is still only PRESENTATION. `resolveMarketExplorerPlanAccess` is the one
  // shared hierarchy, and a caller that passes nothing gets basic — failing
  // closed — while the API enforces the same boundary independently.
  const {
    accessMode, indexPlan, isAuthenticated,
  } = useMemo(() => resolveMarketExplorerPlanAccess(user), [user]);
  const {
    selection: { assetUniverse, sealedFamilyIds, segmentIds },
    selectedSeriesIds, toggleMarket, toggleAny, clearAll: clearAllSelection,
  } = useMarketExplorerSelection({ overview, sealedSegments, cardSegments, initialState });
  const [requestedTimeframe, setRequestedTimeframe] = useState(() => initialState?.timeframe || null);
  // ONE detail target at a time. Four selected markets must not produce four
  // constituent tables; the user names the one they are inspecting.
  const [requestedDetailSeriesId, setRequestedDetailSeriesId] = useState(null);
  const { querySeries, addQuery, updateQuery, removeQuery, clearAll: clearAllQueries } = useMarketExplorerQueries();
  const [editingSeriesId, setEditingSeriesId] = useState(null);
  // VISIBILITY IS NOT REMOVAL. A hidden series is still an Active Market — it
  // still counts toward "what is built", it is still inspectable in
  // Constituents, and un-hiding it never refetches or rebuilds anything. Only
  // Remove (and Clear Graph) actually drop a market from the active set.
  const [hiddenSeriesKeys, setHiddenSeriesKeys] = useState(() => new Set());
  const toggleSeriesVisibility = useCallback((key) => {
    setHiddenSeriesKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }, []);
  const showAllSeries = useCallback(() => setHiddenSeriesKeys(new Set()), []);
  const hideAllSeries = useCallback((keys) => setHiddenSeriesKeys(new Set(keys)), []);
  // CLEAR GRAPH. Removes every active market (prepared AND query-built) and
  // resets visibility, but never touches the Builder draft — a user clearing
  // the chart has not said they want to lose the filters they were composing.
  const clearGraph = useCallback(() => {
    clearAllSelection();
    clearAllQueries();
    setHiddenSeriesKeys(new Set());
    setEditingSeriesId(null);
  }, [clearAllSelection, clearAllQueries]);

  // Era & Sets and Build a Market read the SAME canonical option payload, in
  // one shared request.
  const { status: optionsStatus, options, message: optionsMessage } = useMarketExplorerFilterOptions();

  // Era & Sets sets a research SCOPE, never a series — see the hook.
  const timeframe = resolveExplorerTimeframe(overview, requestedTimeframe);
  const timeframeLabel = timeframeOptions.find((entry) => entry.key === timeframe)?.label || "";
  const toggleSeries = useCallback(
    (seriesId) => toggleAny(seriesId, removeQuery), [toggleAny, removeQuery]);
  const addPrepared = useCallback((seriesId) => {
    if (selectedSeriesIds.includes(seriesId)) return "duplicate";
    toggleAny(seriesId, removeQuery);
    return "added";
  }, [selectedSeriesIds, toggleAny, removeQuery]);

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
  const comparableSeries = useMemo(
    () => buildComparableSeries(overview, sealedSegments, cardSegments),
    [overview, sealedSegments, cardSegments]
  );
  const selectedSeries = useMemo(() => {
    const byKey = new Map(comparableSeries.map((series) => [series.key, series]));
    return [...selectedSeriesIds.map((id) => byKey.get(id)).filter(Boolean), ...querySeries];
  }, [comparableSeries, selectedSeriesIds, querySeries]);

  // WHAT THE CHART ACTUALLY DRAWS. A hidden series is still active (still in
  // Active Markets, still inspectable), it just contributes no line. Zero
  // visible series is a valid, intentional chart state — toggling visibility
  // never adds or removes a market, so it never refetches or rebuilds one.
  const visibleSeries = useMemo(
    () => selectedSeries.filter((series) => !hiddenSeriesKeys.has(series.key)),
    [selectedSeries, hiddenSeriesKeys]
  );
  const allSeriesKeys = useMemo(() => selectedSeries.map((series) => series.key), [selectedSeries]);
  const hideAllActiveSeries = useCallback(() => hideAllSeries(allSeriesKeys), [hideAllSeries, allSeriesKeys]);

  // Derived, never stored: the requested target is kept while it is still on
  // the chart, so adding a market cannot yank the panel away from what the user
  // was reading, and removing one cannot leave it pointing at nothing.
  const activeDetailSeriesId = useMemo(
    () => resolveActiveDetailSeriesId(selectedSeries, requestedDetailSeriesId),
    [selectedSeries, requestedDetailSeriesId]
  );
  const editingSeries = useMemo(() => querySeries.find((series) => series.instanceId === editingSeriesId) || null, [querySeries, editingSeriesId]);
  const beginEdit = useCallback((series) => { setEditingSeriesId(series.instanceId); setRequestedDetailSeriesId(series.key); }, []);

  // Only the PUBLISHED asset-class cards get a top-level card; the graded
  // placeholder is a disabled rail option, not a card with no numbers in it.
  const assetCards = assetEntries;

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
      data-market-explorer-detail-series={activeDetailSeriesId || ""}
      data-market-explorer-access-mode={accessMode}
      className="space-y-3 desk:space-y-4"
    >
      {/* 1 — the ASSET CLASS selector cards. Submarkets and benchmarks
             deliberately do not become top-level cards. */}
      {/* 2 — Explore Segments beside the Market Comparison chart. */}
      <section
        data-market-explorer-analysis
        className={styles.marketExplorerAnalysis}
        aria-label="Market comparison and segment filters"
      >
        <div data-market-explorer-signals className="grid grid-cols-3 gap-2 desk:gap-3">
          {assetCards.map((entry) => <MarketExplorerSeriesCard key={entry.key} entry={entry} timeframe={timeframe} timeframeLabel={timeframeLabel} />)}
        </div>
        <div data-market-explorer-active-strip className="min-w-0 overflow-x-auto border-y border-[var(--border-subtle)] bg-[var(--surface-page)]/20">
          <MarketExplorerActiveMarkets
            series={selectedSeries}
            activeSeriesId={activeDetailSeriesId}
            onInspect={setRequestedDetailSeriesId}
            onRemove={(key) => { if (editingSeries?.key === key) setEditingSeriesId(null); toggleSeries(key); }}
            onEdit={beginEdit}
            canRemove={selectedSeries.length > 1}
            hiddenSeriesKeys={hiddenSeriesKeys}
            onToggleVisibility={toggleSeriesVisibility}
            onShowAll={showAllSeries}
            onHideAll={hideAllActiveSeries}
            timeframe={timeframe}
          />
        </div>
        <MarketExplorerChart
          overview={overview}
          selectedSeries={visibleSeries}
          totalActiveCount={selectedSeries.length}
          timeframe={timeframe}
          timeframeLabel={timeframeLabel}
          timeframeOptions={timeframeOptions}
          onTimeframeChange={setRequestedTimeframe}
          onClearGraph={clearGraph}
        />
        <MarketExplorerQueryBuilder
          options={options}
          optionsStatus={optionsStatus}
          optionsMessage={optionsMessage}
          benchmarkEntries={benchmarkEntries}
          preparedSeries={comparableSeries}
          activeSeries={selectedSeries}
          onAddPrepared={addPrepared}
          onAddQuery={addQuery}
          onUpdateQuery={updateQuery}
          editingSeries={editingSeries}
          onCancelEdit={() => setEditingSeriesId(null)}
          onToggleBenchmark={toggleMarket}
          selectedSeriesCount={selectedSeries.length}
          isAuthenticated={isAuthenticated}
          currentPlan={indexPlan}
          accessMode={accessMode}
          coverageSummary={coverageSummary}
        />
      </section>

      {/* 3 — the advanced lane, collapsed and sitting directly beneath the
             workspace it feeds rather than stranded below unrelated content. */}

      {/* 4 — everything currently charted, from either lane, in ONE row.
             There is deliberately no second chip strip beneath this: custom
             queries used to render their own duplicate row, which showed the
             same markets twice and let the two disagree. Their one unique
             contribution, the index level, moved onto the chip. */}
      {/* ACCEPTED LOWER-PAGE ORDER: Active Markets -> Constituents -> Market
          Comparison Analysis -> Methodology. Constituents answers "what is
          inside the one market I'm inspecting" right after Active Markets
          names it; Comparison Analysis is the cross-market summary table and
          reads naturally after the reader has seen one market's composition;
          Methodology is reference material and never sits between two
          interactive result sections. */}
      <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-label="Current market constituents">
        <MarketExplorerConstituents
          selectedSeries={selectedSeries}
          activeSeriesId={activeDetailSeriesId}
          onSelectSeries={setRequestedDetailSeriesId}
          onEditSeries={beginEdit}
        />
      </section>

      <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-label="Market comparison analysis">
        <MarketExplorerDetails
          // VISIBLE, not merely active: comparison reflects what the chart is
          // currently showing ("compare what I see"). A hidden market stays a
          // full Active Market (still removable, still inspectable in
          // Constituents above) but drops out of this summary table until
          // shown again -- it never disappears from the workspace, only from
          // this one comparison view.
          series={visibleSeries}
          activeSeriesId={activeDetailSeriesId}
          onInspect={setRequestedDetailSeriesId}
          timeframe={timeframe}
        />
      </section>

      <MarketExplorerMethodology />
    </div>
  );
}
