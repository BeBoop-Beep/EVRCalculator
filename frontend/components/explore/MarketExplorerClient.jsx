"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import MarketExplorerChart from "./MarketExplorerChart";
import MarketExplorerDetails from "./MarketExplorerDetails";
import MarketExplorerQueryBuilder from "./MarketExplorerQueryBuilder";
import MarketExplorerConstituents from "./MarketExplorerConstituents";
import MarketExplorerActiveMarkets from "./MarketExplorerActiveMarkets";
import MarketExplorerMethodology from "./MarketExplorerMethodology";
import MarketExplorerBrowse from "./MarketExplorerBrowse";
import MarketExplorerScreens from "./MarketExplorerScreens";
import MarketExplorerRarityMarkets from "./MarketExplorerRarityMarkets";
import MarketExplorerSealedTypes, { MarketExplorerSealedQuickMarkets } from "./MarketExplorerSealedTypes";
import useAssetOptions from "@/hooks/explore/useAssetOptions";
import { unifySeriesByKey } from "@/lib/explore/marketExplorerComposition.mjs";
import MarketExplorerContextRanking from "./MarketExplorerContextRanking";
import MarketExplorerExactBasket from "./MarketExplorerExactBasket";
import usePreparedMarkets from "@/hooks/explore/usePreparedMarkets";
import { describePreparedFailure, PREPARED_FAILURE } from "@/lib/explore/marketExplorerPreparedLoader.mjs";
import {
  buildBenchmarkModel,
  buildExplorerTimeframeOptions,
  resolveExplorerTimeframe,
} from "@/lib/explore/marketExplorerState.mjs";
import { resolveActiveDetailSeriesId } from "@/lib/explore/marketExplorerConstituents.mjs";
import { buildComparableSeries } from "@/lib/explore/marketExplorerSeries.mjs";
import {
  WORKSPACE_VIEW_ACTIONS,
  createConstituentPageCache,
  createWorkspaceViewState,
  reduceWorkspaceView,
} from "@/lib/explore/marketExplorerWorkspace.mjs";
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
  preparedDirectoryStatus = "ready",
  initialPreparedKey = null,
}) {
  const auth = useAuth();
  // An unresolved/null client context must not erase the server-resolved paid
  // identity during hydration. A resolved context is authoritative afterwards.
  const liveUser = auth?.user || (!auth || auth.authRevision === 0 ? user : null);
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
  const [builderMode, setBuilderMode] = useState("exact");
  // activeBrowseAsset is BROWSING state (search scope, categories, rarity/type controls,
  // Builder default asset). It is deliberately NOT the chart selection: switching it
  // never adds or removes an active market.
  const [activeBrowseAsset, setActiveBrowseAsset] = useState("cards");
  const [basketSeed, setBasketSeed] = useState(null);
  const cardOptionStates = useAssetOptions("cards", { enabled: activeBrowseAsset === "cards" });
  const sealedOptionStates = useAssetOptions("sealed", { enabled: activeBrowseAsset === "sealed" });
  const gradedOptionStates = useAssetOptions("graded", { enabled: activeBrowseAsset === "graded" });
  const [detailsOpen, setDetailsOpen] = useState(false);
  const builderDialogRef = useRef(null);
  const [mobileToolsOpen, setMobileToolsOpen] = useState(false);
  // PREPARED SELECTION LIFECYCLE (marketExplorerPreparedLoader.mjs). A prepared
  // market is ACTIVE only once its data has loaded. Requested-but-unloaded and
  // failed markets live in their own sets, are never re-sent with later
  // requests, and never remove a market that already loaded.
  const {
    loader: preparedLoader, series: loadedPreparedSeries, loadedKeys: preparedActiveKeys,
    pendingKeys: preparedPendingKeys, failed: preparedFailures, failedKeys: preparedFailedKeys,
  } = usePreparedMarkets();
  const preparedLabels = useMemo(
    () => new Map((preparedDirectory || []).map((row) => [row.market_key, row.label])), [preparedDirectory]);

  useEffect(() => {
    if (canComparePreparedMarkets && compareUpgradeVisible) setCompareUpgradeVisible(false);
  }, [canComparePreparedMarkets, compareUpgradeVisible]);
  useEffect(() => {
    if (!builderOpen) return undefined;
    if (typeof document === "undefined") return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const dialog = builderDialogRef.current;
    if (typeof dialog?.showModal === "function" && !dialog.open) dialog.showModal();
    const focusable = () => [...(dialog?.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])') || [])];
    requestAnimationFrame(() => {
      const search = dialog?.querySelector("[data-market-exact-search]");
      if (search) search.focus(); else focusable()[0]?.focus();
    });
    const keydown = (event) => {
      if (event.key === "Escape") { event.preventDefault(); setBuilderOpen(false); return; }
      if (event.key !== "Tab") return;
      const nodes = focusable(); if (!nodes.length) return;
      const first = nodes[0]; const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); if (dialog?.open) dialog.close(); document.body.style.overflow = previousOverflow; document.querySelector("[data-market-explorer-build-trigger]")?.focus(); };
  }, [builderOpen]);
  // CONSTITUENT TARGET. `requestedDetailSeriesId` is the user's last explicit
  // choice; the EFFECTIVE target (`activeDetailSeriesId`, below) is derived from it
  // through resolveActiveDetailSeriesId: a stable market KEY (never a label), exactly
  // one enumerable active market, kept while that market is still active, with a
  // deterministic fallback (first enumerable market) when it is removed. No second
  // state variable exists for the target. Focus never writes to it.
  const [requestedDetailSeriesId, setRequestedDetailSeriesId] = useState(null);
  const { querySeries, addQuery, updateQuery, removeQuery, clearAll: clearAllQueries } = useMarketExplorerQueries();
  const [editingSeriesId, setEditingSeriesId] = useState(null);
  // ACTIVE != VISIBLE != TARGET != FOCUSED. A hidden series is still an Active
  // Market (still counted, still inspectable in Constituents; un-hiding never
  // refetches). Visibility and FOCUS (`focused`: null = comparison mode) move in
  // one reducer only because their transitions are atomic; see
  // marketExplorerWorkspace.mjs for the deterministic rules.
  const [workspaceView, dispatchView] = useReducer(reduceWorkspaceView, undefined, createWorkspaceViewState);
  const hiddenSeriesKeys = workspaceView.hidden;
  const toggleSeriesVisibility = useCallback((key) => dispatchView({ type: WORKSPACE_VIEW_ACTIONS.toggleVisibility, key }), []);
  const showAllSeries = useCallback(() => dispatchView({ type: WORKSPACE_VIEW_ACTIONS.showAll }), []);
  const hideAllSeries = useCallback((keys) => dispatchView({ type: WORKSPACE_VIEW_ACTIONS.hideAll, keys }), []);
  const focusSeries = useCallback((key) => dispatchView({ type: WORKSPACE_VIEW_ACTIONS.focus, key }), []);
  const clearFocus = useCallback(() => dispatchView({ type: WORKSPACE_VIEW_ACTIONS.clearFocus }), []);
  // Generation-pinned constituent pages survive closing the workspace and
  // switching targets; they are dropped only for a removed market or Clear All.
  const constituentPageCache = useMemo(() => createConstituentPageCache(), []);
  // CLEAR ALL — the ONE workspace-level clear (formerly "Clear Graph" and a
  // second "Clear all"). Removes every active market (prepared AND query-built),
  // visibility bookkeeping, focus, the constituent target and the open panel. It
  // never touches the Builder draft, the Browse context or the filter-options
  // cache. (Function keeps its historical name `clearGraph`.)
  const clearGraph = useCallback(() => {
    clearAllSelection();
    clearAllQueries();
    dispatchView({ type: WORKSPACE_VIEW_ACTIONS.reset });
    setEditingSeriesId(null);
    setRequestedDetailSeriesId(null);
    setDetailsOpen(false);
    constituentPageCache.clear();
    preparedLoader.clear();
  }, [clearAllSelection, clearAllQueries, preparedLoader, constituentPageCache]);

  // Era & Sets and Build a Market read the SAME canonical option payload, in
  // one shared request.
  const {
    status: optionsStatus,
    options,
    message: optionsMessage,
    retry: retryOptions,
    isRetrying: optionsRetrying,
  } = useMarketExplorerFilterOptions({ isAuthenticated, authRevision: auth?.authRevision || 0, enabled: isAuthenticated && canComparePreparedMarkets });

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
    const current = preparedLoader.getSnapshot();
    if (current.loaded[seriesId]) {
      preparedLoader.remove(seriesId);
      return "removed";
    }
    // Duplicate clicks while loading are guarded; the pending strip can cancel.
    if (current.pending.includes(seriesId)) return "pending";
    preparedLoader.add(seriesId).then((outcome) => {
      if (outcome === "loaded") setRequestedDetailSeriesId(seriesId);
    });
    return "added";
  }, [canComparePreparedMarkets, preparedLoader]);

  // Comparison-capable users accumulate markets. Selecting a third market must
  // never silently delete the first two; active prepared markets toggle in
  // place and can be removed from the same surface that added them.
  const selectPrepared = useCallback((seriesId) => {
    if (canComparePreparedMarkets) return comparePrepared(seriesId);
    // Basic: one workspace market. The previous line stays until the
    // replacement has LOADED, so a failed swap leaves the chart intact.
    preparedLoader.replace(seriesId).then((outcome) => {
      if (outcome !== "loaded" && outcome !== "duplicate") return;
      setRequestedDetailSeriesId(seriesId);
      clearAllSelection();
      clearAllQueries();
      dispatchView({ type: WORKSPACE_VIEW_ACTIONS.reset });
    });
    return "replaced";
  }, [canComparePreparedMarkets, clearAllQueries, clearAllSelection, comparePrepared, preparedLoader]);

  // A canonical prepared deep link is a selection, not an addition to the
  // legacy default asset pair. Resolve it through the same replacement path
  // Basic Browse uses so the first usable state contains exactly one market.
  useEffect(() => {
    if (!initialPreparedKey) return;
    clearAllSelection();
    clearAllQueries();
    dispatchView({ type: WORKSPACE_VIEW_ACTIONS.reset });
    preparedLoader.replace(initialPreparedKey);
  }, [clearAllQueries, clearAllSelection, initialPreparedKey, preparedLoader]);

  // A hand-authored legacy URL can contain several prepared selections. The
  // Basic contract still resolves to one workspace market on first paint.
  useEffect(() => {
    if (!canComparePreparedMarkets && selectedSeriesIds.length > 1) {
      replacePrepared(selectedSeriesIds[0]);
    }
  }, [canComparePreparedMarkets, replacePrepared, selectedSeriesIds]);

  // Per-Set Chase remains available as a benchmark inside Custom Filters.
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
    // ONE identity per visible market: V2 parents (raw / sealedMarket) supersede the
    // legacy overview entry of the same key instead of drawing a duplicate line.
    return unifySeriesByKey([...selectedSeriesIds.map((id) => byKey.get(id)).filter(Boolean), ...loadedPreparedSeries, ...querySeries]);
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
  const activeDetailMarket = selectedSeries.find((entry) => entry.key === activeDetailSeriesId) || null;
  // FOCUS is derived against what is active and visible, so a removed or hidden
  // market can never leave a stale focus behind.
  const focusedSeriesKey = workspaceView.focused && allSeriesKeys.includes(workspaceView.focused)
    && !hiddenSeriesKeys.has(workspaceView.focused) ? workspaceView.focused : null;
  useEffect(() => {
    dispatchView({ type: WORKSPACE_VIEW_ACTIONS.reconcile, activeKeys: allSeriesKeys });
  }, [allSeriesKeys]);
  // The workspace has nothing to show once the last active market is gone.
  const hasActiveMarkets = selectedSeries.length > 0;
  useEffect(() => {
    if (!hasActiveMarkets) setDetailsOpen(false);
  }, [hasActiveMarkets]);
  const editingSeries = useMemo(() => querySeries.find((series) => series.instanceId === editingSeriesId) || null, [querySeries, editingSeriesId]);
  const beginEdit = useCallback((series) => {
    setEditingSeriesId(series.instanceId);
    setRequestedDetailSeriesId(series.key);
    // Custom Filters live in Build Your Market: open the tab that owns this spec.
    setBuilderMode(series.spec?.membershipMode === "explicit" ? "exact" : "filters");
    setBuilderOpen(true);
    if (series.spec?.membershipMode !== "explicit") setMobileToolsOpen(true);
  }, []);

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
      className="grid min-w-0 gap-3 desk:grid-cols-[minmax(18rem,20rem)_minmax(0,1fr)] desk:items-start desk:gap-3"
    >
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
      <aside id="explorer-controls" data-market-explorer-sidebar className={`${mobileToolsOpen ? "block" : "hidden"} order-3 min-w-0 space-y-3 desk:order-none desk:col-start-1 desk:block desk:max-h-[calc(100vh-7rem)] desk:overflow-y-auto`}>
        <section data-market-explorer-zone="explore" className={`${styles.explorerZone} ${styles.surfaceQuiet} set-glass-surface`} aria-labelledby="explore-markets-zone-heading">
        <div className={styles.explorerZoneHeader}>
          <p className={styles.explorerZoneEyebrow}>Explore</p>
          <h2 id="explore-markets-zone-heading" className={styles.explorerZoneTitle}>Browse Markets</h2>
          <p className={styles.explorerZoneDescription}>Browse published Set, Era, and curated markets.</p>
        </div>
        <MarketExplorerBrowse directory={preparedDirectory} directoryStatus={preparedDirectoryStatus} activeKeys={preparedActiveKeys}
          pendingKeys={preparedPendingKeys} failedKeys={preparedFailedKeys}
          canCompare={canComparePreparedMarkets} onSelect={selectPrepared} onCompare={comparePrepared}
          assetLayer={activeBrowseAsset} onAssetLayerChange={setActiveBrowseAsset}
          gradedReason={gradedOptionStates.data?.reason || null}
          onAddToBasket={(item) => { setBasketSeed({ item, nonce: (basketSeed?.nonce || 0) + 1 }); setBuilderMode("exact"); setBuilderOpen(true); }}
          onBuild={() => { setBuilderMode("exact"); setBuilderOpen(true); }} />
        <div data-market-explorer-sidebar-section="analyze" className="border-t border-[var(--border-subtle)] px-3 py-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">Analyze</p>
          {activeBrowseAsset === "cards" ? <MarketExplorerRarityMarkets
            directory={preparedDirectory}
            assetOptions={cardOptionStates.status === "ready" ? cardOptionStates.data : null}
            rarityOptions={options?.cardRarities?.rarities || []}
            activeKeys={preparedActiveKeys}
            pendingKeys={preparedPendingKeys}
            activeSeries={querySeries}
            canUse={canComparePreparedMarkets}
            onUpgrade={() => setCompareUpgradeVisible(true)}
            onSelect={selectPrepared}
            onAddQuery={addQuery}
            onRemoveQuery={removeQuery}
          /> : null}
          {activeBrowseAsset === "sealed" ? <>
            <MarketExplorerSealedQuickMarkets options={sealedOptionStates.data} activeKeys={preparedActiveKeys} onSelect={selectPrepared} />
            <MarketExplorerSealedTypes options={sealedOptionStates.data} status={sealedOptionStates.status} onRetry={sealedOptionStates.retry}
              activeKeys={preparedActiveKeys} pendingKeys={preparedPendingKeys} activeSeries={querySeries}
              canBuild={canBuildCustomMarkets} onUpgrade={() => setCompareUpgradeVisible(true)}
              onSelect={selectPrepared} onAddQuery={addQuery} onRemoveQuery={removeQuery} />
          </> : null}
          <MarketExplorerScreens canUse={canComparePreparedMarkets} activeKeys={preparedActiveKeys} pendingKeys={preparedPendingKeys}
            onUpgrade={() => setCompareUpgradeVisible(true)} onSelect={selectPrepared} />
        </div>
        </section>
      </aside>
        <dialog ref={builderDialogRef} role="dialog" aria-modal="true" aria-hidden={!builderOpen} data-market-explorer-builder-overlay data-market-explorer-zone="build" className={builderOpen ? "fixed inset-0 z-[9999] m-0 flex h-full max-h-none w-full max-w-none items-stretch justify-center border-0 bg-slate-950/80 p-0 backdrop-blur-sm desk:items-center desk:p-6" : "hidden"} aria-labelledby="build-markets-zone-heading">
          <div className={`${styles.explorerZone} ${styles.surfaceQuiet} set-glass-surface flex h-[100dvh] w-full min-w-0 flex-col overflow-hidden bg-[var(--surface-page)] shadow-2xl desk:h-[86vh] desk:max-h-[90vh] desk:w-[min(78rem,calc(100vw-3rem))] desk:rounded-2xl`}>
            <div className="flex flex-none items-center gap-2 border-b border-[var(--border-subtle)] px-4 py-2 sm:px-6" role="tablist" aria-label="Build Your Market method">
              <button type="button" role="tab" aria-selected={builderMode === "exact"} onClick={() => setBuilderMode("exact")} className={`min-h-10 rounded-md border px-4 text-xs font-semibold ${builderMode === "exact" ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.14)] text-[rgb(45,212,191)]" : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>Cards &amp; Products</button>
              <button type="button" role="tab" aria-selected={builderMode === "filters"} onClick={() => setBuilderMode("filters")} className={`min-h-10 rounded-md border px-4 text-xs font-semibold ${builderMode === "filters" ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.14)] text-[rgb(45,212,191)]" : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>Custom Filters{!canBuildCustomMarkets ? " · Premium" : ""}</button>
            </div>
            {builderMode === "exact" ? (
              <div data-market-explorer-build-path="exact" className="flex min-h-0 flex-1 flex-col">
                <MarketExplorerExactBasket currentPlan={indexPlan} editingSeries={editingSeries}
                  initialScope={activeBrowseAsset === "sealed" ? "sealed" : "all"} seedItem={basketSeed}
                  onAddQuery={addQuery} onUpdateQuery={updateQuery} onCancelEdit={() => setEditingSeriesId(null)} onClose={() => setBuilderOpen(false)} />
              </div>
            ) : (
              <div data-market-explorer-build-path="filters" className="min-h-0 flex-1 overflow-y-auto">
                <MarketExplorerQueryBuilder presentation="sidebar" optionsProvided options={options} optionsStatus={optionsStatus} optionsMessage={optionsMessage}
                  onRetryOptions={retryOptions} optionsRetrying={optionsRetrying} benchmarkEntries={benchmarkEntries}
                  preparedSeries={comparableSeries} activeSeries={selectedSeries} onAddPrepared={addPrepared} onAddQuery={addQuery}
                  onUpdateQuery={updateQuery} editingSeries={editingSeries?.spec?.membershipMode === "explicit" ? null : editingSeries}
                  onCancelEdit={() => setEditingSeriesId(null)} onToggleBenchmark={toggleMarket} selectedSeriesCount={selectedSeries.length}
                  isAuthenticated={isAuthenticated} currentPlan={indexPlan} accessMode={accessMode} coverageSummary={coverageSummary} />
                <div className="sticky bottom-0 flex justify-end border-t border-[var(--border-subtle)] bg-[var(--surface-page)]/95 px-4 py-3 backdrop-blur sm:px-6">
                  <button type="button" onClick={() => setBuilderOpen(false)} className="min-h-10 rounded-md border border-[var(--border-subtle)] px-4 text-xs font-semibold text-[var(--text-primary)]">Close</button>
                </div>
              </div>
            )}
          </div>
        </dialog>
      {/* 1 — the ASSET CLASS selector cards. Submarkets and benchmarks
             deliberately do not become top-level cards. */}
      {/* 2 — Explore Segments beside the Market Comparison chart. */}
      <section
        data-market-explorer-analysis
        data-market-explorer-zone="compare"
        className="order-2 flex min-w-0 flex-col desk:order-none desk:col-start-2"
        aria-labelledby="compare-markets-zone-heading"
      >
        <div className="sr-only">
          <p className={styles.explorerZoneEyebrow}>02 / Research</p>
          <h2 id="compare-markets-zone-heading" className={styles.explorerZoneTitle}>Compare &amp; Analyze</h2>
          <p className={styles.explorerZoneDescription}>Inspect active markets on one timeline, then examine composition and context.</p>
        </div>
        <div data-market-explorer-active-strip className="order-1 min-w-0 border-b border-[var(--border-subtle)] bg-[var(--surface-page)]/20">
          <MarketExplorerActiveMarkets
            series={selectedSeries}
            activeSeriesId={activeDetailSeriesId}
            onInspect={setRequestedDetailSeriesId}
            onRemove={(key) => {
              // Removing a market forgets it as the requested target; a non-target
              // removal leaves the target alone, a target removal falls back
              // deterministically (resolveActiveDetailSeriesId).
              if (requestedDetailSeriesId === key) setRequestedDetailSeriesId(null);
              if (preparedActiveKeys.includes(key)) { preparedLoader.remove(key); constituentPageCache.evictMarket(key); }
              else if (querySeries.some((entry) => entry.key === key)) {
                // Query-built markets are keyed by their instance id (`market:...`),
                // which toggleAny's legacy `query:` prefix test never matched, so the
                // remove button was a silent no-op for them. Route by SOURCE, not key shape.
                if (editingSeries?.key === key) setEditingSeriesId(null);
                removeQuery(key);
              } else { toggleSeries(key); }
            }}
            onEdit={beginEdit}
            canRemove
            hiddenSeriesKeys={hiddenSeriesKeys}
            onToggleVisibility={toggleSeriesVisibility}
            onShowAll={showAllSeries}
            onHideAll={hideAllActiveSeries}
            onClearAll={clearGraph}
            focusedSeriesKey={focusedSeriesKey}
            onFocus={focusSeries}
            timeframe={timeframe}
          />
        </div>
        <div data-market-explorer-chart-workspace className="order-2 relative min-w-0">
        <div
          data-market-explorer-graph
          aria-hidden={detailsOpen ? "true" : undefined}
          inert={detailsOpen ? true : undefined}
          className={detailsOpen ? "pointer-events-none min-w-0 select-none" : "min-w-0"}
        >
          {preparedPendingKeys.map((key) => (
            <div key={`pending:${key}`} role="status" data-market-explorer-prepared-pending={key} className="mb-2 flex items-center justify-between gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              <span>Adding {preparedLabels.get(key) || "market"}…</span>
              <button type="button" data-market-explorer-prepared-cancel={key} onClick={() => preparedLoader.remove(key)} className="rounded border border-[var(--border-subtle)] px-2 py-1 font-semibold">Cancel</button>
            </div>
          ))}
          {preparedFailedKeys.map((key) => {
            const failure = preparedFailures[key];
            return (
              <div key={`failed:${key}`} role="alert" data-market-explorer-prepared-error={key} data-market-explorer-prepared-error-kind={failure?.kind} className="mb-2 flex items-center justify-between gap-2 rounded-md border border-[rgba(248,113,113,.4)] bg-[rgba(248,113,113,.08)] px-3 py-2 text-xs text-[rgb(248,113,113)]">
                <span>{describePreparedFailure(preparedLabels.get(key), failure)}{selectedSeries.length ? " Your other markets are still shown." : ""}</span>
                <span className="flex flex-none gap-1.5">
                  {failure?.retryable ? <button type="button" data-market-explorer-prepared-retry={key} onClick={() => preparedLoader.retry(key)} className="rounded border border-[rgba(248,113,113,.45)] px-2 py-1 font-semibold">Retry</button> : null}
                  {failure?.kind === PREPARED_FAILURE.entitlement ? <a href="/pricing" className="rounded border border-[rgba(248,113,113,.45)] px-2 py-1 font-semibold">Upgrade</a> : null}
                  <button type="button" data-market-explorer-prepared-dismiss={key} onClick={() => preparedLoader.dismissFailure(key)} className="rounded border border-[rgba(248,113,113,.45)] px-2 py-1 font-semibold">Dismiss</button>
                </span>
              </div>
            );
          })}
          {loadedPreparedSeries.filter((series) => series.trend.length < 2).map((series) => (
            <p key={`nohistory:${series.key}`} role="status" data-market-explorer-prepared-no-history={series.key} className="mb-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              {series.label} has no published price history to chart yet.
            </p>
          ))}
          <MarketExplorerChart
            overview={overview}
            selectedSeries={visibleSeries}
            totalActiveCount={selectedSeries.length}
            timeframe={timeframe}
            timeframeLabel={timeframeLabel}
            timeframeOptions={timeframeOptions}
            onTimeframeChange={setRequestedTimeframe}
            detailsOpen={detailsOpen}
            onToggleDetails={() => setDetailsOpen(true)}
            constituentsAvailable={hasActiveMarkets}
            focusedSeriesKey={focusedSeriesKey}
            onClearFocus={clearFocus}
          />
        </div>
        {detailsOpen ? (
          <div
            data-market-explorer-compare-results
            className="absolute inset-0 z-20 flex min-h-0 flex-col overflow-hidden border border-[var(--border-subtle)] bg-[rgba(2,6,23,.96)] shadow-2xl backdrop-blur"
          >
            <div className="flex flex-none flex-col items-center gap-1.5 border-b border-[var(--border-subtle)] bg-[var(--surface-page)]/95 px-3 py-2 sm:px-4">
              {/* The reversible partner of the "View Constituents & Comparison"
                  trigger: same violet language, TOP edge of the expanded
                  workspace, centred. Closing only hides this panel; markets, chart
                  lines, prepared-loader state, the target and fetched pages stay. */}
              <button
                type="button"
                data-market-explorer-hide-details
                onClick={() => setDetailsOpen(false)}
                aria-expanded={true}
                className="min-h-10 rounded-lg border border-violet-400/60 bg-violet-500/[.12] px-4 text-xs font-semibold text-violet-200 shadow-[0_0_16px_rgba(139,92,246,0.35)] transition-colors hover:border-violet-300/85 hover:bg-violet-500/[.24] hover:text-violet-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/80 focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--surface-page)]"
              >
                Hide Constituents &amp; Comparison
              </button>
              <div className="min-w-0 text-center">
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">Constituents &amp; Comparison</h2>
                <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">Inspect the active market composition and compare what is currently visible on the chart.</p>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <MarketExplorerDetails
                series={visibleSeries}
                activeSeriesId={activeDetailSeriesId}
                onInspect={setRequestedDetailSeriesId}
                timeframe={timeframe}
              />
              <MarketExplorerConstituents
                selectedSeries={selectedSeries}
                activeSeriesId={activeDetailSeriesId}
                onSelectSeries={setRequestedDetailSeriesId}
                onEditSeries={beginEdit}
                onRefreshPrepared={(key) => preparedLoader.refresh(key)}
                hiddenSeriesKeys={hiddenSeriesKeys}
                focusedSeriesKey={focusedSeriesKey}
                pageCache={constituentPageCache}
              />
              {activeDetailMarket?.marketType === "set" ? (
                <MarketExplorerContextRanking
                  market={activeDetailMarket}
                  timeframe={timeframe}
                  canUse={canComparePreparedMarkets}
                  onUpgrade={() => setCompareUpgradeVisible(true)}
                />
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      </section>

      <div className="order-6 desk:col-span-2"><MarketExplorerMethodology /></div>
    </div>
  );
}
