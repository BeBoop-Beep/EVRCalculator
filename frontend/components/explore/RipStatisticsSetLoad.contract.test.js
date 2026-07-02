const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const test = require("node:test");
const assert = require("node:assert/strict");

const ripPageClientPath = path.resolve(__dirname, "RipStatisticsPageClient.jsx");
const marketDashboardStatePath = path.resolve(__dirname, "marketDashboardState.mjs");
const marketClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetMarketClient.js");
const cardsClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetCardsClient.js");
const initialSnapshotsServerPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetInitialSnapshotsServer.js");
const setPageAdaptersPath = path.resolve(__dirname, "../../lib/pokemon/set-page/setPageAdapters.mjs");
const setValueTrendSelectorPath = path.resolve(__dirname, "setValueTrendSelector.mjs");
const setValueContractPath = path.resolve(__dirname, "setValueContract.mjs");
const trendScoresSelectorPath = path.resolve(__dirname, "trendScoresSelector.mjs");
const simulationDriversSelectorPath = path.resolve(__dirname, "simulationDriversSelector.mjs");
const decisionSignalsSelectorPath = path.resolve(__dirname, "decisionSignalsSelector.mjs");
const ripScoreBreakdownSelectorPath = path.resolve(__dirname, "ripScoreBreakdownSelector.mjs");
const dashboardRoutePath = path.resolve(
  __dirname,
  "../../app/api/tcgs/pokemon/sets/[setId]/market/dashboard/route.js"
);
const cardsRoutePath = path.resolve(__dirname, "../../app/api/tcgs/pokemon/sets/[setId]/cards/route.js");
const setPageRoutePath = path.resolve(__dirname, "../../app/api/tcgs/pokemon/sets/[setId]/page/route.js");
const explorePageServicePath = path.resolve(__dirname, "../../../backend/db/services/explore_page_service.py");
const snapshotServicePath = path.resolve(
  __dirname,
  "../../../backend/db/services/pokemon_public_snapshot_service.py"
);
const snapshotBuilderPath = path.resolve(__dirname, "../../../backend/scripts/pokemon_snapshot_builders.py");
const backendApiPath = path.resolve(__dirname, "../../../backend/api/main.py");

test("set detail dependent fetches use one stable resolved set resource id", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("function getResolvedPokemonSetResourceId"));
  assert.ok(source.includes("function setIdentityMatchesTarget"));
  assert.ok(source.includes("function isSetStateForActiveSet"));
  assert.ok(source.includes("const resolvedSetResourceId = useMemo("));
  assert.ok(source.includes("const setId = resolvedSetResourceId;"));
  assert.ok(source.includes('routeSetId: requestedTargetId'));
  assert.ok(source.includes('resolvedSetId: setId'));
});

test("SetShellContract includes normalized setValueSummary from initial payload", async () => {
  const { adaptSetShell } = await import(pathToFileURL(setPageAdaptersPath).href);
  const shell = adaptSetShell({
    summary: { currentChecklistSetValue: 123.45 },
    setValueHistoriesByScope: {
      standard: [
        { date: "2026-06-01", setValue: 100 },
        { date: "2026-06-30", setValue: 123.45 },
      ],
    },
    meta: { asOfDate: "2026-06-30" },
  });

  assert.equal(shell.setValueSummary.currentValue, 123.45);
  assert.equal(shell.setValueSummary.valueScope, "standard");
  assert.equal(shell.setValueSummary.asOf, "2026-06-30");
  assert.equal(shell.setValueSummary.source, "set_value_history");
  assert.ok("delta30dAmount" in shell.setValueSummary);
  assert.ok("confidence" in shell.setValueSummary);
});

test("hero set value is seeded from shell contract instead of overview-only state", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const shellIndex = source.indexOf("const setShellContract = useMemo(");
  const summaryIndex = source.indexOf("const shellSetValueSummary = setShellContract?.setValueSummary");
  const heroHistoryIndex = source.indexOf("const heroSetValueHistory = {");
  const canonicalIndex = source.indexOf("sourcePrefix: \"direct_set_value_history\"");
  const overviewRenderIndex = source.indexOf("<SetValueTrendCard", canonicalIndex);

  assert.ok(shellIndex >= 0);
  assert.ok(summaryIndex > shellIndex);
  assert.ok(heroHistoryIndex > summaryIndex);
  assert.ok(canonicalIndex > heroHistoryIndex);
  assert.ok(overviewRenderIndex > canonicalIndex);
  assert.ok(source.includes("shellSetValueSummary?.currentValue"));
  assert.ok(!source.slice(heroHistoryIndex, canonicalIndex).includes("activeMarketDashboardDerivedState"));
});

test("title-card sparkline/30D delta fall back to the shell contract's compact history before any lazy fetch has loaded", () => {
  // Regression guard: the current-value number reaching the title card from
  // setShellContract (see the test above) is not enough on its own — the
  // sparkline and 30D delta/percent read from activeSetValueContract's
  // "standard" scope, which was built exclusively from the direct set-value
  // fetch and Overview's market dashboard fetch. Both are lazy client
  // fetches that haven't run on Insights/Pull-Rates first load, so the
  // scope stayed empty ("History pending", 30D N/A) even though the shell
  // payload's checklist history was already sitting in memory.
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const directStateIndex = source.indexOf("const activeDirectSetValueState =");
  const loadedScopesIndex = source.indexOf("const activeDirectSetValueLoadedScopes = new Set(");
  const historiesByScopeIndex = source.indexOf("const activeSetValueHistoriesByScope = {");
  const visiblePointsIndex = source.indexOf("const shellSetValueVisiblePoints = Array.isArray(setShellContract?.setValueSummary?.compact?.visiblePoints)");
  const standardHistoryIndex = source.indexOf("const activeSetValueStandardHistory =");

  assert.ok(directStateIndex >= 0, "activeDirectSetValueState must exist");
  assert.ok(loadedScopesIndex > directStateIndex);
  assert.ok(historiesByScopeIndex > loadedScopesIndex);
  assert.ok(visiblePointsIndex > historiesByScopeIndex, "shell visible-points fallback must be derived after the direct/market histories are assembled");
  assert.ok(standardHistoryIndex > visiblePointsIndex, "the standard history must be finalized after the shell fallback is available");

  const fallbackSource = source.slice(historiesByScopeIndex, standardHistoryIndex);
  assert.ok(
    fallbackSource.includes("setShellContract.setValueSummary.compact.visiblePoints"),
    "must source the fallback from setShellContract's compact visible points"
  );
  assert.ok(
    fallbackSource.includes("activeSetValueHistoriesByScope[CANONICAL_SET_VALUE_SCOPE] || []).length === 0"),
    "must only apply the shell fallback when the direct/market scope has no points yet"
  );
  assert.ok(
    fallbackSource.includes("activeSetValueHistoriesByScope[CANONICAL_SET_VALUE_SCOPE] = shellSetValueVisiblePoints;"),
    "must seed the standard scope from the shell fallback so buildSetValueContract can compute delta30d from it"
  );

  const standardHistoryEnd = source.indexOf("const activeSetValueAvailableScopes", standardHistoryIndex);
  const standardHistorySource = source.slice(standardHistoryIndex, standardHistoryEnd);
  assert.ok(
    standardHistorySource.includes("activeSetValueHistoriesByScope[CANONICAL_SET_VALUE_SCOPE] || []"),
    "the standard history passed into the contract must also fall back to the shell-seeded scope, not just the market dashboard's raw history"
  );
});

test("Set Value Trend chart key changes with set id, scope, window, dates, and length", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const componentStart = source.indexOf("function SetValueTrendCard");
  const componentEnd = source.indexOf("function OverviewMetricTile", componentStart);
  const componentSource = source.slice(componentStart, componentEnd);

  assert.ok(componentSource.includes("setId,"));
  assert.ok(componentSource.includes("const seriesStartDate = firstPoint?.date || \"start\""));
  assert.ok(componentSource.includes("const seriesEndDate = lastPoint?.date || \"latest\""));
  assert.ok(componentSource.includes("`${setId || \"set\"}-${selectedTrend.scope}-${effectiveWindowKey || \"window\"}-${seriesStartDate}-${seriesEndDate}-${chartPoints.length}`"));
  assert.ok(source.includes("isAnimationActive={false}"));
  assert.ok(componentSource.includes("setSelectedWindowKey(null)"));
});

test("Set Value Trend selector returns one coherent selected object per window and scope", async () => {
  const { selectOverviewSetValueTrendByScope } = await import(pathToFileURL(setValueTrendSelectorPath).href);
  const selected = selectOverviewSetValueTrendByScope({
    historiesByScope: {
      standard: [
        { date: "2026-06-01", setValue: 100 },
        { date: "2026-06-02", setValue: 105 },
      ],
      hits: [
        { date: "2026-06-01", setValue: 80 },
        { date: "2026-06-02", setValue: 88 },
      ],
    },
    selectedScope: "hits",
    selectedWindowKey: "30D",
  });

  assert.equal(selected.scope, "hits");
  assert.equal(selected.metricLabel, "Hits Set Value");
  assert.equal(selected.currentValue, 88);
  assert.equal(selected.series.at(-1).setValue, 88);
  assert.equal(selected.diagnostics.source, "setValueHistoriesByScope.hits");
});

test("Set Value Contract keeps current value available while history is empty", async () => {
  const { buildSetValueContract, selectSetValueTrendFromContract } = await import(
    pathToFileURL(setValueContractPath).href
  );

  const contract = buildSetValueContract({
    setId: "black-bolt",
    current: {
      value: 5329.67,
      asOf: "2026-06-25",
      source: "summary.currentChecklistSetValue",
    },
    historiesByScope: { standard: [] },
    status: "empty",
  });
  const selected = selectSetValueTrendFromContract({ contract, selectedScope: "standard" });

  assert.equal(contract.current.value, 5329.67);
  assert.equal(contract.current.asOf, "2026-06-25");
  assert.equal(contract.scopes.standard.status, "partial");
  assert.equal(contract.scopes.standard.history.length, 0);
  assert.equal(selected.currentValue, 5329.67);
  assert.equal(selected.status, "partial");
  assert.equal(selected.hasTrend, false);
});

test("Set Value Contract scope history is windowed to 30D by default, not the full fetched range", async () => {
  // Regression guard: contract.scopes.standard.history previously returned
  // the full normalizedHistoriesByScope range (e.g. 3+ months), which is
  // what the title-card mini sparkline reads (setHeaderSummarySelector's
  // getSparklinePoints prefers contractStandard.history first). That made
  // the sparkline show a multi-month range while the same card's 30D
  // Delta/30D % boxes were correctly 30-day figures. The full range must
  // still be reachable via contract.historiesByScope for Overview's window
  // switcher (3M/6M/etc), which reads that field directly instead.
  const { buildSetValueContract, selectSetValueTrendFromContract } = await import(
    pathToFileURL(setValueContractPath).href
  );

  const history = [];
  const start = new Date(Date.UTC(2026, 3, 11)); // 2026-04-11
  const end = new Date(Date.UTC(2026, 6, 2)); // 2026-07-02
  for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    history.push({ date: d.toISOString().slice(0, 10), setValue: 5000 });
  }

  const contract = buildSetValueContract({
    setId: "prismatic-evolutions",
    current: { value: 5000, asOf: "2026-07-02", source: "summary.currentChecklistSetValue" },
    historiesByScope: { standard: history },
    status: "success",
  });

  assert.ok(
    contract.scopes.standard.history.length < history.length,
    "scope history must be windowed, not the full multi-month range"
  );
  assert.ok(
    contract.scopes.standard.history.length <= 31,
    "scope history must be windowed to roughly 30 days"
  );
  assert.equal(contract.scopes.standard.history.at(-1)?.date, "2026-07-02", "windowed history must end on the latest point");
  assert.equal(contract.scopes.standard.history[0]?.date, "2026-06-03", "windowed history must start ~30 days before the latest point");
  assert.equal(
    contract.historiesByScope.standard.length,
    history.length,
    "the full range must remain available on contract.historiesByScope for Overview's window switcher"
  );

  const overview3M = selectSetValueTrendFromContract({ contract, selectedScope: "standard", selectedWindowKey: "3M" });
  assert.equal(
    overview3M.series.length,
    history.length,
    "Overview must still be able to select a wider window (e.g. 3M) from the full range"
  );
});

test("header and overview set value read from the same Set Value Contract", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const contractStart = source.indexOf("const activeSetValueContract = useMemo(");
  const headerStart = source.indexOf("const standardSetValueScope = activeSetValueContract.scopes.standard", contractStart);
  const overviewRenderStart = source.indexOf("<SetValueTrendCard", headerStart);
  const overviewRenderEnd = source.indexOf("/>", overviewRenderStart);
  const overviewRenderSource = source.slice(overviewRenderStart, overviewRenderEnd);

  assert.ok(contractStart >= 0);
  assert.ok(headerStart > contractStart);
  assert.ok(source.includes("const setValue = activeSetValueContract.current.value ?? canonicalSetValueMetrics.value"));
  assert.ok(source.includes("setValueContract={activeSetValueContract}"));
  assert.ok(overviewRenderSource.includes("setValueContract={activeSetValueContract}"));
  assert.ok(source.includes("Current value is available; historical trend is still loading/unavailable."));
});

test("cards tab fetch caches normalized payload and does not clear stale cards on failure", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const fetchStart = source.indexOf("getPokemonSetCards(setId)");
  const thenStart = source.indexOf(".then((payload) => {", fetchStart);
  const catchStart = source.indexOf(".catch((error) => {", fetchStart);
  const thenSource = source.slice(thenStart, catchStart);
  const catchEnd = source.indexOf("});", catchStart);
  const catchSource = source.slice(catchStart, catchEnd);

  assert.ok(thenSource.includes("checklistCacheRef.current.set(setId, payload)"));
  assert.ok(catchSource.includes("previous.setId === setId && previous.cards.length > 0"));
  assert.ok(catchSource.includes('"success_stale"'));
  assert.ok(catchSource.includes("previous.cards"));
});

test("timeout fallback set page payload hydrates with a no-store client retry", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("function isSetPageTransportFallback"));
  assert.ok(source.includes("function fetchPokemonSetPageSnapshot"));
  assert.ok(source.includes('/page?retry=1'));
  assert.ok(source.includes('cache: "no-store"'));
  assert.ok(source.includes("setExplorePayload(payload || null)"));
  assert.ok(source.includes('debugSetPagePerf("set_page.timeout_retry_start"'));
  assert.ok(source.includes('debugSetPagePerf("set_page.timeout_retry_ready"'));
});

test("timeout fallback payload only defers sections that require the full set page snapshot", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  // The client-side retry path is still present for Decision Signals / full-snapshot sections
  assert.ok(source.includes('debugSetPagePerf("set.prefetch_deferred"'));
  assert.ok(source.includes("function isSetPageTransportFallback"));
  assert.ok(source.includes("function fetchPokemonSetPageSnapshot"));
  // shouldPauseSetDetailDependentFetches still exists for snapshot-dependent sections and adjacent prefetch
  assert.ok(source.includes("const shouldPauseSetDetailDependentFetches ="));
  // Module fetches (cards, market, value) use canFetchSetDetailModules — not gated on transport fallback
  assert.ok(source.includes("const canFetchSetDetailModules ="));
  // The "loading" state driven by isTimeoutFallbackPayload is gone from the module-level guards
  assert.ok(!source.includes('createSetValueHistoryState({ status: isTimeoutFallbackPayload ? "loading" : "empty", setId })'));
  assert.ok(!source.includes('status: isTimeoutFallbackPayload ? "loading" : "empty"'));
  assert.ok(!source.includes('type: isTimeoutFallbackPayload ? "loading" : "reset"'));
});

test("primary snapshot fallback still gates adjacent prefetch and simulation-dependent sections", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const warmupStart = source.indexOf("const warmSetDetailResources = useCallback");
  const warmupEnd = source.indexOf("const outcomeDistributionInfo", warmupStart);
  const warmupSource = source.slice(warmupStart, warmupEnd);
  const cardsEffectStart = source.indexOf("getPokemonSetCards(setId)");
  const cardsGuardStart = source.lastIndexOf("if (!canFetchSetDetailModules)", cardsEffectStart);
  const valueHistoryStart = source.indexOf("getPokemonSetValueHistory(setId, { days: 365, scope })");
  const valueGuardStart = source.lastIndexOf("if (!canFetchSetDetailModules)", valueHistoryStart);
  const marketStart = source.indexOf("getPokemonSetMarketDashboard(setId, { window: dashboardSourceWindow })");
  const marketGuardStart = source.lastIndexOf("if (!canFetchSetDetailModules)", marketStart);

  assert.ok(source.includes("function isSetPagePrimarySnapshotUnavailable"));
  assert.ok(source.includes("const isPrimarySnapshotReady ="));
  assert.ok(source.includes("function hasRealSetPageIdentity"));
  assert.ok(source.includes("const shouldPauseSetDetailDependentFetches ="));
  assert.ok(source.includes("const canFetchSetDetailModules ="));
  assert.ok(warmupSource.includes("if (!canFetchSetDetailModules)"));
  assert.ok(warmupSource.includes('deferredReason: !resolvedSetResourceId ? "set_id_unresolved" : "set_identity_mismatch"'));
  assert.ok(warmupSource.includes("if (!includeAdjacent || !activeSetModulesStable || shouldPauseSetDetailDependentFetches"));
  assert.ok(cardsGuardStart >= 0 && cardsGuardStart < cardsEffectStart);
  assert.ok(valueGuardStart >= 0 && valueGuardStart < valueHistoryStart);
  assert.ok(marketGuardStart >= 0 && marketGuardStart < marketStart);
});

test("initial bootstrap does not request adjacent set fanout", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const bootstrapStart = source.indexOf('debugSetPagePerf("set.bootstrap_ready"');
  const bootstrapEnd = source.indexOf("}, [setDetailMode", bootstrapStart);
  const bootstrapSource = source.slice(bootstrapStart, bootstrapEnd);

  assert.ok(source.includes("const activeSetModulesStable ="));
  assert.ok(bootstrapSource.includes('warmSetDetailResources(setId, { includeAdjacent: false, reason: "bootstrap" })'));
  assert.ok(!bootstrapSource.includes("includeAdjacent: true"));
});

test("slug fallback can adopt canonical set identity from successful set page snapshot", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const identityTokensStart = source.indexOf("function getSetIdentityTokens");
  const identityTokensEnd = source.indexOf("function setIdentityMatchesTarget", identityTokensStart);
  const identitySource = source.slice(identityTokensStart, identityTokensEnd);
  const resolverStart = source.indexOf("function getResolvedPokemonSetResourceId");
  const resolverEnd = source.indexOf("function isSetStateForActiveSet", resolverStart);
  const resolverSource = source.slice(resolverStart, resolverEnd);

  assert.ok(identitySource.includes("identity.name"));
  assert.ok(identitySource.includes("identity.set_name"));
  assert.ok(source.includes("explorePayload?.set ||"));
  assert.ok(source.includes("explorePayload?.summary ||"));
  assert.ok(resolverSource.indexOf("if (snapshotResourceId") < resolverSource.indexOf("if (requestedResourceId)"));
});

test("Simulation Drivers selector reads top_hits from current payload shape", async () => {
  const { selectSimulationDrivers } = await import(pathToFileURL(simulationDriversSelectorPath).href);
  const selected = selectSimulationDrivers({
    top_hits: [{ card_name: "Chase Card", ev_contribution: 1.23, current_near_mint_price: 45 }],
    meta: { sources: { simulation_input_cards: "OK" }, warnings: [] },
  });

  assert.equal(selected.rows.length, 1);
  assert.equal(selected.rows[0].card_name, "Chase Card");
  assert.equal(selected.sourceUsed, "top_hits");
  assert.equal(selected.diagnostics.warning, null);
});

test("Simulation Drivers fallback without top_hits exposes backend diagnostic warning", async () => {
  const { selectSimulationDrivers } = await import(pathToFileURL(simulationDriversSelectorPath).href);
  const selected = selectSimulationDrivers({
    meta: {
      sources: {
        explore_rip_statistics_latest: "UNAVAILABLE_FALLBACK",
        simulation_latest_by_target: "OK",
        simulation_input_cards: "NO_ROWS",
      },
      warnings: [],
    },
  });

  assert.equal(selected.rows.length, 0);
  assert.equal(selected.diagnostics.fallbackUsed, true);
  assert.equal(selected.diagnostics.missingBackendSource, "simulation_input_cards");
  assert.match(selected.diagnostics.warning, /simulation_input_cards/);
});

test("Simulation Drivers timeout fallback reports loading instead of unavailable top_hits", async () => {
  const { selectSimulationDrivers } = await import(pathToFileURL(simulationDriversSelectorPath).href);
  const selected = selectSimulationDrivers({
    top_hits: [],
    meta: {
      requestTimeout: true,
      isTransportFallback: true,
      fallback: true,
      fallbackReason: "request_timeout",
      sources: { setPage: "timeout_fallback" },
      warnings: ["Set page snapshot request timed out; retrying."],
      errors: [{ code: "SET_PAGE_PAYLOAD_TIMEOUT" }],
    },
  });

  assert.equal(selected.rows.length, 0);
  assert.equal(selected.diagnostics.status, "loading");
  assert.equal(selected.diagnostics.requestTimeout, true);
  assert.equal(selected.diagnostics.transportFallback, true);
  assert.deepEqual(selected.diagnostics.missingFields, []);
  assert.equal(selected.diagnostics.missingBackendSource, null);
  assert.doesNotMatch(selected.diagnostics.warning, /unavailable: no top_hits/);
  assert.match(selected.diagnostics.warning, /loading: set page snapshot request timed out; retrying/);
});

test("Simulation Drivers explicit missing snapshot still reports unavailable top_hits", async () => {
  const { selectSimulationDrivers } = await import(pathToFileURL(simulationDriversSelectorPath).href);
  const selected = selectSimulationDrivers({
    top_hits: [],
    meta: {
      requestTimeout: false,
      fallback: true,
      fallbackReason: "snapshot_missing",
      sources: { setPage: "fallback" },
      warnings: [],
      errors: [{ code: "SET_PAGE_PAYLOAD_NOT_FOUND", status: 404 }],
    },
  });

  assert.equal(selected.rows.length, 0);
  assert.equal(selected.diagnostics.status, "unavailable");
  assert.deepEqual(selected.diagnostics.missingFields, ["top_hits"]);
  assert.match(selected.diagnostics.warning, /no top_hits rows/);
});

test("Simulation Drivers selector renders stale preserved top_hits and exposes freshness metadata", async () => {
  const { selectSimulationDrivers } = await import(pathToFileURL(simulationDriversSelectorPath).href);
  const selected = selectSimulationDrivers({
    top_hits: [{ card_name: "Preserved Chase", ev_contribution: 1.23, current_near_mint_price: 45 }],
    meta: {
      sources: { simulation_input_cards: "FAILED" },
      warnings: ["Simulation Drivers unavailable: simulation_input_cards FAILED"],
      sectionFreshness: {
        simulationDrivers: {
          status: "stale",
          dataAsOf: "2026-06-24T11:00:00+00:00",
          lastSuccessfulAt: "2026-06-24T12:00:00+00:00",
          attemptedAt: "2026-06-25T12:00:00+00:00",
          source: "simulation_input_cards_with_near_mint_price/run-1",
          reason: "current snapshot build did not include valid top_hits",
        },
      },
    },
  });

  assert.equal(selected.rows.length, 1);
  assert.equal(selected.rows[0].card_name, "Preserved Chase");
  assert.equal(selected.diagnostics.warning, null);
  assert.equal(selected.diagnostics.missingBackendSource, null);
  assert.equal(selected.diagnostics.freshnessStatus, "stale");
  assert.equal(selected.diagnostics.dataAsOf, "2026-06-24T11:00:00+00:00");
  assert.equal(selected.diagnostics.lastSuccessfulAt, "2026-06-24T12:00:00+00:00");
});

test("Decision Signals selector returns stable rows from summary pillars while market is loading", async () => {
  const { selectDecisionSignals } = await import(pathToFileURL(decisionSignalsSelectorPath).href);
  const selected = selectDecisionSignals({
    pillarSignals: [
      { title: "Profit", score: 71, rankTier: "B", rankValue: 12, highlight: "Playable return profile" },
      { title: "Safety", score: 65, rankTier: "B", rankValue: 20, highlight: "Manageable downside" },
    ],
  });

  assert.equal(selected.rows.length, 2);
  assert.equal(selected.rows[0].label, "Profitability");
  assert.equal(selected.sourceUsed, "summary+pillarSignals");
});

test("Trend Scores selector handles missing previous points without crashing", async () => {
  const { selectTrendScores } = await import(pathToFileURL(trendScoresSelectorPath).href);
  const summary = {
    relative_pack_score: 72,
    relative_profit_score: 66,
    safety_score: 58,
    current_checklist_set_value: 5329.67,
    prob_profit: 0.42,
  };

  for (const previousPoint of [null, undefined, {}]) {
    const selected = selectTrendScores({ summary, previousPoint, setValueMetrics: null });

    assert.equal(selected.ripScore.trend, "unknown");
    assert.equal(selected.ripScore.isImprovement, null);
    assert.equal(selected.profitScore.trend, "unknown");
    assert.equal(selected.setValue.trend, "unknown");
    assert.equal(selected.probProfit.trend, "unknown");
  }
});

test("Trend Scores selector preserves valid comparisons and partial set value metrics", async () => {
  const { selectTrendScores } = await import(pathToFileURL(trendScoresSelectorPath).href);
  const selected = selectTrendScores({
    summary: {
      relative_pack_score: 72,
      relative_profit_score: 66,
      current_checklist_set_value: 120,
      prob_profit: 0.42,
    },
    previousPoint: {
      relativePackScore: 70,
      relativeProfitScore: 70,
      setValue: 100,
      probProfit: 0.2,
    },
    setValueMetrics: { value: 125 },
  });

  assert.equal(selected.ripScore.trend, "up");
  assert.equal(selected.ripScore.isImprovement, true);
  assert.equal(selected.profitScore.trend, "down");
  assert.equal(selected.profitScore.isImprovement, false);
  assert.equal(selected.setValue.trend, "up");
  assert.equal(selected.setValue.isImprovement, true);
  assert.equal(selected.probProfit.trend, "up");
});

test("Trend Scores selector tolerates null summary and partial set value metrics", async () => {
  const { selectTrendScores } = await import(pathToFileURL(trendScoresSelectorPath).href);

  const nullSummarySelection = selectTrendScores({
    summary: null,
    previousPoint: null,
    setValueMetrics: { value: 80 },
  });
  const partialSetValueSelection = selectTrendScores({
    summary: { current_checklist_set_value: 80 },
    previousPoint: { setValue: 75 },
    setValueMetrics: {},
  });

  assert.equal(nullSummarySelection.ripScore.trend, "unknown");
  assert.equal(nullSummarySelection.setValue.trend, "unknown");
  assert.equal(partialSetValueSelection.setValue.trend, "up");
  assert.equal(partialSetValueSelection.setValue.isImprovement, true);
});

test("RIP Score Breakdown selector exposes missing rank diagnostics", async () => {
  const { selectRipScoreBreakdown } = await import(pathToFileURL(ripScoreBreakdownSelectorPath).href);
  const selected = selectRipScoreBreakdown({
    relative_profit_score: 70,
    profit_tier: "B",
  });

  const profit = selected.rows.find((row) => row.title === "Profit");
  assert.equal(profit.score, 70);
  assert.equal(profit.rankValue, null);
  assert.match(profit.rankDiagnostic, /Rank unavailable/);
  assert.ok(selected.diagnostics.missingFields.includes("profit_rank"));
});

test("RIP Score Breakdown selector keeps current metrics when trends are missing", async () => {
  const { selectRipScoreBreakdown } = await import(pathToFileURL(ripScoreBreakdownSelectorPath).href);
  const selected = selectRipScoreBreakdown(
    {
      relative_profit_score: 70,
      profit_rank: 4,
      profit_tier: "A",
      relative_safety_score: 61,
      safety_rank: 12,
      safety_tier: "B",
    },
    null
  );

  const profit = selected.rows.find((row) => row.title === "Profit");
  const safety = selected.rows.find((row) => row.title === "Safety");

  assert.equal(profit.score, 70);
  assert.equal(profit.rankValue, 4);
  assert.equal(profit.rankTier, "A");
  assert.equal(profit.scoreTrend, null);
  assert.equal(safety.score, 61);
  assert.equal(safety.rankValue, 12);
});

test("backend top hits warning includes diagnostic source context", () => {
  const source = fs.readFileSync(explorePageServicePath, "utf8");
  const activeDefinitionStart = source.lastIndexOf("def get_explore_page_payload(");
  const activeSource = source.slice(activeDefinitionStart);

  assert.ok(activeSource.includes('sources["simulation_input_cards"] = "OK" if top_hits else "NO_ROWS"'));
  assert.ok(activeSource.includes("Simulation Drivers unavailable: simulation_input_cards_with_near_mint_price "));
  assert.ok(activeSource.includes("returned no rows for calculation_run_id={run_id}"));
  assert.ok(activeSource.includes("Failed to load top hits from simulation_input_cards_with_near_mint_price"));
  assert.ok(activeSource.includes("calculation_run_id={run_id}"));
});

test("set page snapshot service skips live Simulation Drivers repair during route render", () => {
  const source = fs.readFileSync(snapshotServicePath, "utf8");

  assert.ok(source.includes("def _mark_missing_simulation_drivers_without_live_repair"));
  assert.ok(source.includes('sources.get("simulation_input_cards") not in {"FAILED", "NO_ROWS"}'));
  assert.ok(source.includes('"Simulation Drivers are unavailable in this set page snapshot; skipped live repair during route render."'));
  assert.ok(source.includes('"simulationDriversRepairSkipped"'));
  assert.ok(source.includes('"no_live_assembly_during_route_render"'));
  assert.ok(source.includes("payload = _mark_missing_simulation_drivers_without_live_repair(payload)"));
  assert.ok(!source.includes('get_explore_page_payload("set", resolved_set_id)'));
  assert.ok(!source.includes('"live_get_explore_page_payload"'));
});

test("set detail resolver follows route or selected target instead of stale snapshot metadata", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const resolverStart = source.indexOf("function getResolvedPokemonSetResourceId");
  const resolverEnd = source.indexOf("function isSetStateForActiveSet", resolverStart);
  const resolverSource = source.slice(resolverStart, resolverEnd);
  const selectedReturnIndex = resolverSource.indexOf("return selectedResourceId");
  const requestedReturnIndex = resolverSource.indexOf("return requestedResourceId");
  const snapshotReturnIndex = resolverSource.indexOf("return snapshotResourceId");
  const snapshotGuardIndex = resolverSource.indexOf("if (snapshotResourceId && setIdentityMatchesTarget(snapshotIdentity, requestedResourceId))");

  assert.ok(resolverStart >= 0);
  assert.ok(resolverEnd > resolverStart);
  assert.ok(resolverSource.includes("setIdentityMatchesTarget(selectedTarget, requestedResourceId)"));
  assert.ok(selectedReturnIndex >= 0);
  assert.ok(snapshotGuardIndex > selectedReturnIndex);
  assert.ok(snapshotReturnIndex > snapshotGuardIndex);
  assert.ok(requestedReturnIndex > snapshotReturnIndex);
});

test("set value trend uses the active market dashboard id through dropdown set switches", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const activeHistoryStart = source.indexOf("const activeMarketDashboardState");
  const activeHistoryEnd = source.indexOf("const fallbackSetValueAsOf", activeHistoryStart);
  const activeHistorySource = source.slice(activeHistoryStart, activeHistoryEnd);

  assert.ok(activeHistoryStart >= 0);
  assert.ok(activeHistoryEnd > activeHistoryStart);
  assert.ok(activeHistorySource.includes("marketDashboardState.setId === resolvedSetResourceId"));
  assert.ok(activeHistorySource.includes("resolvedSetResourceId"));
  assert.ok(activeHistorySource.includes("activeMarketDashboardDerivedState.setValue"));
  assert.ok(activeHistorySource.includes("activeMarketDashboardDerivedState.topCards"));
  assert.ok(activeHistorySource.includes("activeDirectSetValueState"));
  assert.ok(activeHistorySource.includes("activeSetValueHistoriesByScope"));
  assert.ok(!activeHistorySource.includes("selectedTarget"));
  assert.ok(source.includes('debugSetPagePerf("set_value_trend.render_state"'));
  assert.ok(source.includes("standardHistoryLength"));
});

test("set value history direct-fetch effect requests only the scopes the active tab needs", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const directFetchStart = source.indexOf('debugSetPagePerf("set_value.direct_fetch_start"');
  const directFetchEnd = source.indexOf('debugSetPagePerf("set_value.direct_fetch_ready"', directFetchStart);
  const directFetchSource = source.slice(directFetchStart, directFetchEnd);
  const directEffectStart = source.lastIndexOf("useEffect(() => {", directFetchStart);
  const directEffectEnd = source.indexOf("\n\n  useEffect(() => {", directFetchEnd);
  const directEffectSource = source.slice(directEffectStart, directEffectEnd);

  assert.ok(source.includes("getPokemonSetValueHistory"));
  assert.ok(source.includes("const [setValueHistoryState, setSetValueHistoryState] = useState"));
  assert.ok(directFetchStart >= 0);
  assert.ok(directFetchEnd > directFetchStart);
  assert.ok(directEffectSource.includes("const seededSetValueFromSnapshot ="));
  // Only "standard" (header/title) is always desired; hits/top10 are added
  // only when the overview Set Value Trend card is active — not an
  // unconditional fanout over every SET_VALUE_SCOPE_OPTIONS entry.
  assert.ok(directEffectSource.includes("const desiredScopes = Array.from("));
  assert.ok(directEffectSource.includes('setDetailTab === "overview" ? [setValueTrendScope || CANONICAL_SET_VALUE_SCOPE] : []'));
  assert.ok(directEffectSource.includes("const requestedScopes = desiredScopes.filter((scope) => !seededLoadedScopes.includes(scope));"));
  assert.ok(!directEffectSource.includes("const requestedScopes = SET_VALUE_SCOPE_OPTIONS.map((scope) => scope.key).filter("), "must not unconditionally request every scope");
  assert.ok(directFetchSource.includes("requestedScopes.map"));
  assert.ok(directFetchSource.includes("CANONICAL_SET_VALUE_SCOPE"));
  assert.ok(directEffectSource.includes("resolvedSetResourceId"));
  assert.ok(directEffectSource.includes("if (!canFetchSetDetailModules)"));
});

test("set value history direct-fetch effect prefers live market dashboard state over a raw cache read", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const directEffectStart = source.indexOf("const cachedDashboardPayload = getCachedPokemonSetMarketDashboard(setId,");
  const requestedScopesEnd = source.indexOf("const requestedScopes = desiredScopes.filter", directEffectStart);
  const seedSource = source.slice(directEffectStart, requestedScopesEnd);

  assert.ok(directEffectStart >= 0, "value-history effect's seed-merge block must exist");
  assert.ok(seedSource.includes("activeMarketDashboardState.setId === setId"), "must check the live market dashboard state belongs to the active set");
  assert.ok(seedSource.includes("activeMarketDashboardDerivedState.setValue.historiesByScope"), "must read scopes from the live market dashboard derived state first");
  assert.ok(seedSource.includes("adaptSetValueHistoriesFromSources"), "must still fall back to the raw cache/explorePayload adapter when live state is empty");
});

test("value-history, market-dashboard, and cards fetch results are ignored if the active set changed before they resolved", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const guardCall = "isSetStateForActiveSet(setId, { requestedTargetId, selectedTarget, resolvedSetResourceId: activeSetResourceIdRef.current })";
  assert.ok(source.includes(`if (!${guardCall}) {`), "the shared stale-active-set guard shape must appear before applying fetched state");
  assert.ok(source.includes('debugSetPagePerf("set_value.direct_fetch_stale"'), "value-history fetch must guard against a stale active set before applying results");
  assert.ok(source.includes('debugSetPagePerf("market.tab_fetch_stale"'), "market dashboard fetch must guard against a stale active set before applying results");
  assert.ok(source.includes('debugSetPagePerf("cards.tab_fetch_stale"'), "cards fetch must guard against a stale active set before applying results");

  const occurrences = source.split(`if (!${guardCall}) {`).length - 1;
  assert.equal(occurrences, 3, "cards, market dashboard, and value-history fetches must each carry this stale-set guard");
});

test("warmSetDetailResources performs route prefetch only — no cards/market/value-history data fetch", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const warmupStart = source.indexOf("const warmSetDetailResources = useCallback");
  const warmupEnd = source.indexOf("const outcomeDistributionInfo", warmupStart);
  const warmupSource = source.slice(warmupStart, warmupEnd);

  assert.ok(warmupStart >= 0);
  assert.ok(warmupEnd > warmupStart);
  // warmSetDetailResources previously fetched cards + market dashboard data
  // (and, at one point, value-history) for hovered/adjacent/bootstrap sets
  // the user may never open, fanning out /cards + /market/dashboard (+
  // downstream /market/value-history) requests across many set ids on every
  // switch. It must now do route prefetch only; each tab's own effect fetches
  // its module lazily once that tab actually renders for the active set.
  assert.ok(!warmupSource.includes("getPokemonSetValueHistory"), "warmup must not call getPokemonSetValueHistory");
  assert.ok(!warmupSource.includes("SET_VALUE_SCOPE_OPTIONS.map((scope) =>"), "warmup must not fan out over SET_VALUE_SCOPE_OPTIONS");
  assert.ok(!warmupSource.includes("prefetchPokemonSetCards"), "warmup must not prefetch cards data");
  assert.ok(!warmupSource.includes("prefetchPokemonSetMarketDashboard"), "warmup must not prefetch market dashboard data");
  assert.ok(!warmupSource.includes("getPokemonSetCards("), "warmup must not fetch cards data directly either");
  assert.ok(!warmupSource.includes("getPokemonSetMarketDashboard("), "warmup must not fetch market dashboard data directly either");
  assert.ok(warmupSource.includes("router.prefetch(targetHref)"), "warmup still route-prefetches the destination page");
});

test("warmSetDetailResources data prefetch removal is not reintroduced via a background market-dashboard fetch on non-overview tabs", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(!source.includes("prefetchPokemonSetCards"), "prefetchPokemonSetCards must not be imported or called anywhere");
  assert.ok(!source.includes("prefetchPokemonSetMarketDashboard"), "prefetchPokemonSetMarketDashboard must not be imported or called anywhere");

  const marketEffectStart = source.indexOf("const shouldRenderMarketData = setDetailTab ===");
  const marketEffectEnd = source.indexOf("let isCancelled = false;", marketEffectStart);
  const marketEffectSource = source.slice(marketEffectStart, marketEffectEnd);
  assert.ok(marketEffectStart >= 0, "market dashboard effect must exist");
  assert.ok(
    marketEffectSource.includes("if (!shouldRenderMarketData) {"),
    "must still gate the live fetch on the overview tab being active"
  );
});

test("one market dashboard payload produces value trend and top chase card data", async () => {
  const { buildMarketDashboardStateFromPayload } = await import(pathToFileURL(marketDashboardStatePath).href);
  const payload = {
    topChaseCards: [{ id: "card-1", name: "Chase", marketPrice: 42 }],
    setValueHistoriesByScope: {
      standard: [{ date: "2026-06-01", setValue: 100 }],
      hits: [{ date: "2026-06-01", setValue: 80 }],
    },
    availableScopes: [{ key: "standard" }, { key: "hits" }],
    meta: { source: "snapshot" },
  };

  const marketState = buildMarketDashboardStateFromPayload(payload);

  assert.equal(marketState.topCards.cards.length, 1);
  assert.equal(marketState.topCards.cards[0].name, "Chase");
  assert.equal(marketState.setValue.history.length, 1);
  assert.equal(marketState.setValue.historiesByScope.hits.length, 1);
  assert.equal(marketState.topCards.meta, payload.meta);
  assert.equal(marketState.setValue.meta, payload.meta);
});

test("overview shares a single canonical market dashboard request for value trend and top chase cards", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const dashboardCallCount = (source.match(/getPokemonSetMarketDashboard\(/g) || []).length;

  assert.equal(dashboardCallCount, 1);
  assert.ok(source.includes("const [marketDashboardState, dispatchMarketDashboard] = useReducer("));
  assert.ok(source.includes("dispatchMarketDashboard({ type: \"success\", setId, payload, sourceWindow: dashboardSourceWindow })"));
  assert.ok(source.includes("buildMarketDashboardStateFromPayload(activeMarketDashboardState.payload || seededMarketDashboardPayload)"));
  assert.ok(!source.includes("setTopMarketCardsState"));
  assert.ok(!source.includes("applyMarketDashboardPayload"));
});

test("changing the visible top chase window does not enter dashboard loading or fetch state", async () => {
  const { createMarketDashboardState, marketDashboardReducer } = await import(pathToFileURL(marketDashboardStatePath).href);
  const payload = {
    topChaseCards: [{ id: "card-1", priceHistory: [] }],
    setValueHistoriesByScope: { standard: [{ date: "2026-06-01", setValue: 100 }] },
  };
  const initialState = createMarketDashboardState({
    status: "success",
    setId: "black-bolt",
    payload,
    sourceWindow: "365d",
  });

  const nextState = marketDashboardReducer(initialState, {
    type: "visible_window_changed",
    windowKey: "3M",
  });

  assert.equal(nextState, initialState);
  assert.equal(nextState.status, "success");
  assert.equal(nextState.sourceWindow, "365d");
});

test("market dashboard window keys are canonical for fetches and cache keys", () => {
  const ripSource = fs.readFileSync(ripPageClientPath, "utf8");
  const marketSource = fs.readFileSync(marketClientPath, "utf8");
  const dashboardRoute = fs.readFileSync(dashboardRoutePath, "utf8");

  assert.ok(marketSource.includes("export function normalizeMarketDashboardWindow"));
  assert.ok(marketSource.includes(".toLowerCase()"));
  assert.ok(marketSource.includes("window=${normalizeMarketDashboardWindow(window)}"));
  assert.ok(marketSource.includes('params.set("window", normalizedWindow)'));
  assert.ok(ripSource.includes('const DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW = "365d"'));
  assert.ok(ripSource.includes("getPokemonSetMarketDashboard(setId, { window: dashboardSourceWindow })"));
  assert.ok(dashboardRoute.includes("normalizeMarketDashboardWindow(window)"));
});

test("overview initial market dashboard request uses 365d snapshot source", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const marketSource = fs.readFileSync(marketClientPath, "utf8");
  const apiSource = fs.readFileSync(backendApiPath, "utf8");

  assert.ok(source.includes('const DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW = "365d"'));
  assert.ok(source.includes("const dashboardSourceWindow = DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW"));
  assert.ok(source.includes("getPokemonSetMarketDashboard(setId, { window: dashboardSourceWindow })"));
  assert.ok(marketSource.includes('const DEFAULT_MARKET_DASHBOARD_WINDOW = "365d"'));
  assert.ok(apiSource.includes('window=window or "365d"'));
});

test("30D top chase UI selection does not require a 30d dashboard snapshot", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('const DEFAULT_TOP_MARKET_CARDS_WINDOW = "30D"'));
  assert.ok(source.includes("selectedWindowKey={topMarketCardsWindowKey}"));
  assert.ok(source.includes("onWindowChange={setTopMarketCardsWindowKey}"));
  assert.ok(!source.includes("getPokemonSetMarketDashboard(setId, { window: topMarketCardsWindowKey"));
  assert.ok(!source.includes("getCachedPokemonSetMarketDashboard(setId, { window: topMarketCardsWindowKey"));
  assert.ok(!source.includes("prefetchPokemonSetMarketDashboard(resolvedSetId, { window: DEFAULT_TOP_MARKET_CARDS_WINDOW })"));
});

test("RIP desirability comparison renders only from available payload fields", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("function normalizeRipDesirabilityComparison"));
  assert.ok(source.includes("rip_score_without_desirability"));
  assert.ok(source.includes("rip_score_with_desirability"));
  assert.ok(source.includes("rip_rank_delta"));
  assert.ok(source.includes("function RipDesirabilityComparisonStrip"));
  assert.ok(source.includes("Without Desirability"));
  assert.ok(source.includes("With Desirability"));
  assert.ok(source.includes("Score Delta"));
  assert.ok(source.includes("Rank Delta"));
  assert.ok(source.includes("ripDesirabilityComparison={ripDesirabilityComparison}"));
});

test("set page insights receive RIP desirability comparison through snapshot summary payload", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const snapshotBuilderSource = fs.readFileSync(snapshotBuilderPath, "utf8");
  const requiredFields = [
    "rip_score_without_desirability",
    "rip_score_with_desirability",
    "rip_score_delta",
    "rip_rank_without_desirability",
    "rip_rank_with_desirability",
    "rip_rank_delta",
    "desirability_component_score",
    "rip_desirability_impact_label",
  ];

  assert.ok(snapshotBuilderSource.includes("RIP_DESIRABILITY_COMPARISON_FIELDS"));
  assert.ok(snapshotBuilderSource.includes("_merge_rip_desirability_comparison_into_set_payload"));
  assert.ok(snapshotBuilderSource.includes('next_payload["summary"] = summary'));
  assert.ok(source.includes("const summary = { ...(shellPayload?.summary || {}), ...(explorePayload?.summary || {}) };"));

  for (const field of requiredFields) {
    assert.ok(snapshotBuilderSource.includes(field), `snapshot builder propagates ${field}`);
    assert.ok(source.includes(field), `frontend normalizer accepts ${field}`);
  }

  const summaryStart = source.indexOf("const summary = { ...(shellPayload?.summary || {}), ...(explorePayload?.summary || {}) };");
  const comparisonStart = source.indexOf("const ripDesirabilityComparison = useMemo(", summaryStart);
  const comparisonEnd = source.indexOf("const desirabilitySummary", comparisonStart);
  const comparisonSource = source.slice(comparisonStart, comparisonEnd);
  const insightsStart = source.indexOf('{setDetailMode ? (', comparisonEnd);
  const insightsEnd = source.indexOf("<DesirabilityProofCards", insightsStart);
  const insightsSource = source.slice(insightsStart, insightsEnd);

  assert.ok(summaryStart >= 0);
  assert.ok(comparisonStart > summaryStart);
  assert.ok(comparisonSource.includes("normalizeRipDesirabilityComparison(summary, selectedTarget)"));
  assert.ok(insightsSource.includes("<RipScoreBreakdownModule"));
  assert.ok(insightsSource.includes("ripDesirabilityComparison={ripDesirabilityComparison}"));
});

test("market dashboard normalizer attaches top chase histories to cards", async () => {
  const { normalizeMarketDashboardPayload } = await import(pathToFileURL(marketClientPath).href);
  const payload = {
    set: { id: "set-1", name: "Mega Evolution" },
    topChaseCards: [
      {
        cardId: "card-1",
        cardVariantId: "variant-1",
        name: "Mega Chase",
        marketPrice: 12,
      },
    ],
    topChaseCardHistories: {
      "variant-1": [
        { date: "2026-06-01", marketPrice: 10 },
        { date: "2026-06-02", marketPrice: 12 },
      ],
    },
    setValueHistoriesByScope: { standard: [] },
    meta: {},
  };

  const normalized = normalizeMarketDashboardPayload(payload);
  const card = normalized.topChaseCards[0];

  assert.equal(card.cardVariantId, "variant-1");
  assert.equal(card.priceHistory.length, 2);
  assert.equal(card.price_history.length, 2);
  assert.equal(card.priceHistory[0].marketPrice, 10);
  assert.equal(card.priceHistory[1].marketPrice, 12);
});

test("top chase trend fix stays out of set value and canonical market dashboard state", () => {
  const ripSource = fs.readFileSync(ripPageClientPath, "utf8");
  const marketStateSource = fs.readFileSync(marketDashboardStatePath, "utf8");
  const setValueRenderStart = ripSource.indexOf("<SetValueTrendCard");
  const setValueRenderEnd = ripSource.indexOf("/>", setValueRenderStart);
  const setValueRenderSource = ripSource.slice(setValueRenderStart, setValueRenderEnd);

  assert.ok(setValueRenderStart >= 0);
  assert.ok(setValueRenderEnd > setValueRenderStart);
  assert.ok(setValueRenderSource.includes("history={activeSetValueHistory.history}"));
  assert.ok(!setValueRenderSource.includes("priceHistory"));
  assert.ok(!setValueRenderSource.includes("topChase"));
  assert.ok(!marketStateSource.includes("priceHistory"));
  assert.ok(!marketStateSource.includes("topChaseCardHistories"));
  assert.ok(ripSource.includes('debugSetPagePerf("top_chase_cards.trend_state"'));
});

test("compact sparkline tooltip is local to the sparkline wrapper", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const compactStart = source.indexOf("function CompactSparkline");
  const compactEnd = source.indexOf("function normalizeSetValueHistoryPoints", compactStart);
  const compactSource = source.slice(compactStart, compactEnd);

  assert.ok(compactStart >= 0);
  assert.ok(compactEnd > compactStart);
  assert.ok(compactSource.includes("data-compact-sparkline"));
  assert.ok(compactSource.includes("data-compact-sparkline-tooltip"));
  assert.ok(compactSource.includes("className={[\"group relative"));
  assert.ok(compactSource.includes("event.clientX - bounds.left"));
  assert.ok(compactSource.includes("style={{ left: tooltipX }}"));
  assert.ok(compactSource.includes("absolute bottom-[calc(100%+0.55rem)]"));
  assert.ok(!compactSource.includes("pointer-events-none fixed"));
  assert.ok(!compactSource.includes("window.innerWidth"));
  assert.ok(!compactSource.includes("event.clientY"));
});

test("header set value compact sparkline shows the simple date/value/delta hover tooltip", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const labelIndex = source.indexOf("{setValueMetricLabel}");
  const sparklineStart = source.indexOf("<CompactSparkline", labelIndex);
  const sparklineEnd = source.indexOf("/>", sparklineStart);
  const setValueSparklineSource = source.slice(sparklineStart, sparklineEnd);

  assert.ok(labelIndex >= 0);
  assert.ok(sparklineStart > labelIndex);
  assert.ok(setValueSparklineSource.includes("points={setHeaderSummary.setValue.sparklinePoints}"));
  assert.ok(setValueSparklineSource.includes('valueKey="setValue"'));
  // CompactSparkline's default tooltip already renders exactly date/value/delta
  // (see its own showTooltip block) — the title card must not opt back out of it.
  assert.ok(!setValueSparklineSource.includes("showTooltip={false}"));
});

test("dropdown set switch can hydrate from a cached 365d market dashboard payload", async () => {
  const { hydrateMarketDashboardStateFromCachedPayload } = await import(pathToFileURL(marketDashboardStatePath).href);
  const cachedPayload = {
    topChaseCards: [{ id: "card-1" }],
    setValueHistoriesByScope: { standard: [{ date: "2026-06-01", setValue: 100 }] },
  };

  const hydratedState = hydrateMarketDashboardStateFromCachedPayload({
    setId: "white-flare",
    cachedPayload,
    sourceWindow: "365d",
  });

  assert.equal(hydratedState.status, "success");
  assert.equal(hydratedState.setId, "white-flare");
  assert.equal(hydratedState.payload, cachedPayload);
  assert.equal(hydratedState.sourceWindow, "365d");

  const source = fs.readFileSync(ripPageClientPath, "utf8");
  assert.ok(source.includes('warmSetDetailResources(nextTargetId, { reason: "selection" })'));
  assert.ok(source.includes("hydrateMarketDashboardStateFromCachedPayload({"));
});

test("overview market dashboard state is isolated from desirability validation payloads", () => {
  const source = fs.readFileSync(marketDashboardStatePath, "utf8");
  const start = source.indexOf("export function buildMarketDashboardStateFromPayload(payload)");
  const end = source.length;
  const marketStateBuilder = source.slice(start, end);

  assert.ok(start >= 0);
  assert.ok(marketStateBuilder.includes("payload?.setValueHistoriesByScope"));
  assert.ok(marketStateBuilder.includes("payload?.topChaseCards"));
  assert.ok(!marketStateBuilder.includes("desirabilityValidation"));
  assert.ok(!marketStateBuilder.includes("desirability_validation"));
});

test("first-load snapshot fetches retry once for transient proxy or snapshot failures", () => {
  const marketSource = fs.readFileSync(marketClientPath, "utf8");
  const cardsSource = fs.readFileSync(cardsClientPath, "utf8");

  for (const source of [marketSource, cardsSource]) {
    assert.ok(source.includes("RETRYABLE_SNAPSHOT_STATUSES"));
    assert.ok(source.includes("for (let attempt = 0; attempt < 2; attempt += 1)"));
    assert.ok(source.includes("!isRetryableSnapshotError(error)"));
    assert.ok(source.includes("fetch_retry"));
  }
});

test("proxy routes do not cache failed snapshot responses", () => {
  const dashboardRoute = fs.readFileSync(dashboardRoutePath, "utf8");
  const cardsRoute = fs.readFileSync(cardsRoutePath, "utf8");

  for (const source of [dashboardRoute, cardsRoute]) {
    assert.ok(source.includes('const FAILED_ANALYTICS_CACHE_CONTROL = "no-store"'));
    assert.ok(source.includes("!proxyResponse.ok ? FAILED_ANALYTICS_CACHE_CONTROL"));
    assert.ok(source.includes('cache: "no-store"'));
  }
});

test("backend public snapshot resolver accepts URL slugs like journey-together", () => {
  const source = fs.readFileSync(snapshotServicePath, "utf8");

  assert.ok(source.includes("def _normalise_set_lookup_key"));
  assert.ok(source.includes("resolved set identifier by normalized slug"));
  assert.ok(source.includes('row.get("name")'));
  assert.ok(source.includes('row.get("canonical_key")'));
});

test("card snapshot client preserves precomputed card validation fields", () => {
  const source = fs.readFileSync(cardsClientPath, "utf8");

  assert.ok(source.includes("payload?.cardDesirabilityValidation?.cards"));
  assert.ok(source.includes("validationByKey"));
  assert.ok(source.includes("validation?.adjustedCardAppealScore"));
  assert.ok(source.includes("subjectDemandScore"));
  assert.ok(source.includes("cardAppealScore"));
  assert.ok(source.includes("scarcityAdjustedCardAppealScore"));
  assert.ok(source.includes("validation?.pokemonDesirabilityScore"));
  assert.ok(source.includes("validation?.treatmentScore"));
  assert.ok(source.includes("validation?.scarcityScore"));
  assert.ok(source.includes("validation?.isHitEligible"));
  assert.ok(source.includes("validation?.setValueShare"));
  assert.ok(source.includes("validation?.pokemonName"));
  assert.ok(source.includes("normalizeCardAppealMarketPriceCorrelation"));
  assert.ok(source.includes("cardAppealMarketPriceCorrelation"));
  assert.ok(source.includes("payload?.cardAppealMarketPriceCorrelation"));
  assert.ok(source.includes("plotRows"));
  assert.ok(source.includes("subjectDesirabilityScore"));
});

test("cards proxy route returns controlled timeout errors", () => {
  const cardsRoute = fs.readFileSync(cardsRoutePath, "utf8");

  assert.ok(cardsRoute.includes("AbortController"));
  assert.ok(cardsRoute.includes("BACKEND_FETCH_TIMEOUT_MS"));
  assert.ok(cardsRoute.includes("POKEMON_SET_CARDS_TIMEOUT"));
  assert.ok(cardsRoute.includes('"Timed out loading Pokemon set cards"'));
  assert.ok(cardsRoute.includes("backendPath"));
  assert.ok(cardsRoute.includes("backendPathForDiagnostics(backendUrl)"));
});

test("card appeal market chart defaults to hits with honest labels", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('useState("cardAppeal")'));
  assert.ok(source.includes('useState("hits")'));
  assert.ok(source.includes("getCardAppealSampleDiagnostics"));
  assert.ok(source.includes('label: "Priced Cards"'));
  assert.ok(source.includes('label: "Hits Only"'));
  assert.ok(source.includes('label: "Card Appeal"'));
  assert.ok(source.includes("Card Appeal is currently calculated for Pokémon cards only."));
  assert.ok(source.includes("This chart only includes priced cards with a Card Appeal score."));
  assert.ok(source.includes("Card Appeal currently uses Pokémon demand + card treatment"));
  assert.ok(source.includes("non-Pokémon cards are excluded even if they have prices."));
  assert.ok(source.includes("priced non-Pokémon"));
  assert.ok(source.includes("excluded from Card Appeal."));
  assert.ok(source.includes("priced cards`"));
  assert.ok(source.includes('label: "Pure Pokemon Demand"'));
  assert.ok(source.includes('label: "Treatment Score"'));
  assert.ok(source.includes('label: "Scarcity-Adjusted Appeal"'));
  assert.ok(!source.includes('label: "Adjusted Card Appeal"'));
  assert.ok(!source.includes('tooltipLabel: "Adjusted Appeal"'));
  assert.ok(!source.includes("useHitsOnly"));
  assert.ok(!source.includes("hitPoints"));
  assert.ok(!source.includes("Undervalued"));
  assert.ok(source.includes("Appeal Above Price"));
});

test("card appeal market chart accepts current price and logs sample diagnostics", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("toNumber(card?.currentPrice)"));
  assert.ok(source.includes("toNumber(card?.current_price)"));
  for (const expected of [
    "selectedSetId",
    "selectedSetSlug",
    "selectedTab",
    "checklistCardsLength",
    "cardsWithMarketPriceOrCurrentPrice",
    "cardsWithPokemonDesirabilityScore",
    "cardsWithCardDesirabilityScore",
    "cardsWithTreatmentScore",
    "cardsWithAdjustedCardAppealScore",
    "cardsWithScarcityScore",
    "finalChartPointCount",
    "activeMetricKey",
    "activeMetricLabel",
    "currentCardScope",
  ]) {
    assert.ok(source.includes(expected), `missing diagnostic key: ${expected}`);
  }
});

test("card appeal market chart prefers canonical correlation sample when available", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("cardAppealMarketPriceCorrelation"));
  assert.ok(source.includes("getCanonicalCardAppealCorrelationForSelection"));
  assert.ok(source.includes("getCanonicalCardAppealRows"));
  assert.ok(source.includes("getCardValidationRowsForMetric"));
  assert.ok(source.includes('["pure", "cardAppeal", "treatment"].includes(selectedMetric?.key)'));
  assert.ok(source.includes('selectedMetric?.key !== "pure"'));
  assert.ok(source.includes('selectedScope?.key !== "priced"'));
  assert.ok(source.includes("const sourceRows = getCardValidationRowsForMetric(rows, cardAppealMarketPriceCorrelation, selectedMetric)"));
  assert.ok(source.includes("const canonicalRowsAvailable = getCanonicalCardAppealRows(cardAppealMarketPriceCorrelation, selectedMetric).length > 0"));
  assert.ok(source.includes("const pointPearson = calculatePearsonCorrelation(points)"));
  assert.ok(source.includes("const pointSpearman = calculateSpearmanCorrelation(points)"));
  assert.ok(source.includes("const sampleCount = canonicalCorrelation && !canonicalRowsAvailable ? canonicalCorrelation.n : points.length"));
  assert.ok(source.includes('"canonical cards"'));
  assert.ok(source.includes('"hits only"'));
  assert.ok(source.includes("points.length} plotted"));
});

test("card validation bucket row keys include stable identity beyond card name", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const helperStart = source.indexOf("function getValidationBucketRowKey");
  const helperEnd = source.indexOf("function CardDesirabilityMarketValidationCard", helperStart);
  const helperSource = source.slice(helperStart, helperEnd);
  const renderStart = source.indexOf("{bucket.rows.map((row, rowIndex) => (", helperEnd);
  const renderEnd = source.indexOf("</div>", renderStart);
  const renderSource = source.slice(renderStart, renderEnd);

  assert.ok(helperStart >= 0);
  assert.ok(helperEnd > helperStart);
  for (const expected of [
    "row?.id",
    "row?.cardId ?? row?.card_id",
    "row?.pokemonCanonicalCardId ?? row?.pokemon_canonical_card_id",
    "row?.printedNumber ?? row?.printed_number",
    "row?.setNumber ?? row?.set_number",
    "row?.rarity",
    "row?.name",
    "index",
  ]) {
    assert.ok(helperSource.includes(expected), `missing key field: ${expected}`);
  }
  assert.ok(helperSource.includes(".filter((part) => part !== null && part !== undefined && part !== \"\")"));
  assert.ok(helperSource.includes(".map(String)"));
  assert.ok(renderSource.includes("getValidationBucketRowKey(bucket, row, rowIndex)"));
  assert.ok(!renderSource.includes("`${bucket.title}:${row.name}`"));
});

test("desirability proof cards render from set payload validation data", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("function DesirabilityProofCards"));
  assert.ok(source.includes("Desirability Impact"));
  assert.ok(source.includes("Desirability Signal Check"));
  assert.ok(source.includes("getDesirabilityValidationPayload(explorePayload)"));
  assert.ok(source.includes("desirabilityValidationPayload"));
  assert.ok(source.includes("Card appeal validation is not available for this set yet."));
  assert.ok(source.includes("View Card Appeal chart"));
  assert.ok(source.includes("#set-detail-card-desirability-price"));
});

test("desirability validation selector uses metric-specific market checks", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('key: "setValue"'));
  assert.ok(source.includes('key: "packCost"'));
  assert.ok(source.includes("opening sets with value data"));
  assert.ok(source.includes("opening sets with pack cost"));
  assert.ok(source.includes("simulated opening sets"));
  assert.ok(source.includes("P95 is cost-adjusted upper-tail upside."));
  assert.ok(source.includes("Highly desirable sets often become more expensive to open."));
  assert.ok(!source.includes('key: "p99"'));
  assert.ok(!source.includes("P99 Chase Upside"));
});

test("desirability validation set value prefers canonical checklist target fields", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const resolverStart = source.indexOf("function getValidationSetValueMetric");
  const resolverEnd = source.indexOf("function getValueRelatedKeys", resolverStart);
  const resolverSource = source.slice(resolverStart, resolverEnd);
  const validationFieldIndex = resolverSource.indexOf("set_value_for_validation");
  const checklistFieldIndex = resolverSource.indexOf("current_checklist_set_value");
  const simulatedFieldIndex = resolverSource.indexOf("simulated_set_value");

  assert.ok(resolverStart >= 0);
  assert.ok(resolverEnd > resolverStart);
  assert.ok(validationFieldIndex >= 0);
  assert.ok(resolverSource.includes("setValueForValidation"));
  assert.ok(resolverSource.includes("currentChecklistSetValue"));
  assert.ok(resolverSource.includes("checklistSetValue"));
  assert.ok(checklistFieldIndex < validationFieldIndex);
  assert.ok(validationFieldIndex < simulatedFieldIndex);
  assert.ok(source.includes("function getDesirabilityValidationDiagnostics"));
  assert.ok(source.includes("selectSetDesirabilityValidation"));
  assert.ok(source.includes("[desirability-validation] sample diagnostics"));
});

test("card appeal market validation can hydrate from initial module snapshot correlation", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const diagnosticsSource = fs.readFileSync(path.resolve(__dirname, "cardAppealSampleDiagnostics.mjs"), "utf8");

  assert.ok(source.includes("initialCardAppealMarketPriceCorrelation"));
  assert.ok(source.includes("initialModuleSnapshots = null"));
  assert.ok(source.includes("cardsPayload: initialCardsPayload"));
  assert.ok(source.includes("marketDashboardPayload: initialMarketDashboardPayload"));
  assert.ok(source.includes("const initialCardAppealMarketPriceCorrelation = initialSetPageDataSeed.cardAppealMarketPriceCorrelation"));
  assert.ok(source.includes("initialCardAppealRows"));
  assert.ok(source.includes("checklistState.cards.length > 0 ? checklistState.cards : initialCardAppealRows"));
  assert.ok(source.includes("resolvePreferredCardAppealCorrelation({"));
  assert.ok(source.includes("cardsPayload: initialCardsPayload"));
  assert.ok(source.includes("previous: initialCardAppealMarketPriceCorrelation"));
  assert.ok(diagnosticsSource.indexOf("asObject(cardsPayload?.cardAppealMarketPriceCorrelation)") < diagnosticsSource.indexOf("asObject(checklistState?.cardAppealMarketPriceCorrelation)"));
});

test("initial cards payload seeds checklist state before cards fetch", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const stateStart = source.indexOf("const [checklistState, setChecklistState] = useState(() => ({");
  const effectStart = source.indexOf("getPokemonSetCards(setId)", stateStart);
  const effectSource = source.slice(stateStart, effectStart);
  const thenStart = source.indexOf("getPokemonSetCards(setId)");
  const thenEnd = source.indexOf(".catch((error) => {", thenStart);
  const thenSource = source.slice(thenStart, thenEnd);

  assert.ok(source.includes("const initialSnapshotCards = initialSetPageDataSeed.cards"));
  assert.ok(effectSource.includes('status: initialSnapshotCards.length > 0 ? "success" : "idle"'));
  assert.ok(effectSource.includes("cards: initialSnapshotCards"));
  assert.ok(source.includes("const snapshotCards = initialSetPageDataSeed.cards"));
  assert.ok(thenSource.includes("const preserveCards = previousCards.length > 0 ? previousCards : seededCards"));
  assert.ok(thenSource.includes('"success_stale"'));
});

test("initial market dashboard payload seeds set value and dashboard state", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes('status: initialSetPageDataSeed.marketDashboard ? "success" : "idle"'));
  assert.ok(source.includes("payload: initialSetPageDataSeed.marketDashboard"));
  assert.ok(source.includes("const initialSetValueLoadedScopes = SET_VALUE_SCOPE_OPTIONS.map"));
  assert.ok(source.includes('status: initialSetValueLoadedScopes.length > 0 ? "success" : "idle"'));
  assert.ok(source.includes("historiesByScope: initialSetPageDataSeed.setValueHistoriesByScope"));
  assert.ok(source.includes("if (hasCompleteSetValueScopes(seededHistoriesByScope))"));
  assert.ok(source.includes('reason: "snapshot_has_all_scopes"'));
});

test("dev diagnostics report initial module snapshot counts", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("showSetPageDiagnostics"));
  assert.ok(source.includes("initialModuleDiagnosticRows"));
  assert.ok(source.includes('["initial cards payload", initialCardsPayload ? "present" : "missing"]'));
  assert.ok(source.includes('["initial cards count", Array.isArray(initialCardsPayload?.cards) ? initialCardsPayload.cards.length : 0]'));
  assert.ok(source.includes('["initial market dashboard", initialMarketDashboardPayload ? "present" : "missing"]'));
  assert.ok(source.includes('"initial set value scopes"'));
  assert.ok(source.includes('["initial top chase count", initialTopChaseCards.length]'));
  assert.ok(source.includes('"initial correlation"'));
  assert.ok(source.includes('["suppressed warnings", suppressedWarnings.length]'));
  assert.ok(source.includes('["debug warnings", debugWarnings.length]'));
});

test("server initial snapshot loader fetches backend modules directly without throwing page render", () => {
  const source = fs.readFileSync(initialSnapshotsServerPath, "utf8");

  assert.ok(source.includes("BACKEND_API_BASE_URL"));
  assert.ok(source.includes('/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/cards'));
  assert.ok(source.includes('/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/dashboard'));
  assert.ok(source.includes('cache: "no-store"'));
  assert.ok(source.includes("getTimeoutMs()"));
  assert.ok(source.includes("payload: null"));
  assert.ok(source.includes("errors.cards"));
  assert.ok(source.includes("errors.marketDashboard"));
});

test("handleTargetPrefetch calls router.prefetch for the destination href without changing navigation hrefs", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const prefetchStart = source.indexOf("const handleTargetPrefetch");
  const prefetchEnd = source.indexOf("};", prefetchStart);
  const prefetchSource = source.slice(prefetchStart, prefetchEnd);

  assert.ok(prefetchStart >= 0, "handleTargetPrefetch must exist");
  assert.ok(prefetchSource.includes("warmSetDetailResources(targetId, options)"), "still warms data resources");
  assert.ok(prefetchSource.includes("router.prefetch("), "must call router.prefetch for route");
  assert.ok(prefetchSource.includes("targetHrefById?.["), "must look up href from targetHrefById map");

  // Navigation must still use router.push – prefetch is separate
  const navStart = source.indexOf("const handleTargetIdChange");
  const navEnd = source.indexOf("};", navStart);
  const navSource = source.slice(navStart, navEnd);
  assert.ok(navSource.includes("router.push(nextHref"), "navigation still uses router.push");
  assert.ok(!navSource.includes("router.prefetch"), "navigation handler must not call router.prefetch");
});

test("warmSetDetailResources startPrefetch also calls router.prefetch for route pre-rendering", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const warmupStart = source.indexOf("const warmSetDetailResources = useCallback");
  const warmupEnd = source.indexOf("const outcomeDistributionInfo", warmupStart);
  const warmupSource = source.slice(warmupStart, warmupEnd);

  const startPrefetchStart = warmupSource.indexOf("const startPrefetch = (targetSetId");
  const startPrefetchEnd = warmupSource.indexOf("};", startPrefetchStart);
  const startPrefetchSource = warmupSource.slice(startPrefetchStart, startPrefetchEnd);

  assert.ok(startPrefetchStart >= 0, "startPrefetch inner function must exist");
  assert.ok(startPrefetchSource.includes("router.prefetch(targetHref)"), "startPrefetch must call router.prefetch with targetHref");
  assert.ok(startPrefetchSource.includes("targetHrefById?.[resolvedSetId]"), "must look up href using resolvedSetId");
});

test("adjacent set prefetch is disabled by default via SET_PREFETCH_ADJACENT_LIMIT", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const warmupStart = source.indexOf("const warmSetDetailResources = useCallback");
  const warmupEnd = source.indexOf("const outcomeDistributionInfo", warmupStart);
  const warmupSource = source.slice(warmupStart, warmupEnd);

  // Adjacent prefetch previously multiplied cards + dashboard + value-history
  // requests across nearby sets on every hover/navigation, saturating the
  // browser's per-origin connection limit. The mechanism stays in place
  // (bounded by this constant) but is off by default.
  assert.ok(source.includes("const SET_PREFETCH_ADJACENT_LIMIT = 0"), "SET_PREFETCH_ADJACENT_LIMIT must default to 0 (disabled)");
  assert.ok(warmupSource.includes("for (let offset = 1; offset <= SET_PREFETCH_ADJACENT_LIMIT; offset += 1)"), "adjacent loop must remain bounded by SET_PREFETCH_ADJACENT_LIMIT");
  assert.ok(warmupSource.includes("if (!includeAdjacent || !activeSetModulesStable || shouldPauseSetDetailDependentFetches"), "adjacent prefetch must be guarded");
});

test("adjacent set fanout has no bypass path outside the bounded warmSetDetailResources loop", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  // startPrefetch (called once per resolved set id, deduped) is the only
  // function that fans out per-adjacent-set work, and it is only ever
  // invoked from the bounded `for` loop above or the single active-set call.
  // No other function in the file iterates `targets` to warm multiple sets.
  const startPrefetchCallCount = (source.match(/startPrefetch\(/g) || []).length;
  assert.equal(startPrefetchCallCount, 2, "startPrefetch must only be invoked for the active set and from the bounded adjacent loop");

  const otherAdjacentFanoutStart = source.indexOf("targets.findIndex", source.indexOf("adjacentTargets.forEach") + 1);
  assert.equal(otherAdjacentFanoutStart, -1, "no second adjacent-set fanout loop may exist elsewhere in the file");
});

test("timeout fallback does not block cards, market dashboard, or set value fetches when set resource id is resolved", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const cardsEffectStart = source.indexOf("getPokemonSetCards(setId)");
  const marketStart = source.indexOf("getPokemonSetMarketDashboard(setId, { window: dashboardSourceWindow })");
  const valueHistoryStart = source.indexOf("getPokemonSetValueHistory(setId, { days: 365, scope })");

  // canFetchSetDetailModules must exist and include the transport-fallback bypass
  assert.ok(source.includes("const canFetchSetDetailModules ="), "canFetchSetDetailModules must be defined");
  assert.ok(
    source.includes("isSetPageTransportFallback(explorePayload) || hasActiveSetPageIdentity"),
    "transport fallback must allow module fetches when set id is resolved"
  );
  // Module effects guard on canFetchSetDetailModules, not shouldPauseSetDetailDependentFetches
  assert.ok(source.lastIndexOf("if (!canFetchSetDetailModules)", cardsEffectStart) >= 0, "cards effect must use canFetchSetDetailModules guard");
  assert.ok(source.lastIndexOf("if (!canFetchSetDetailModules)", marketStart) >= 0, "market effect must use canFetchSetDetailModules guard");
  assert.ok(source.lastIndexOf("if (!canFetchSetDetailModules)", valueHistoryStart) >= 0, "value history effect must use canFetchSetDetailModules guard");
  // shouldPauseSetDetailDependentFetches no longer appears as a standalone guard before these calls
  assert.ok(source.lastIndexOf("if (shouldPauseSetDetailDependentFetches)", cardsEffectStart) < 0, "shouldPauseSetDetailDependentFetches must not block cards");
  assert.ok(source.lastIndexOf("if (shouldPauseSetDetailDependentFetches)", marketStart) < 0, "shouldPauseSetDetailDependentFetches must not block market");
  assert.ok(source.lastIndexOf("if (shouldPauseSetDetailDependentFetches)", valueHistoryStart) < 0, "shouldPauseSetDetailDependentFetches must not block value history");
});

test("set page proxy route has bounded timeout and does not cache failed responses", () => {
  const source = fs.readFileSync(setPageRoutePath, "utf8");

  assert.ok(source.includes("AbortController"), "must use AbortController for bounded timeout");
  assert.ok(source.includes("BACKEND_FETCH_TIMEOUT_MS"), "must define fetch timeout constant");
  assert.ok(source.includes("SET_PAGE_SNAPSHOT_PROXY_TIMEOUT"), "must use SET_PAGE_SNAPSHOT_PROXY_TIMEOUT code on timeout");
  assert.ok(source.includes('"Set page snapshot request timed out"'), "must emit descriptive timeout message");
  assert.ok(source.includes('const FAILED_ANALYTICS_CACHE_CONTROL = "no-store"'), "must define no-store constant for failures");
  assert.ok(source.includes("backendPathForDiagnostics(backendUrl)"), "must include backend path in error diagnostics");
  assert.ok(!source.includes("next: { revalidate: 300 }"), "proxy fetch must not use Next.js revalidation cache");
  assert.ok(source.includes('cache: "no-store"'), "backend fetch must bypass Next.js cache with no-store");
});

// ---------------------------------------------------------------------------
// Perf fix: full /page payloads must never enter Next's data cache, and
// client-side retries of that endpoint must be gated, abortable, and unable
// to overwrite the active set with a stale response.
// ---------------------------------------------------------------------------

test("set page proxy route never emits a cacheable response for the oversized full page payload", () => {
  const source = fs.readFileSync(setPageRoutePath, "utf8");

  // The backend fetch itself must not opt into Next's data cache at all
  // (no `next: { revalidate }` of any kind), since full /page payloads
  // routinely exceed the 2MB data-cache limit and fail to be stored.
  assert.ok(!/next:\s*\{\s*revalidate/.test(source), "backend fetch must not pass any next.revalidate option");
  assert.ok(source.includes('cache: "no-store"'), "backend fetch must use cache: \"no-store\"");

  // The outgoing response must be consistently no-store — no public/CDN
  // cache-control branch for this route, unlike the smaller module routes.
  assert.ok(!source.includes("PUBLIC_ANALYTICS_CACHE_CONTROL"), "full /page route must not define a public cache-control path");
  assert.ok(!source.includes("s-maxage"), "full /page route must not emit a public/CDN cache header");
  const cacheControlHeaderCount = (source.match(/"Cache-Control":\s*FAILED_ANALYTICS_CACHE_CONTROL/g) || []).length;
  assert.ok(cacheControlHeaderCount >= 2, "every response branch (error and success) must send the no-store Cache-Control constant");
});

test("fetchPokemonSetPageSnapshot accepts and forwards an AbortSignal", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const fnStart = source.indexOf("async function fetchPokemonSetPageSnapshot(");
  const fnEnd = source.indexOf("\n}\n", fnStart);
  const fnSource = source.slice(fnStart, fnEnd);

  assert.ok(fnStart >= 0, "fetchPokemonSetPageSnapshot must exist");
  assert.ok(fnSource.includes("{ signal }"), "must destructure a signal option");
  assert.ok(fnSource.includes("signal,"), "must forward signal to the underlying fetch call");
  assert.ok(fnSource.includes('cache: "no-store"'), "retry fetch must bypass Next's data cache");
});

test("set page retry effect is gated to a resolved set, a true transport fallback, and a full-page tab", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const effectStart = source.indexOf("// Only retry when this is a true transport fallback");
  const effectEnd = source.indexOf("[explorePayload, requestedTargetId, selectedTarget, resolvedSetResourceId, setDetailMode, setDetailTab]);", effectStart);
  const effectSource = source.slice(effectStart, effectEnd);

  assert.ok(effectStart >= 0, "the retry effect must exist");
  assert.ok(effectSource.includes("SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD.has(setDetailTab)"), "retry must only run on tabs that need the full page payload");
  assert.ok(effectSource.includes("!resolvedSetResourceId"), "retry must require a stable resolved set resource id");
  assert.ok(effectSource.includes("isSetPageTransportFallback(explorePayload)"), "retry must require a true transport fallback payload");
  assert.ok(effectSource.includes("getSetSnapshotIdentity(explorePayload)"), "retry must inspect the fallback payload's identity");
  assert.ok(
    effectSource.includes("setIdentityMatchesTarget(fallbackIdentity, resolvedSetResourceId)"),
    "retry must require the fallback identity to match the active set when an identity exists"
  );
  assert.ok(
    !effectSource.includes("resolvedSetResourceId || requestedTargetId"),
    "retry must not fall back to requestedTargetId when resolvedSetResourceId is unresolved"
  );
});

test("Cards and Overview tabs are excluded from the full page retry/lazy-fetch tabs", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(
    source.includes('const SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD = new Set(["pull-rates", "insights"]);'),
    "only pull-rates and insights may trigger a full /page fetch"
  );
  assert.ok(!/SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD = new Set\(\[[^\]]*(cards|overview)/i.test(source), "cards/overview must never be included");
});

test("retry fetch aborts on cleanup and the resulting AbortError is ignored", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const effectStart = source.indexOf("// Only retry when this is a true transport fallback");
  const effectEnd = source.indexOf("[explorePayload, requestedTargetId, selectedTarget, resolvedSetResourceId, setDetailMode, setDetailTab]);", effectStart);
  const effectSource = source.slice(effectStart, effectEnd);

  assert.ok(effectSource.includes("const controller = new AbortController();"), "retry effect must create an AbortController");
  assert.ok(
    effectSource.includes("fetchPokemonSetPageSnapshot(setId, { signal: controller.signal })"),
    "retry fetch must be wired to the controller's signal"
  );
  assert.ok(effectSource.includes("controller.abort();"), "cleanup must abort the in-flight retry fetch on set/tab change");
  assert.ok(
    effectSource.includes('error?.name === "AbortError"'),
    "catch handler must ignore AbortError instead of surfacing it as a retry failure"
  );
  // Aborting must not clear/blank existing UI state — the catch handler
  // returns early on AbortError instead of dispatching an error/empty status.
  const catchStart = effectSource.indexOf(".catch((error) => {");
  const catchAbortGuardEnd = effectSource.indexOf("return;", catchStart);
  const abortGuardSource = effectSource.slice(catchStart, catchAbortGuardEnd);
  assert.ok(abortGuardSource.includes("isCancelled || error?.name"), "abort/cancel check must be the first thing the catch handler does");
});

test("lazy full-page fetch for insights/pull-rates is also abortable", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const effectStart = source.indexOf("if (!setDetailMode || explorePayload) {");
  const effectEnd = source.indexOf("}, [setDetailMode, setDetailTab, explorePayload, resolvedSetResourceId, requestedTargetId]);", effectStart);
  const effectSource = source.slice(effectStart, effectEnd);

  assert.ok(effectStart >= 0, "the lazy full-page fetch effect must exist");
  assert.ok(effectSource.includes("SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD.has(setDetailTab)"), "must reuse the shared full-page tab set instead of duplicating tab literals");
  assert.ok(effectSource.includes("const controller = new AbortController();"), "must create an AbortController");
  assert.ok(effectSource.includes("fetchPokemonSetPageSnapshot(setId, { signal: controller.signal })"), "fetch must be wired to the controller's signal");
  assert.ok(effectSource.includes("controller.abort();"), "cleanup must abort the in-flight fetch on set/tab change");
});

test("a stale retry response cannot overwrite the active set after switching sets", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("const activeSetResourceIdRef = useRef(null);"), "must track the freshest resolved set id in a ref for async callbacks");
  assert.ok(source.includes("activeSetResourceIdRef.current = resolvedSetResourceId;"), "ref must be kept in sync with the latest resolved set id on every render");

  const effectStart = source.indexOf("// Only retry when this is a true transport fallback");
  const effectEnd = source.indexOf("[explorePayload, requestedTargetId, selectedTarget, resolvedSetResourceId, setDetailMode, setDetailTab]);", effectStart);
  const effectSource = source.slice(effectStart, effectEnd);
  const thenStart = effectSource.indexOf(".then((payload) => {");
  const thenEnd = effectSource.indexOf(".catch((error) => {", thenStart);
  const thenSource = effectSource.slice(thenStart, thenEnd);

  assert.ok(effectStart >= 0 && thenStart >= 0, "retry .then() handler must exist");
  assert.ok(
    thenSource.includes("isSetStateForActiveSet(setId, {") && thenSource.includes("resolvedSetResourceId: activeSetResourceIdRef.current,"),
    "must verify the fetched setId still matches the freshest active set identity before applying it"
  );
  assert.ok(
    thenSource.indexOf("setExplorePayload(payload || null);") > thenSource.indexOf("isStillActiveSet"),
    "setExplorePayload must only run after the stale-set check"
  );
});

// ---------------------------------------------------------------------------
// Regression: Cards/Overview blanking after the set page performance split
// ---------------------------------------------------------------------------

test("getResolvedPokemonSetResourceId accepts shellPayload as an identity source", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const fnStart = source.indexOf("function getResolvedPokemonSetResourceId(");
  const fnEnd = source.indexOf("\n}\n", fnStart);
  const fnSource = source.slice(fnStart, fnEnd);

  assert.ok(fnStart >= 0, "getResolvedPokemonSetResourceId must exist");
  assert.ok(fnSource.includes("shellPayload"), "must accept shellPayload in its params");
  assert.ok(fnSource.includes("getSetSnapshotIdentity(shellPayload)"), "must derive identity from shellPayload");
  assert.ok(fnSource.includes("shellResourceId"), "must compute a shell-derived resource id");
  assert.ok(
    source.includes(
      "getResolvedPokemonSetResourceId({ requestedTargetId, selectedTarget, explorePayload, shellPayload })"
    ),
    "resolvedSetResourceId call site must pass shellPayload through"
  );
});

test("hasRealSetPageIdentity does not require explorePayload when a resource id is already resolved", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const fnStart = source.indexOf("function hasRealSetPageIdentity(");
  const fnEnd = source.indexOf("\n}\n", fnStart);
  const fnSource = source.slice(fnStart, fnEnd);

  assert.ok(fnStart >= 0, "hasRealSetPageIdentity must exist");
  // Cards/Overview intentionally render with explorePayload === null; identity
  // must still be considered known there instead of unconditionally failing.
  assert.ok(fnSource.includes("if (!explorePayload) {"), "must special-case a null explorePayload");
  assert.ok(
    fnSource.includes("return Boolean(resolvedSetResourceId);"),
    "must fall back to resolvedSetResourceId when explorePayload is absent"
  );
});

test("cards module fetch is allowed once identity resolves from shell even though explorePayload is null", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  // canFetchSetDetailModules short-circuits on a null explorePayload (the
  // Cards/Overview case) as long as resolvedSetResourceId is present.
  const canFetchStart = source.indexOf("const canFetchSetDetailModules =");
  const canFetchEnd = source.indexOf(";", source.indexOf(": true", canFetchStart));
  const canFetchSource = source.slice(canFetchStart, canFetchEnd);

  assert.ok(canFetchSource.includes("Boolean(resolvedSetResourceId)"), "must gate on a resolved set resource id");
  assert.ok(canFetchSource.includes("!explorePayload"), "must allow module fetches when explorePayload is intentionally null");
});

test("market dashboard reducer reset preserves an existing successful payload for the same set", async () => {
  const { createMarketDashboardState, marketDashboardReducer } = await import(pathToFileURL(marketDashboardStatePath).href);

  const initialState = createMarketDashboardState({
    status: "success",
    setId: "ascended-heroes",
    payload: { topChaseCards: [{ id: "card-1" }] },
    sourceWindow: "365d",
  });

  // A reset for the SAME set (e.g. a transient canFetchSetDetailModules dip)
  // must not blank out data that is already loaded.
  const sameSetReset = marketDashboardReducer(initialState, {
    type: "reset",
    status: "empty",
    setId: "ascended-heroes",
    sourceWindow: "365d",
  });
  assert.equal(sameSetReset.status, "success_stale");
  assert.deepEqual(sameSetReset.payload, initialState.payload);

  // A reset for a DIFFERENT set must still discard the stale payload.
  const differentSetReset = marketDashboardReducer(initialState, {
    type: "reset",
    status: "empty",
    setId: "obsidian-flames",
    sourceWindow: "365d",
  });
  assert.equal(differentSetReset.status, "empty");
  assert.equal(differentSetReset.payload, null);
});

test("overview value-history skip-when-complete check lives only in the lazy direct-fetch effect, not in prefetch", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const warmupStart = source.indexOf("const warmSetDetailResources = useCallback");
  const warmupEnd = source.indexOf("const outcomeDistributionInfo", warmupStart);
  const warmupSource = source.slice(warmupStart, warmupEnd);

  const startPrefetchStart = warmupSource.indexOf("const startPrefetch = (targetSetId");
  const startPrefetchEnd = warmupSource.indexOf("};", startPrefetchStart);
  const startPrefetchSource = warmupSource.slice(startPrefetchStart, startPrefetchEnd);

  // startPrefetch no longer fetches value-history at all (fanout removed),
  // so it has no completeness check of its own to gate. The one remaining
  // completeness check ("set value history fetches directly on every set
  // detail tab" test) lives in the lazy per-scope effect instead.
  assert.ok(
    !startPrefetchSource.includes("hasCompleteSetValueScopes"),
    "startPrefetch must not duplicate the value-history completeness check"
  );
  assert.ok(
    !startPrefetchSource.includes("Promise.all("),
    "startPrefetch must not run any multi-request fanout"
  );
  assert.ok(source.includes("if (hasCompleteSetValueScopes(seededHistoriesByScope))"), "the direct-fetch effect still skips fetching when scopes are already complete");
});

test("overview market dashboard error handling keeps stale/seeded data instead of blanking the tab", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const marketEffectStart = source.indexOf("getPokemonSetMarketDashboard(setId, { window: dashboardSourceWindow })");
  const marketEffectEnd = source.indexOf("return () => {", marketEffectStart);
  const marketEffectSource = source.slice(marketEffectStart, marketEffectEnd);

  assert.ok(marketEffectSource.includes('type: "error"'), "must dispatch an error action on fetch failure");
  // The reducer's own "error" case (not the effect) is what preserves stale
  // payload for the same set — assert that behavior directly.
  const marketStateSource = fs.readFileSync(marketDashboardStatePath, "utf8");
  const errorCaseStart = marketStateSource.indexOf('case "error":');
  const errorCaseEnd = marketStateSource.indexOf("case \"error\":", errorCaseStart + 1) >= 0
    ? marketStateSource.indexOf("case \"error\":", errorCaseStart + 1)
    : marketStateSource.indexOf("default:", errorCaseStart);
  const errorCaseSource = marketStateSource.slice(errorCaseStart, errorCaseEnd);
  assert.ok(errorCaseSource.includes('"success_stale"'), "error case must fall back to success_stale when a payload already exists for the set");
});

test("set detail body renders from shell payload without requiring full explore payload", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  // The regression: Cards/Overview intentionally never receive explorePayload
  // (see page.js's needsExplorePagePayload), so gating the entire body on
  // explorePayload alone left those tabs permanently blank.
  assert.ok(
    !source.includes("{!pageError && explorePayload ? ("),
    "set detail render must not be gated only on explorePayload"
  );

  const shellBooleanStart = source.indexOf("const hasSetDetailShellPayload =");
  assert.ok(shellBooleanStart >= 0, "must define a shell-aware render boolean");
  const shellBooleanEnd = source.indexOf(";", source.indexOf(": Boolean(explorePayload);", shellBooleanStart));
  const shellBooleanSource = source.slice(shellBooleanStart, shellBooleanEnd);

  assert.ok(shellBooleanSource.includes("setDetailMode"), "shell-aware boolean must branch on setDetailMode");
  assert.ok(shellBooleanSource.includes("shellPayload"), "must allow rendering from shellPayload alone");
  assert.ok(shellBooleanSource.includes("resolvedSetResourceId"), "must allow rendering once identity resolves");

  const canRenderStart = source.indexOf("const canRenderPrimaryContent =");
  assert.ok(canRenderStart >= 0, "must define a top-level primary-content render gate");
  const canRenderEnd = source.indexOf(";", canRenderStart);
  const canRenderSource = source.slice(canRenderStart, canRenderEnd);
  assert.ok(canRenderSource.includes("pageError"), "primary content gate must still respect pageError");
  assert.ok(canRenderSource.includes("hasSetDetailShellPayload"), "primary content gate must use the shell-aware boolean");

  assert.ok(source.includes("{canRenderPrimaryContent ? ("), "top-level body must render off canRenderPrimaryContent");
});

test("Explore/profile navigation is not routed through set-detail tab navigation", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  // pushSetDetailRouteState backs handleSetDetailTabChange/handleSetDetailNavSelect;
  // it must no-op outside setDetailMode so it can never touch Explore/profile routes.
  const pushStart = source.indexOf("const pushSetDetailRouteState = ({ tab, section } = {}) => {");
  const pushEnd = source.indexOf("};", pushStart);
  const pushSource = source.slice(pushStart, pushEnd);
  assert.ok(pushStart >= 0, "pushSetDetailRouteState must exist");
  assert.ok(pushSource.includes("if (!setDetailMode) {"), "must no-op outside set-detail mode");

  // handleSetDetailNavSelect must be wired only to the set-detail navigation
  // rail — never to the shared PublicProfileLocalScaffold shell that owns
  // Explore/profile section navigation via profileBaseHref + <Link>.
  const wiringCount = (source.match(/onNavigate=\{handleSetDetailNavSelect\}/g) || []).length;
  assert.equal(wiringCount, 1, "handleSetDetailNavSelect must be wired to exactly one nav surface (the set-detail rail)");

  const scaffoldStart = source.indexOf("<PublicProfileLocalScaffold");
  const scaffoldOpenEnd = source.indexOf(">", scaffoldStart);
  const scaffoldOpeningProps = source.slice(scaffoldStart, scaffoldOpenEnd);

  assert.ok(scaffoldStart >= 0, "PublicProfileLocalScaffold must be rendered");
  assert.ok(scaffoldOpeningProps.includes("profileBaseHref={profileBaseHref}"), "Explore/profile shell must receive profileBaseHref");
  assert.ok(!scaffoldOpeningProps.includes("onNavigate"), "profile shell must own its Explore/profile navigation, not receive the set-detail nav handler");
  assert.ok(!scaffoldOpeningProps.includes("handleSetDetailNavSelect"), "profile shell must not be wired to handleSetDetailNavSelect");
  assert.ok(!scaffoldOpeningProps.includes("handleTargetIdChange"), "profile shell must not be wired to set-switch navigation");
});

test("same-set tab/section navigation uses router.push, not a shallow history-only update", () => {
  // Regression guard: pushSetDetailRouteState previously called a
  // window.history.pushState-only helper for same-set tab/section changes.
  // That meant page.js never re-ran on tab clicks, so the newly-active tab's
  // module snapshot (cards/marketDashboard/full explore payload, all of
  // which are tab-scoped SSR fetches) never loaded — causing first-navigation
  // hydration gaps (missing Set Value Trend, "No cards found" flashes, stale
  // header data) that only cleared on a hard refresh. router.push must be
  // used so every same-set tab change is a real navigation through page.js.
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const pushStart = source.indexOf("const pushSetDetailRouteState = ({ tab, section } = {}) => {");
  const pushEnd = source.indexOf("};", pushStart);
  const pushSource = source.slice(pushStart, pushEnd);

  assert.ok(pushStart >= 0, "pushSetDetailRouteState must exist");
  assert.ok(
    pushSource.includes("router.push(nextHref, { scroll: false })"),
    "pushSetDetailRouteState must navigate via router.push"
  );
  assert.ok(
    !pushSource.includes("pushShallowSetDetailHistoryState"),
    "pushSetDetailRouteState must not delegate to a shallow history-only helper"
  );
  assert.ok(
    !pushSource.includes("window.history.pushState"),
    "pushSetDetailRouteState must not write history state directly instead of navigating"
  );
});

test("shallow-only same-set tab navigation helper does not exist", () => {
  // Regression guard: keeps the pushState-only shortcut from being
  // reintroduced anywhere in this file until every tab has a proven
  // client-side query/hydration path (with its own tests) to back it.
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(
    !source.includes("pushShallowSetDetailHistoryState"),
    "pushShallowSetDetailHistoryState (or any same-named helper) must not exist in this file"
  );
  assert.ok(
    !source.includes("window.history.pushState"),
    "no shallow window.history.pushState-only navigation helper may exist in this file"
  );
});

test("title/header card renders from the Set Header Summary Contract, not activeSetDetailTab", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(
    source.includes('import { buildSetHeaderSummary } from "./setHeaderSummarySelector.mjs";'),
    "must import buildSetHeaderSummary"
  );

  const memoStart = source.indexOf("const setHeaderSummary = useMemo(");
  assert.ok(memoStart >= 0, "must define a setHeaderSummary memo");
  const memoEnd = source.indexOf("const activeChartSetValueMetrics = useMemo(", memoStart);
  const memoSource = source.slice(memoStart, memoEnd);

  assert.ok(memoSource.includes("buildSetHeaderSummary({"), "memo must call buildSetHeaderSummary");
  assert.ok(memoSource.includes("explorePayload,"), "must pass explorePayload");
  assert.ok(memoSource.includes("shellPayload,"), "must pass shellPayload");
  assert.ok(memoSource.includes("marketDashboardPayload: initialMarketDashboardPayload,"), "must pass the seeded market dashboard payload");
  assert.ok(memoSource.includes("marketDashboardState: activeMarketDashboardDerivedState,"), "must pass the derived market dashboard state");
  assert.ok(memoSource.includes("setValueContract: activeSetValueContract,"), "must pass the blended set value contract");
  assert.ok(memoSource.includes("selectedTarget,"), "must pass selectedTarget");
  assert.ok(memoSource.includes("resolvedSetResourceId,"), "must pass resolvedSetResourceId");
  assert.ok(
    memoSource.includes("explorePayloadIsFresh: isPrimarySnapshotReady,"),
    "must gate explorePayload freshness on the existing identity-matched readiness flag"
  );
  assert.ok(
    memoSource.includes("previousSameSetSummary: setHeaderSummaryCacheRef.current,"),
    "must thread the sticky same-set cache in as the fourth-priority fallback"
  );

  const cacheWriteIndex = source.indexOf("setHeaderSummaryCacheRef.current = setHeaderSummary;", memoStart);
  assert.ok(
    cacheWriteIndex > memoStart && cacheWriteIndex <= memoEnd,
    "must persist the freshest header summary into the sticky cache right after computing it"
  );

  // The header hero card (title/score/recommendation/set-value block) must
  // read from setHeaderSummary — never directly off setDetailTab, and never
  // bare `summary.pack_tier`/`recommendationBadge` inside that block, since
  // those are only as fresh as whatever tab happened to load.
  const heroStart = source.indexOf('{RIP_COPY.scoreLabel}</p>');
  const heroEnd = source.indexOf("set-detail-content", heroStart);
  const heroSource = source.slice(heroStart, heroEnd);

  assert.ok(!heroSource.includes("setDetailTab"), "header hero must not depend on the active setDetailTab");
  assert.ok(heroSource.includes("setHeaderSummary.score"), "header score must come from setHeaderSummary");
  assert.ok(heroSource.includes("setHeaderSummary.tier"), "header tier must come from setHeaderSummary");
  assert.ok(heroSource.includes("setHeaderSummary.rank"), "header rank must come from setHeaderSummary");
  assert.ok(heroSource.includes("setHeaderSummary.recommendationBadge"), "header badge must come from setHeaderSummary");
  assert.ok(heroSource.includes("setHeaderSummary.recommendationSummary"), "header recommendation text must come from setHeaderSummary");
  assert.ok(heroSource.includes("setHeaderSummary.setValue.current"), "header set value must come from setHeaderSummary");
  assert.ok(heroSource.includes("setHeaderSummary.setValue.delta30dAmount"), "header set value delta must come from setHeaderSummary");
  assert.ok(heroSource.includes("setHeaderSummary.setValue.sparklinePoints"), "header sparkline must come from setHeaderSummary");
  assert.ok(heroSource.includes("headerDecisionMetrics.map("), "header metric tiles must come from headerDecisionMetrics, not the shared decisionMetrics array");
});

test("title-card checklist set value sparkline has a hover tooltip like the Overview Set Value Trend chart", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const heroStart = source.indexOf('{RIP_COPY.scoreLabel}</p>');
  const sparklineStart = source.indexOf("<CompactSparkline", heroStart);
  const sparklineEnd = source.indexOf("/>", sparklineStart);
  const sparklineSource = source.slice(sparklineStart, sparklineEnd);

  assert.ok(sparklineStart >= 0, "header CompactSparkline must exist");
  assert.ok(
    !sparklineSource.includes("showTooltip={false}"),
    "header sparkline must not explicitly disable the built-in date/value/delta tooltip"
  );
});

test("compact header sparkline tooltip floats above the RIP score/title card instead of being clipped", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const heroStart = source.indexOf('{RIP_COPY.scoreLabel}</p>');
  const sparklineStart = source.indexOf("<CompactSparkline", heroStart);
  assert.ok(sparklineStart > heroStart, "header CompactSparkline must exist after the RIP score label");

  const cardWrapperStart = source.lastIndexOf('<div className="relative flex min-h-[8.25rem]', sparklineStart);
  const cardWrapperEnd = source.indexOf(">", cardWrapperStart);
  const cardWrapperClassName = source.slice(cardWrapperStart, cardWrapperEnd);

  assert.ok(cardWrapperStart >= 0, "checklist set value card wrapping the header sparkline must exist");
  assert.ok(
    cardWrapperClassName.includes("has-[[data-compact-sparkline-tooltip]]:z-30"),
    "checklist set value card must raise its stacking context above the RIP score/title card (z-20) while its tooltip is showing"
  );
  assert.ok(
    !cardWrapperClassName.includes("overflow-hidden"),
    "checklist set value card must not clip the sparkline tooltip"
  );

  const compactStart = source.indexOf("function CompactSparkline");
  const compactEnd = source.indexOf("function normalizeSetValueHistoryPoints", compactStart);
  const compactSource = source.slice(compactStart, compactEnd);

  assert.ok(
    compactSource.includes("overflow-visible"),
    "sparkline container must allow its tooltip to escape the tiny chart box instead of clipping it"
  );
  assert.ok(
    compactSource.includes("pointer-events-none absolute"),
    "sparkline tooltip must not intercept pointer events"
  );
  assert.ok(
    compactSource.includes("z-[9999]"),
    "sparkline tooltip must use a high z-index so it floats above surrounding cards"
  );

  // The Overview Set Value Trend chart must reuse the same compact tooltip shape.
  const overviewTooltipStart = source.indexOf("<RechartsTooltip content={<SetValueTooltip");
  const overviewTooltipLineEnd = source.indexOf("\n", overviewTooltipStart);
  const overviewTooltipSource = source.slice(overviewTooltipStart, overviewTooltipLineEnd);
  assert.ok(overviewTooltipStart >= 0, "Overview chart RechartsTooltip must exist");
  assert.ok(
    overviewTooltipSource.includes('content={<SetValueTooltip />}'),
    "Overview chart tooltip content must use the compact set value tooltip"
  );
  assert.ok(
    !overviewTooltipSource.includes("wrapperStyle"),
    "Overview chart tooltip must not be modified by the compact header tooltip fix"
  );
});

test("interpretation (recommendation badge/summary, pillar metas, set intelligence) falls back to shellPayload", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(
    source.includes(
      "const interpretation = explorePayload?.interpretation || shellPayload?.interpretation || {};"
    ),
    "interpretation must fall back to shellPayload so Decision Signals / recommendation text survive tab switches"
  );
});

test("shell payload contract exposes interpretation and set value history for the header/Decision Signals", () => {
  const source = fs.readFileSync(setPageAdaptersPath, "utf8");
  const backendServiceSource = fs.readFileSync(snapshotServicePath, "utf8");
  const backendBuilderSource = fs.readFileSync(snapshotBuilderPath, "utf8");

  assert.ok(
    backendServiceSource.includes("set_intelligence_json"),
    "shell snapshot query must select set_intelligence_json so the header/Decision Signals can read the recommendation"
  );
  assert.ok(
    backendServiceSource.includes('"interpretation": interpretation,') ||
      backendServiceSource.includes('"interpretation":') ,
    "shell payload builder must expose interpretation"
  );
  assert.ok(
    backendServiceSource.includes("_load_shell_checklist_set_value_history"),
    "shell endpoint must enrich the payload with a lightweight checklist set value history"
  );
  assert.ok(
    backendBuilderSource.includes('"average_hit_value"'),
    "snapshot builder must project average_hit_value into a shell-visible subset"
  );
  assert.ok(
    backendBuilderSource.includes('"biggest_upside_score"') && backendBuilderSource.includes('"biggest_upside_rank"'),
    "snapshot builder must project biggest_upside score/rank/tier into rip_summary_json"
  );
  assert.ok(source.length > 0, "setPageAdapters module must still be readable");
});
