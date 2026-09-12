"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MarketExplorerChart from "./MarketExplorerChart";
import MarketExplorerDetails from "./MarketExplorerDetails";
import MarketExplorerSeriesCard from "./MarketExplorerSeriesCard";
import MarketExplorerQueryBuilder from "./MarketExplorerQueryBuilder";
import MarketExplorerConstituents from "./MarketExplorerConstituents";
import MarketExplorerActiveMarkets from "./MarketExplorerActiveMarkets";
import MarketExplorerMethodology from "./MarketExplorerMethodology";
import MarketExplorerBrowse from "./MarketExplorerBrowse";
import MarketExplorerScreens from "./MarketExplorerScreens";
import MarketExplorerRarityMarkets from "./MarketExplorerRarityMarkets";
import MarketExplorerContextRanking from "./MarketExplorerContextRanking";
import MarketExplorerExactBasket from "./MarketExplorerExactBasket";
import { buildPreparedSeries } from "@/lib/explore/marketExplorerPrepared.mjs";
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
import { useAuth } from "@/components/AuthContext";

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
  preparedDirectory = [],
  initialPreparedKey = null,
}) {
  const auth = useAuth();
  // An unresolved/null client context must not erase the server-resolved paid
  // identity during hydration. A resolved context is authoritative afterwards.
  const liveUser = auth?.user || (auth?.authRevision === 0 ? user : null);
  const timeframeOptions = useMemo(() => buildExplorerTimeframeOptions(overview), [overview]);
  // The server user owns the first paint. The sitewide AuthContext user then
  // becomes canonical so login and profile/plan changes recover on this page
  // without inventing an Explorer-specific session or requiring a reload.
  //
  // It is still only PRESENTATION. `resolveMarketExplorerPlanAccess` is the one
  // shared hierarchy, and a caller that passes nothing gets basic — failing
  // closed — while the API enforces the same boundary independently.
  const {
    accessMode, indexPlan, isAuthenticated, canComparePreparedMarkets, canBuildCustomMarkets,
  } = useMemo(() => resolveMarketExplorerPlanAccess(liveUser), [liveUser]);
  const {
    selection: { assetUniverse, sealedFamilyIds, segmentIds },
    selectedSeriesIds, toggleMarket, toggleAny, replacePrepared, clearAll: clearAllSelection,
  } = useMarketExplorerSelection({ overview, sealedSegments, cardSegments, initialState, hasExternalSeries: Boolean(initialPreparedKey) });
  const [requestedTimeframe, setRequestedTimeframe] = useState(() => initialState?.timeframe || null);
  const [compareUpgradeVisible, setCompareUpgradeVisible] = useState(false);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builderTab, setBuilderTab] = useState("filtered");
  const builderDialogRef = useRef(null);
  const [mobileToolsOpen, setMobileToolsOpen] = useState(false);
  const [preparedActiveKeys, setPreparedActiveKeys] = useState(() => initialPreparedKey ? [initialPreparedKey] : []);
  const [loadedPreparedSeries, setLoadedPreparedSeries] = useState([]);

  useEffect(() => {
    if (canComparePreparedMarkets && compareUpgradeVisible) setCompareUpgradeVisible(false);
  }, [canComparePreparedMarkets, compareUpgradeVisible]);
  useEffect(() => {
    if (!builderOpen) return undefined;
    if (typeof document === "undefined") return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const dialog = builderDialogRef.current;
    const focusable = () => [...(dialog?.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])') || [])];
    requestAnimationFrame(() => focusable()[0]?.focus());
    const keydown = (event) => {
      if (event.key === "Escape") { event.preventDefault(); setBuilderOpen(false); return; }
      if (event.key !== "Tab") return;
      const nodes = focusable(); if (!nodes.length) return;
      const first = nodes[0]; const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); document.body.style.overflow = previousOverflow; document.querySelector("[data-market-explorer-build-trigger]")?.focus(); };
  }, [builderOpen]);
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
    setPreparedActiveKeys([]);
  }, [clearAllSelection, clearAllQueries]);

  // Era & Sets and Build a Market read the SAME canonical option payload, in
  // one shared request.
  const {
    status: optionsStatus,
    options,
    message: optionsMessage,
    retry: retryOptions,
    isRetrying: optionsRetrying,
  } = useMarketExplorerFilterOptions({ isAuthenticated, authRevision: auth?.authRevision || 0, enabled: canBuildCustomMarkets });

  // Era & Sets sets a research SCOPE, never a series — see the hook.
  const timeframe = resolveExplorerTimeframe(overview, requestedTimeframe);
  const timeframeLabel = timeframeOptions.find((entry) => entry.key === timeframe)?.label || "";
  const toggleSeries = useCallback(
    (seriesId) => toggleAny(seriesId, removeQuery), [toggleAny, removeQuery]);
  const addPrepared = useCallback((seriesId) => {
    if (selectedSeriesIds.includes(seriesId)) return "duplicate";
    if (!canComparePreparedMarkets) {
      replacePrepared(seriesId);
      clearAllQueries();
      return "replaced";
    }
    toggleAny(seriesId, removeQuery);
    return "added";
  }, [canComparePreparedMarkets, clearAllQueries, replacePrepared, selectedSeriesIds, toggleAny, removeQuery]);
  const comparePrepared = useCallback((seriesId) => {
    if (!canComparePreparedMarkets) {
      setCompareUpgradeVisible(true);
      return "upgrade";
    }
    if (!preparedActiveKeys.length) { clearAllSelection(); clearAllQueries(); }
    setPreparedActiveKeys((current) => current.includes(seriesId) ? current : [...current, seriesId].slice(0, 25));
    return "added";
  }, [canComparePreparedMarkets, clearAllQueries, clearAllSelection, preparedActiveKeys.length]);

  const selectPrepared = useCallback((seriesId) => {
    setPreparedActiveKeys([seriesId]);
    setRequestedDetailSeriesId(seriesId);
    clearAllSelection();
    clearAllQueries();
    setHiddenSeriesKeys(new Set());
  }, [clearAllQueries, clearAllSelection]);

  // A canonical prepared deep link is a selection, not an addition to the
  // legacy default asset pair. Resolve it through the same replacement path
  // Basic Browse uses so the first usable state contains exactly one market.
  useEffect(() => {
    if (!initialPreparedKey) return;
    clearAllSelection();
    clearAllQueries();
    setHiddenSeriesKeys(new Set());
  }, [clearAllQueries, clearAllSelection, initialPreparedKey]);

  useEffect(() => {
    if (!preparedActiveKeys.length) { setLoadedPreparedSeries([]); return; }
    const controller = new AbortController();
    fetch("/api/market/explorer/prepared", {
      method: "POST", credentials: "include", cache: "no-store", signal: controller.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ marketKeys: preparedActiveKeys }),
    }).then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.message || "Prepared comparison unavailable");
      setLoadedPreparedSeries(buildPreparedSeries(payload.markets, payload.history));
    }).catch((error) => { if (error?.name !== "AbortError") setLoadedPreparedSeries([]); });
    return () => controller.abort();
  }, [preparedActiveKeys]);

  // A hand-authored legacy URL can contain several prepared selections. The
  // Basic contract still resolves to one workspace market on first paint.
  useEffect(() => {
    if (!canComparePreparedMarkets && selectedSeriesIds.length > 1) {
      replacePrepared(selectedSeriesIds[0]);
    }
  }, [canComparePreparedMarkets, replacePrepared, selectedSeriesIds]);

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
    return [...selectedSeriesIds.map((id) => byKey.get(id)).filter(Boolean), ...loadedPreparedSeries, ...querySeries];
  }, [comparableSeries, loadedPreparedSeries, selectedSeriesIds, querySeries]);

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
      className="grid min-w-0 gap-3 desk:grid-cols-[minmax(19rem,22rem)_minmax(0,1fr)] desk:items-start desk:gap-4"
    >
      <header data-market-explorer-product-header className="px-1 pb-2 pt-1 desk:col-span-2">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-3xl">Market Explorer</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">Explore. Compare. Build your own Pokémon markets.</p>
      </header>
      {compareUpgradeVisible ? (
        <section data-market-explorer-compare-upgrade role="status" className={`${styles.surfaceQuiet} set-glass-surface fixed left-1/2 top-20 z-[80] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 px-4 py-4 shadow-2xl`}>
          <div className="flex flex-wrap items-start gap-3">
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">Compare markets with Index+</h2>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">Put Sets, Eras and Quick Markets on the same timeline and see what is actually outperforming.</p>
            </div>
            <a href="/pricing" data-market-explorer-compare-upgrade-link className="rounded-md border border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.16)] px-3 py-2 text-xs font-semibold text-[rgb(45,212,191)]">Upgrade to Index+</a>
            <button type="button" aria-label="Dismiss comparison upgrade" onClick={() => setCompareUpgradeVisible(false)} className="rounded px-2 py-1 text-xs text-[var(--text-secondary)]">Dismiss</button>
          </div>
        </section>
      ) : null}
      <button type="button" data-market-explorer-mobile-tools aria-expanded={mobileToolsOpen}
        onClick={() => setMobileToolsOpen((open) => !open)}
        className="order-1 flex min-h-11 items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 text-sm font-semibold text-[var(--text-primary)] desk:hidden">
        Markets / Tools <span aria-hidden="true">{mobileToolsOpen ? "−" : "+"}</span>
      </button>
      <aside id="explorer-controls" data-market-explorer-sidebar className={`${mobileToolsOpen ? "block" : "hidden"} order-3 min-w-0 space-y-3 desk:order-none desk:col-start-1 desk:row-start-2 desk:block desk:max-h-[calc(100vh-7rem)] desk:overflow-y-auto`}>
        <section data-market-explorer-zone="explore" className={`${styles.explorerZone} ${styles.surfaceQuiet} set-glass-surface`} aria-labelledby="explore-markets-zone-heading">
        <div className={styles.explorerZoneHeader}>
          <p className={styles.explorerZoneEyebrow}>Explore</p>
          <h2 id="explore-markets-zone-heading" className={styles.explorerZoneTitle}>Browse Markets</h2>
          <p className={styles.explorerZoneDescription}>Browse published Set, Era, and curated markets.</p>
        </div>
        <MarketExplorerBrowse directory={preparedDirectory} activeKeys={preparedActiveKeys}
          canCompare={canComparePreparedMarkets} onSelect={selectPrepared} onCompare={comparePrepared} onBuild={() => setBuilderOpen(true)} />
        <div data-market-explorer-sidebar-section="analyze" className="border-t border-[var(--border-subtle)] px-3 py-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">Analyze</p>
          <MarketExplorerRarityMarkets directory={preparedDirectory} activeKeys={preparedActiveKeys} onSelect={selectPrepared} />
          <MarketExplorerScreens canUse={canComparePreparedMarkets} activeKeys={preparedActiveKeys}
            onUpgrade={() => setCompareUpgradeVisible(true)} onSelect={comparePrepared} />
        </div>
        </section>
        <section ref={builderDialogRef} role="dialog" aria-modal="true" aria-hidden={!builderOpen} data-market-explorer-builder-overlay data-market-explorer-zone="build" className={`${builderOpen ? "fixed inset-0 z-[70] flex flex-col overflow-y-auto bg-[var(--surface-page)] shadow-2xl desk:inset-x-1/2 desk:bottom-auto desk:top-1/2 desk:max-h-[88vh] desk:w-[min(64rem,calc(100vw-3rem))] desk:-translate-x-1/2 desk:-translate-y-1/2 desk:rounded-2xl" : "hidden"} ${styles.explorerZone} ${styles.surfaceQuiet} set-glass-surface`} aria-labelledby="build-markets-zone-heading">
          <div className={styles.explorerZoneHeader}>
            <p className={styles.explorerZoneEyebrow}>Build · Premium</p>
            <h2 id="build-markets-zone-heading" className={styles.explorerZoneTitle}>Build Your Market</h2>
            <p className={styles.explorerZoneDescription}>Use filters for a dynamic market or hand-pick an exact basket.</p>
            <button type="button" aria-label="Close Build Your Market" onClick={() => setBuilderOpen(false)} className="absolute right-4 top-4 min-h-11 min-w-11 rounded-full border border-[var(--border-subtle)] text-xl">×</button>
          </div>
          <div role="tablist" aria-label="Market creation path" className="flex gap-2 border-y border-[var(--border-subtle)] px-4 py-3">{[["filtered", "Custom Filtered"], ["exact", "Exact Basket"]].map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={builderTab === id} onClick={() => setBuilderTab(id)} className={`min-h-10 rounded-md border px-4 text-sm font-semibold ${builderTab === id ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.14)] text-[rgb(45,212,191)]" : "border-[var(--border-subtle)]"}`}>{label}</button>)}</div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div hidden={builderTab !== "filtered"} data-market-explorer-build-path="filtered" className={styles.explorerBuildPath}>
              <MarketExplorerQueryBuilder optionsProvided options={options} optionsStatus={optionsStatus} optionsMessage={optionsMessage}
                onRetryOptions={retryOptions} optionsRetrying={optionsRetrying} benchmarkEntries={benchmarkEntries}
                preparedSeries={comparableSeries} activeSeries={selectedSeries} onAddPrepared={addPrepared} onAddQuery={addQuery}
                onUpdateQuery={updateQuery} editingSeries={editingSeries?.spec?.membershipMode === "explicit" ? null : editingSeries}
                onCancelEdit={() => setEditingSeriesId(null)} onToggleBenchmark={toggleMarket} selectedSeriesCount={selectedSeries.length}
                isAuthenticated={isAuthenticated} currentPlan={indexPlan} accessMode={accessMode} coverageSummary={coverageSummary} />
            </div>
            <div hidden={builderTab !== "exact"} data-market-explorer-build-path="exact" className={styles.explorerBuildPath}>
              <MarketExplorerExactBasket currentPlan={indexPlan} editingSeries={editingSeries}
                onAddQuery={addQuery} onUpdateQuery={updateQuery} onCancelEdit={() => setEditingSeriesId(null)} />
            </div>
          </div>
        </section>
      </aside>
      {/* 1 — the ASSET CLASS selector cards. Submarkets and benchmarks
             deliberately do not become top-level cards. */}
      {/* 2 — Explore Segments beside the Market Comparison chart. */}
      <section
        data-market-explorer-analysis
        data-market-explorer-zone="compare"
        className={`order-2 flex min-w-0 flex-col ${styles.explorerZone} ${styles.explorerZonePrimary} ${styles.surfaceQuiet} set-glass-surface desk:order-none desk:col-start-2`}
        aria-labelledby="compare-markets-zone-heading"
      >
        <div className="sr-only">
          <p className={styles.explorerZoneEyebrow}>02 / Research</p>
          <h2 id="compare-markets-zone-heading" className={styles.explorerZoneTitle}>Compare &amp; Analyze</h2>
          <p className={styles.explorerZoneDescription}>Inspect active markets on one timeline, then examine composition and context.</p>
        </div>
        <div data-market-explorer-signals className="order-3 border-t border-[var(--border-subtle)] px-3 py-3 sm:px-4">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">Market overview</p>
          <div className="grid grid-cols-3 gap-2 desk:gap-3">
            {assetCards.map((entry) => <MarketExplorerSeriesCard key={entry.key} entry={entry} timeframe={timeframe} timeframeLabel={timeframeLabel} />)}
          </div>
        </div>
        <div data-market-explorer-active-strip className="order-1 min-w-0 border-b border-[var(--border-subtle)] bg-[var(--surface-page)]/20">
          <MarketExplorerActiveMarkets
            series={selectedSeries}
            activeSeriesId={activeDetailSeriesId}
            onInspect={setRequestedDetailSeriesId}
            onRemove={(key) => {
              if (preparedActiveKeys.includes(key)) setPreparedActiveKeys((current) => current.filter((entry) => entry !== key));
              else { if (editingSeries?.key === key) setEditingSeriesId(null); toggleSeries(key); }
            }}
            onEdit={beginEdit}
            canRemove={selectedSeries.length > 1}
            hiddenSeriesKeys={hiddenSeriesKeys}
            onToggleVisibility={toggleSeriesVisibility}
            onShowAll={showAllSeries}
            onHideAll={hideAllActiveSeries}
            onClearAll={clearGraph}
            timeframe={timeframe}
          />
        </div>
        <div data-market-explorer-graph className="order-2 min-w-0">
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
        </div>

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
      <div data-market-explorer-compare-results className="order-4 border-t border-[var(--border-subtle)]" aria-label="Market comparison analysis">
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
        <div className={styles.explorerInspectionGrid}>
          <section aria-label="Current market constituents" className="min-w-0">
            <MarketExplorerConstituents selectedSeries={selectedSeries} activeSeriesId={activeDetailSeriesId}
              onSelectSeries={setRequestedDetailSeriesId} onEditSeries={beginEdit} />
          </section>
          <div className="min-w-0">
            <MarketExplorerContextRanking market={selectedSeries.find((entry) => entry.key === activeDetailSeriesId)} timeframe={timeframe}
              canUse={canComparePreparedMarkets} onUpgrade={() => setCompareUpgradeVisible(true)} />
          </div>
        </div>
      </div>
      </section>

      <div className="order-5 desk:col-span-2"><MarketExplorerMethodology /></div>
    </div>
  );
}
