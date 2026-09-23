"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MarketExplorerChart from "./MarketExplorerChart";
import MarketExplorerDetails from "./MarketExplorerDetails";
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
  const [detailsOpen, setDetailsOpen] = useState(false);
  const builderDialogRef = useRef(null);
  const [mobileToolsOpen, setMobileToolsOpen] = useState(false);
  const [preparedActiveKeys, setPreparedActiveKeys] = useState(() => initialPreparedKey ? [initialPreparedKey] : []);
  const [loadedPreparedSeries, setLoadedPreparedSeries] = useState([]);
  const [preparedLoadError, setPreparedLoadError] = useState(null);

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
    let outcome = "added";
    setPreparedActiveKeys((current) => {
      if (current.includes(seriesId)) {
        outcome = "removed";
        return current.filter((key) => key !== seriesId);
      }
      return [...current, seriesId].slice(0, 25);
    });
    if (outcome === "added") setRequestedDetailSeriesId(seriesId);
    return outcome;
  }, [canComparePreparedMarkets]);

  // Comparison-capable users accumulate markets. Selecting a third market must
  // never silently delete the first two; active prepared markets toggle in
  // place and can be removed from the same surface that added them.
  const selectPrepared = useCallback((seriesId) => {
    if (canComparePreparedMarkets) return comparePrepared(seriesId);
    setPreparedActiveKeys([seriesId]);
    setRequestedDetailSeriesId(seriesId);
    clearAllSelection();
    clearAllQueries();
    setHiddenSeriesKeys(new Set());
    return "replaced";
  }, [canComparePreparedMarkets, clearAllQueries, clearAllSelection, comparePrepared]);

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
    if (!preparedActiveKeys.length) { setLoadedPreparedSeries([]); setPreparedLoadError(null); return; }
    const controller = new AbortController();
    fetch("/api/market/explorer/prepared", {
      method: "POST", credentials: "include", cache: "no-store", signal: controller.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ marketKeys: preparedActiveKeys }),
    }).then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.message || "Prepared comparison unavailable");
      setLoadedPreparedSeries(buildPreparedSeries(payload.markets, payload.history));
      setPreparedLoadError(null);
    }).catch((error) => {
      // A failed prepared request must not erase previously-loaded valid
      // series. Keep whatever last loaded successfully and surface a
      // visible, bounded error/retry state instead of silently clearing.
      if (error?.name !== "AbortError") setPreparedLoadError(error?.message || "Prepared comparison unavailable");
    });
    return () => controller.abort();
  }, [preparedActiveKeys]);

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
  const activeDetailMarket = selectedSeries.find((entry) => entry.key === activeDetailSeriesId) || null;
  const editingSeries = useMemo(() => querySeries.find((series) => series.instanceId === editingSeriesId) || null, [querySeries, editingSeriesId]);
  const beginEdit = useCallback((series) => {
    setEditingSeriesId(series.instanceId);
    setRequestedDetailSeriesId(series.key);
    if (series.spec?.membershipMode === "explicit") setBuilderOpen(true);
    else { setFiltersOpen(true); setMobileToolsOpen(true); }
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
      className="grid min-w-0 gap-3 desk:grid-cols-[minmax(19rem,22rem)_minmax(0,1fr)] desk:items-start desk:gap-4"
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
          canCompare={canComparePreparedMarkets} onSelect={selectPrepared} onCompare={comparePrepared}
          onBuild={() => { setBuilderMode("exact"); setBuilderOpen(true); }} />
        <div data-market-explorer-sidebar-section="analyze" className="border-t border-[var(--border-subtle)] px-3 py-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">Analyze</p>
          <MarketExplorerRarityMarkets
            directory={preparedDirectory}
            rarityOptions={options?.cardRarities?.rarities || []}
            activeKeys={preparedActiveKeys}
            activeSeries={querySeries}
            canUse={canComparePreparedMarkets}
            onUpgrade={() => setCompareUpgradeVisible(true)}
            onSelect={selectPrepared}
            onAddQuery={addQuery}
            onRemoveQuery={removeQuery}
          />
          <MarketExplorerScreens canUse={canComparePreparedMarkets} activeKeys={preparedActiveKeys}
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
              if (preparedActiveKeys.includes(key)) setPreparedActiveKeys((current) => current.filter((entry) => entry !== key));
              else { if (editingSeries?.key === key) setEditingSeriesId(null); toggleSeries(key); }
            }}
            onEdit={beginEdit}
            canRemove
            hiddenSeriesKeys={hiddenSeriesKeys}
            onToggleVisibility={toggleSeriesVisibility}
            onShowAll={showAllSeries}
            onHideAll={hideAllActiveSeries}
            onClearAll={clearGraph}
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
          {preparedLoadError ? <div role="alert" data-market-explorer-prepared-error className="mb-2 flex items-center justify-between gap-2 rounded-md border border-[rgba(248,113,113,.4)] bg-[rgba(248,113,113,.08)] px-3 py-2 text-xs text-[rgb(248,113,113)]">
            <span>{preparedLoadError}. Previously loaded markets are still shown.</span>
            <button type="button" data-market-explorer-prepared-retry onClick={() => setPreparedActiveKeys((keys) => [...keys])} className="rounded border border-[rgba(248,113,113,.45)] px-2 py-1 font-semibold">Retry</button>
          </div> : null}
          <MarketExplorerChart
            overview={overview}
            selectedSeries={visibleSeries}
            totalActiveCount={selectedSeries.length}
            timeframe={timeframe}
            timeframeLabel={timeframeLabel}
            timeframeOptions={timeframeOptions}
            onTimeframeChange={setRequestedTimeframe}
            onClearGraph={clearGraph}
            detailsOpen={detailsOpen}
            onToggleDetails={() => setDetailsOpen(true)}
          />
        </div>
        {detailsOpen ? (
          <div
            data-market-explorer-compare-results
            className="absolute inset-0 z-20 flex min-h-0 flex-col overflow-hidden border border-[var(--border-subtle)] bg-[rgba(2,6,23,.96)] shadow-2xl backdrop-blur"
          >
            <div className="flex flex-none items-center justify-between gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-page)]/95 px-3 py-2.5 sm:px-4">
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">Constituents &amp; Comparison</h2>
                <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">Inspect the active market composition and compare what is currently visible on the chart.</p>
              </div>
              <button
                type="button"
                data-market-explorer-hide-details
                onClick={() => setDetailsOpen(false)}
                className="min-h-10 flex-none rounded-lg border border-[var(--border-subtle)] px-3 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:border-[rgba(45,212,191,.45)] hover:bg-[rgba(45,212,191,.07)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,.65)]"
              >
                Hide Constituents &amp; Comparison
              </button>
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
