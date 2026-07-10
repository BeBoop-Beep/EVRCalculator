const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const test = require("node:test");
const assert = require("node:assert/strict");

const ripPageClientPath = path.resolve(__dirname, "RipStatisticsPageClient.jsx");
const marketDashboardStatePath = path.resolve(__dirname, "marketDashboardState.mjs");
const marketClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetMarketClient.js");
const cardsClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetCardsClient.js");
const pullRatesClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetPullRatesClient.js");
const insightsClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetInsightsClient.js");
const initialSnapshotsServerPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetInitialSnapshotsServer.js");
const setPageAdaptersPath = path.resolve(__dirname, "../../lib/pokemon/set-page/setPageAdapters.mjs");
const setValueTrendSelectorPath = path.resolve(__dirname, "setValueTrendSelector.mjs");
const setValueContractPath = path.resolve(__dirname, "setValueContract.mjs");
const setHeaderSummarySelectorPath = path.resolve(__dirname, "setHeaderSummarySelector.mjs");
const trendScoresSelectorPath = path.resolve(__dirname, "trendScoresSelector.mjs");
const simulationDriversSelectorPath = path.resolve(__dirname, "simulationDriversSelector.mjs");
const decisionSignalsSelectorPath = path.resolve(__dirname, "decisionSignalsSelector.mjs");
const ripScoreBreakdownSelectorPath = path.resolve(__dirname, "ripScoreBreakdownSelector.mjs");
const dashboardRoutePath = path.resolve(
  __dirname,
  "../../app/api/tcgs/pokemon/sets/[setId]/market/dashboard/route.js"
);
const cardsRoutePath = path.resolve(__dirname, "../../app/api/tcgs/pokemon/sets/[setId]/cards/route.js");
const overviewRoutePath = path.resolve(__dirname, "../../app/api/tcgs/pokemon/sets/[setId]/overview/route.js");
const setPageRoutePath = path.resolve(__dirname, "../../app/api/tcgs/pokemon/sets/[setId]/page/route.js");
const explorePageServicePath = path.resolve(__dirname, "../../../backend/db/services/explore_page_service.py");
const snapshotServicePath = path.resolve(
  __dirname,
  "../../../backend/db/services/pokemon_public_snapshot_service.py"
);
const marketServicePath = path.resolve(
  __dirname,
  "../../../backend/db/services/pokemon_set_market_service.py"
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
  const fetchStart = source.indexOf("getPokemonSetCardsValidation(setId)");
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
  const cardsEffectStart = source.indexOf("getPokemonSetCardsValidation(setId)");
  const cardsGuardStart = source.lastIndexOf("if (!canFetchSetDetailModules)", cardsEffectStart);
  const valueHistoryStart = source.indexOf("getPokemonSetValueHistory(setId, { days: 365, scope })");
  const valueGuardStart = source.lastIndexOf("if (!canFetchSetDetailModules)", valueHistoryStart);
  const marketStart = source.indexOf("getPokemonSetTopChase(setId, { window: topChaseSourceWindow");
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
  // Set Value Trend/Performance vs Cost source from effectiveSetValueDerivedState,
  // which prefers the /overview snapshot once loaded and falls back to
  // activeMarketDashboardDerivedState.setValue until then. Top Chase Cards
  // (activeMarketDashboardDerivedState.topCards, checked below) still reads
  // the market dashboard state directly and is untouched.
  assert.ok(activeHistorySource.includes("effectiveSetValueDerivedState.setValue"));
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
  assert.ok(directEffectSource.includes("const requestedScopes = desiredScopes.filter("));
  assert.ok(directEffectSource.includes("!seededLoadedScopes.includes(scope) && !alreadyLoadedScopes.includes(scope)"));
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
  assert.ok(source.includes('debugSetPagePerf("top_chase.tab_fetch_stale"'), "top chase fetch must guard against a stale active set before applying results");
  assert.ok(source.includes('debugSetPagePerf("market_movers.tab_fetch_stale"'), "market movers fetch must guard against a stale active set before applying results");
  assert.ok(source.includes('debugSetPagePerf("cards.tab_fetch_stale"'), "cards fetch must guard against a stale active set before applying results");
  assert.ok(source.includes('debugSetPagePerf("cards_page.tab_fetch_stale"'), "cards page fetch must guard against a stale active set before applying results");

  // cards (full, Insights-only), cards page (paginated Cards tab), pull rates
  // (Phase 4A), value-history, overview, top-chase, and market-movers
  // fetches each carry this guard shape (the monolithic market-dashboard
  // live fetch was removed — see the split-endpoint tests below). Insights
  // moved off this guard shape in the progressive-rendering refactor: its
  // critical/secondary fetches use useSectionFetchState's own request-id
  // based staleness guard instead (see the Phase 11 Insights tests below).
  const occurrences = source.split(`if (!${guardCall}) {`).length - 1;
  assert.equal(occurrences, 7, "cards, cards page, pull rates, value-history, overview, top-chase, and market-movers fetches must each carry this stale-set guard");
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

test("market dashboard payload exposes distinct 1D/7D/30D market mover rows for the window selector", async () => {
  const { buildMarketDashboardStateFromPayload } = await import(pathToFileURL(marketDashboardStatePath).href);
  const payload = {
    topChaseCards: [],
    setValueHistoriesByScope: { standard: [{ date: "2026-06-01", setValue: 100 }] },
    marketMovers: { window: "30D", heatingUp: [{ cardId: "card-30d", name: "30D Gainer" }], coolingOff: [] },
    marketMoversByWindow: {
      "1D": { heatingUp: [{ cardId: "card-1d", name: "1D Gainer" }], coolingOff: [] },
      "7D": { heatingUp: [], coolingOff: [{ cardId: "card-7d", name: "7D Decliner" }] },
      "30D": { heatingUp: [{ cardId: "card-30d", name: "30D Gainer" }], coolingOff: [] },
    },
  };

  const marketState = buildMarketDashboardStateFromPayload(payload);
  const { marketMoversByWindow } = marketState.topCards;

  assert.ok(marketMoversByWindow, "marketMoversByWindow must be exposed on topCards");
  assert.equal(marketMoversByWindow["1D"].heatingUp[0].cardId, "card-1d");
  assert.equal(marketMoversByWindow["1D"].coolingOff.length, 0);
  assert.equal(marketMoversByWindow["7D"].heatingUp.length, 0);
  assert.equal(marketMoversByWindow["7D"].coolingOff[0].cardId, "card-7d");
  assert.equal(marketMoversByWindow["30D"].heatingUp[0].cardId, "card-30d");
  // Selecting a different window must actually change which rows would render —
  // the three windows must not collapse to the same data.
  assert.notDeepEqual(marketMoversByWindow["1D"], marketMoversByWindow["7D"]);
  assert.notDeepEqual(marketMoversByWindow["7D"], marketMoversByWindow["30D"]);
});

test("Market Movers module supports a 1D/7D/30D window selector defaulting to 30D", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const componentStart = source.indexOf("function MarketMoversModule(");
  const componentEnd = source.indexOf("\nfunction normalizePullRateAssumptions");
  assert.ok(componentStart >= 0, "MarketMoversModule must exist");
  const componentSource = source.slice(componentStart, componentEnd);

  assert.ok(source.includes('const DEFAULT_MARKET_MOVERS_WINDOW = "30D"'));
  assert.ok(
    source.includes("const MARKET_MOVERS_WINDOW_OPTIONS = [") &&
      source.includes('{ key: "1D", label: "1D" }') &&
      source.includes('{ key: "7D", label: "7D" }') &&
      source.includes('{ key: "30D", label: "30D" }'),
    "window options must offer exactly 1D/7D/30D"
  );
  // 3M/6M/1Y/Lifetime are a deliberate follow-up, not part of this change.
  assert.ok(!source.includes('{ key: "3M", label: "3M" }'));
  assert.ok(!source.includes('{ key: "1Y", label: "1Y" }'));
  assert.ok(!source.includes('{ key: "lifetime", label: "Lifetime" }'));

  // The window selector is now lifted to the parent component (so it can
  // drive the /market/movers fetch effect per selected window) instead of
  // living as local state inside MarketMoversModule.
  assert.ok(
    componentSource.includes(
      '{ movers, moversByWindow, selectedWindow, status = "success", error, onWindowChange, onViewAll }'
    )
  );
  assert.ok(!componentSource.includes("useState(DEFAULT_MARKET_MOVERS_WINDOW)"), "window state must be lifted to the parent, not local to the module");
  assert.ok(componentSource.includes("resolvedMoversByWindow[selectedWindow]"));
  assert.ok(componentSource.includes("<MarketWindowSelector"));
  assert.ok(componentSource.includes("windows={MARKET_MOVERS_WINDOW_OPTIONS}"));
  assert.ok(componentSource.includes("value={selectedWindow}"));
  assert.ok(componentSource.includes("onChange={onWindowChange}"));
  assert.ok(componentSource.includes("`${selectedWindow} card price movement with noise guardrails applied.`"));
  assert.ok(componentSource.includes("Ranks card-level ${selectedWindow} movement"));

  assert.ok(source.includes("const [marketMoversWindowKey, setMarketMoversWindowKey] = useState(DEFAULT_MARKET_MOVERS_WINDOW)"), "parent must own the selected movers window state, defaulting to 30D");
  assert.ok(source.includes("moversByWindow={marketMoversByWindow}"));
  assert.ok(source.includes("selectedWindow={marketMoversWindowKey}"));
  assert.ok(source.includes("onWindowChange={setMarketMoversWindowKey}"));
  assert.ok(source.includes("onViewAll={handleViewAllMarketMovers}"), "View all movers behavior must be unchanged");
});

test("top chase cards and market movers each fetch their own canonical slim endpoint, and the live market dashboard fetch is gone", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const dashboardCallCount = (source.match(/getPokemonSetMarketDashboard\(/g) || []).length;
  const topChaseCallCount = (source.match(/getPokemonSetTopChase\(/g) || []).length;
  const marketMoversCallCount = (source.match(/getPokemonSetMarketMovers\(/g) || []).length;

  assert.equal(dashboardCallCount, 0, "the live /market/dashboard fetch must be fully removed");
  assert.equal(topChaseCallCount, 1, "top chase cards must fetch exactly once via the slim /market/top-chase endpoint");
  assert.equal(marketMoversCallCount, 1, "market movers must fetch exactly once via the slim /market/movers endpoint");
  assert.ok(source.includes("const [marketDashboardState, dispatchMarketDashboard] = useReducer("));
  assert.ok(source.includes("const [topChaseState, dispatchTopChase] = useReducer("));
  assert.ok(source.includes("const [marketMoversState, dispatchMarketMovers] = useReducer("));
  assert.ok(source.includes("buildMarketDashboardStateFromPayload(activeMarketDashboardState.payload || seededMarketDashboardPayload)"));
  assert.ok(!source.includes("setTopMarketCardsState"));
  assert.ok(!source.includes("applyMarketDashboardPayload"));
});

// ---------------------------------------------------------------------------
// Overview module parity (regression fix) — the live /market/movers fetch
// resolves to a flat { heatingUp, coolingOff, all, window } object (see
// normalizeMarketMoversPayload in pokemonSetMarketClient.js), the same shape
// hasMarketMoverRows/MarketMoversModule read directly. Reading it back out
// through an extra `.marketMovers` key (matching only the legacy monolithic
// /market/dashboard payload shape) silently discarded the live per-window
// fetch's data, so Market Movers always fell back to the (now-empty, since
// /market/dashboard is no longer live-fetched) dashboard-seeded state and
// never rendered. This did not surface as a fetch failure or console error —
// the request succeeded, the data just never reached the module.
// ---------------------------------------------------------------------------

test("Overview parity: the live market movers fetch result is read back in its normalized (flat) shape, not double-nested", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(
    source.includes("const marketMoversLive = activeMarketMoversState.payload || null;"),
    "marketMoversLive must read activeMarketMoversState.payload directly — getPokemonSetMarketMovers's normalized " +
      "payload is already the flat { heatingUp, coolingOff, all, window } shape, not wrapped in a `.marketMovers` key " +
      "(activeMarketMoversState is the resolvedSetResourceId-guarded read of marketMoversState — see the set-switch " +
      "stale-state regression test below)"
  );
  assert.ok(
    !source.includes("const marketMoversLive = activeMarketMoversState.payload?.marketMovers"),
    "must not regress to reading a nonexistent nested `.marketMovers` key off the slim /market/movers payload"
  );
});

test("Overview parity: getPokemonSetMarketMovers's normalized payload shape matches what hasMarketMoverRows/MarketMoversModule read", async () => {
  const { normalizeMarketMoversPayload } = await import(pathToFileURL(marketClientPath).href);

  // Shape returned by GET /tcgs/pokemon/sets/{id}/market/movers (backend
  // get_pokemon_set_market_movers_payload), as consumed by
  // getPokemonSetMarketMovers in pokemonSetMarketClient.js.
  const backendResponse = {
    set: { id: "set-1", name: "Prismatic Evolutions", slug: "prismaticEvolutions" },
    window: "30D",
    windowDays: 30,
    marketMovers: {
      window: "30D",
      windowDays: 30,
      heatingUp: [{ cardId: "card-1", name: "Sylveon ex", currentPrice: 555.64, change30dAmount: 50.18 }],
      coolingOff: [{ cardId: "card-2", name: "Flareon ex", currentPrice: 223.42, change30dAmount: -10.5 }],
      all: [],
    },
    meta: { warnings: [] },
  };

  const normalized = normalizeMarketMoversPayload(backendResponse);

  // This is exactly what marketMoversLive is set to (marketMoversState.payload
  // directly) and exactly what hasMarketMoverRows(entry) reads — entry.heatingUp
  // / entry.coolingOff at the top level, not entry.marketMovers.heatingUp.
  assert.ok(Array.isArray(normalized.heatingUp), "normalized payload must expose heatingUp at the top level");
  assert.ok(Array.isArray(normalized.coolingOff), "normalized payload must expose coolingOff at the top level");
  assert.equal(normalized.heatingUp.length, 1);
  assert.equal(normalized.coolingOff.length, 1);
  assert.equal(normalized.marketMovers, undefined, "the normalized payload must not be double-nested under a marketMovers key");
});

test("Overview parity: Market Movers and Top Chase Cards are both still rendered inside the overview tab's JSX block", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const overviewBlockStart = source.indexOf('{setDetailTab === "overview" ? (');
  assert.ok(overviewBlockStart >= 0, "the overview tab conditional render block must exist");
  const overviewBlockEnd = source.indexOf("<MarketMoversModule", overviewBlockStart);
  assert.ok(overviewBlockEnd > overviewBlockStart, "MarketMoversModule must render inside the overview tab block");

  const topChaseBlockEnd = source.indexOf("<TopChaseCardsModule", overviewBlockEnd);
  assert.ok(topChaseBlockEnd > overviewBlockEnd, "TopChaseCardsModule must render inside the overview tab block, after MarketMoversModule");

  // Both must appear before the overview block's own closing `) : null}` —
  // approximated by asserting no earlier/later tab conditional interrupts
  // between the overview block start and the TopChaseCardsModule render.
  const nextTabBlockStart = source.indexOf('setDetailTab === "cards"', overviewBlockStart);
  assert.ok(
    nextTabBlockStart === -1 || nextTabBlockStart > topChaseBlockEnd,
    "MarketMoversModule/TopChaseCardsModule must render before any subsequent tab block, i.e. still inside overview"
  );
});

// ---------------------------------------------------------------------------
// Phase 5A — post-split regression stabilization. Market Movers and Top Chase
// Cards previously disappeared entirely (no loading/empty state) whenever the
// slim /market/movers or /market/top-chase fetch hadn't resolved yet, or
// resolved to genuinely zero rows with no cards/dashboard fallback available.
// Both section containers must now always render on Overview; only their
// inner content (loading skeleton / error / empty message / real rows) may
// vary. Verified live against a local dev server + backend: see the task
// report for browser/network results.
// ---------------------------------------------------------------------------

test("Phase 5A: Overview fetches Top Chase and Market Movers through their slim endpoints", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  assert.ok(source.includes("getPokemonSetTopChase(setId, { window: topChaseSourceWindow, limit: 10 })"), "Top Chase must fetch via getPokemonSetTopChase");
  assert.ok(source.includes("getPokemonSetMarketMovers(setId, { window: moversSourceWindow, limit: 5 })"), "Market Movers must fetch via getPokemonSetMarketMovers");
});

test("Phase 5A: Top Chase Cards section container always renders on Overview, regardless of data availability", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(
    source.includes("const shouldShowTopMarketCards = true;"),
    "shouldShowTopMarketCards must no longer hide the Top Chase Cards container when the slim endpoint is empty/loading"
  );
  // The old data-dependent gate must be gone, not just overridden.
  assert.ok(
    !/const shouldShowTopMarketCards =\s*\n\s*activeTopMarketCardsState\.status/.test(source),
    "must not still branch on activeTopMarketCardsState.status to decide whether to show the container"
  );
});

test("Phase 5A: Market Movers section container always renders on Overview, regardless of data availability", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(
    !source.includes("{hasMarketMovers ? ("),
    "the Market Movers container must no longer be conditionally rendered behind hasMarketMovers"
  );
  const renderStart = source.indexOf('id="set-detail-market-movers"');
  assert.ok(renderStart >= 0, "the Market Movers container div must exist");
  assert.ok(
    source.slice(renderStart, renderStart + 400).includes("<MarketMoversModule"),
    "MarketMoversModule must render unconditionally inside its container div"
  );

  // MarketMoversModule itself must no longer bail out to null just because
  // there are zero rows — it must show a loading skeleton, an error message,
  // or fall through to MarketMoverColumn's own per-column empty state.
  const componentStart = source.indexOf("function MarketMoversModule(");
  const componentEnd = source.indexOf("\nfunction normalizePullRateAssumptions");
  const componentSource = source.slice(componentStart, componentEnd);
  assert.ok(!/if \(!hasAnyWindowMovers\) \{\s*\n\s*return null;/.test(componentSource), "must not early-return null just because there are no mover rows yet");
  assert.ok(componentSource.includes('status === "loading"'), "must render a loading state distinct from the empty state");
  assert.ok(componentSource.includes("<InlinePanelSkeleton"), "must show a loading skeleton while the fetch is in flight");
  assert.ok(componentSource.includes('status === "error"'), "must render an error state instead of silently disappearing");
});

test("Phase 5A: Overview does not require activeMarketDashboardDerivedState to render the Top Chase or Market Movers containers", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  // The render-gating flags themselves must not reference the dashboard
  // derived state — only the data fallback (cards/movers content) may.
  const shouldShowLine = source.split("\n").find((line) => line.includes("const shouldShowTopMarketCards ="));
  assert.ok(shouldShowLine, "shouldShowTopMarketCards must exist");
  assert.ok(
    !shouldShowLine.includes("activeMarketDashboardDerivedState"),
    "shouldShowTopMarketCards must not depend on activeMarketDashboardDerivedState"
  );
  assert.ok(
    !source.includes("{hasMarketMovers ? ("),
    "the Market Movers container render must not be gated on hasMarketMovers"
  );
});

test("Phase 5A: Overview live path does not call getPokemonSetMarketDashboard or fetchPokemonSetPageSnapshot", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const dashboardCallCount = (source.match(/getPokemonSetMarketDashboard\(/g) || []).length;
  assert.equal(dashboardCallCount, 0, "must never call getPokemonSetMarketDashboard");

  const overviewEffectsStart = source.indexOf("// Slim /market/top-chase fetch");
  const overviewEffectsEnd = source.indexOf("// Slim /overview fetch for Set Value Trend/Performance vs Cost only.");
  const overviewEffectsSource = source.slice(overviewEffectsStart, overviewEffectsEnd);
  assert.ok(overviewEffectsStart >= 0 && overviewEffectsEnd > overviewEffectsStart, "top-chase/market-movers effects must exist");
  assert.ok(
    !overviewEffectsSource.includes("fetchPokemonSetPageSnapshot("),
    "Overview's top-chase/market-movers fetch effects must never call the legacy full-page fetch"
  );
});

test("Phase 5A: normal tabs keep their own slim endpoints unchanged (Cards/Pull Rates/Insights/card validation) and adjacent prefetch stays disabled", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  assert.ok(source.includes("getPokemonSetCardsPage("), "Cards tab must still use getPokemonSetCardsPage");
  assert.ok(source.includes("getPokemonSetPullRates("), "Pull Rates tab must still use getPokemonSetPullRates");
  // Insights split into critical/secondary fetches in the progressive-
  // rendering refactor (see the Phase 11 Insights tests below) — the old
  // single getPokemonSetInsights( call site is gone from this file. Each new
  // fetcher is passed by reference to useSectionFetchState rather than
  // called directly, so there's no literal trailing "(" here.
  assert.ok(source.includes("getPokemonSetInsightsCritical"), "Insights tab must reference getPokemonSetInsightsCritical for its critical tier");
  assert.ok(source.includes("getPokemonSetInsightsSecondary"), "Insights tab must reference getPokemonSetInsightsSecondary for its secondary tier");
  assert.ok(source.includes("getPokemonSetCardsValidation("), "card validation must still use getPokemonSetCardsValidation");
  assert.ok(
    source.includes("const SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD = new Set([]);"),
    "no normal tab may require the full /page payload"
  );
  assert.ok(source.includes("const SET_PREFETCH_ADJACENT_LIMIT = 0"), "adjacent prefetch must remain disabled by default");
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

test("market dashboard window keys are canonical for the cache-hydration fallback and the legacy dashboard route", () => {
  const ripSource = fs.readFileSync(ripPageClientPath, "utf8");
  const marketSource = fs.readFileSync(marketClientPath, "utf8");
  const dashboardRoute = fs.readFileSync(dashboardRoutePath, "utf8");

  assert.ok(marketSource.includes("export function normalizeMarketDashboardWindow"));
  assert.ok(marketSource.includes(".toLowerCase()"));
  assert.ok(marketSource.includes("window=${normalizeMarketDashboardWindow(window)}"));
  assert.ok(marketSource.includes('params.set("window", normalizedWindow)'));
  assert.ok(ripSource.includes('const DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW = "365d"'));
  // The live fetch is gone, but the fallback hydration path still reads the
  // 365d-keyed cache/seed so a previously-fetched dashboard snapshot for this
  // set still backs Top Chase Cards/Market Movers until their own fetches land.
  assert.ok(ripSource.includes("getCachedPokemonSetMarketDashboard(setId, { window: dashboardSourceWindow })"));
  assert.ok(dashboardRoute.includes("normalizeMarketDashboardWindow(window)"));
});

test("top chase and market movers request windows are canonical", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const marketSource = fs.readFileSync(marketClientPath, "utf8");

  assert.ok(source.includes('const DEFAULT_TOP_CHASE_MARKET_WINDOW = "30D"'));
  assert.ok(source.includes("const topChaseSourceWindow = DEFAULT_TOP_CHASE_MARKET_WINDOW"));
  assert.ok(source.includes("getPokemonSetTopChase(setId, { window: topChaseSourceWindow"));
  assert.ok(source.includes('const [marketMoversWindowKey, setMarketMoversWindowKey] = useState(DEFAULT_MARKET_MOVERS_WINDOW)'));
  assert.ok(source.includes("getPokemonSetMarketMovers(setId, { window: moversSourceWindow"));
  assert.ok(marketSource.includes("export async function getPokemonSetTopChase"));
  assert.ok(marketSource.includes("export async function getPokemonSetMarketMovers"));
});

test("market movers effect refetches by selected window and top chase effect does not depend on it", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const moversEffectStart = source.indexOf("getPokemonSetMarketMovers(setId, { window: moversSourceWindow");
  const moversEffectDepsStart = source.indexOf("}, [", moversEffectStart);
  const moversEffectDepsEnd = source.indexOf("]);", moversEffectDepsStart);
  const moversEffectDeps = source.slice(moversEffectDepsStart, moversEffectDepsEnd);
  assert.ok(moversEffectStart >= 0, "market movers effect must exist");
  assert.ok(
    moversEffectDeps.includes("marketMoversWindowKey"),
    "the market movers effect must re-run (and refetch) when the selected window changes"
  );

  const topChaseEffectStart = source.indexOf("getPokemonSetTopChase(setId, { window: topChaseSourceWindow");
  const topChaseEffectDepsStart = source.indexOf("}, [", topChaseEffectStart);
  const topChaseEffectDepsEnd = source.indexOf("]);", topChaseEffectDepsStart);
  const topChaseEffectDeps = source.slice(topChaseEffectDepsStart, topChaseEffectDepsEnd);
  assert.ok(
    !topChaseEffectDeps.includes("marketMoversWindowKey"),
    "the top chase effect must not refetch just because the movers window selector changed"
  );
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
  assert.ok(source.includes("const summary = { ...(effectiveShellPayload?.summary || {}), ...(explorePayload?.summary || {}) };"));

  for (const field of requiredFields) {
    assert.ok(snapshotBuilderSource.includes(field), `snapshot builder propagates ${field}`);
    assert.ok(source.includes(field), `frontend normalizer accepts ${field}`);
  }

  const summaryStart = source.indexOf("const summary = { ...(effectiveShellPayload?.summary || {}), ...(explorePayload?.summary || {}) };");
  const comparisonStart = source.indexOf("const ripDesirabilityComparison = useMemo(", summaryStart);
  const comparisonEnd = source.indexOf("const desirabilitySummary", comparisonStart);
  const comparisonSource = source.slice(comparisonStart, comparisonEnd);
  const insightsStart = source.indexOf('{setDetailMode ? (', comparisonEnd);
  const insightsEnd = source.indexOf("<DesirabilityEvidenceCard", insightsStart);
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

test("overview proxy route serves no-store on failure and public cache on success", () => {
  const source = fs.readFileSync(overviewRoutePath, "utf8");

  assert.ok(source.includes('const PUBLIC_ANALYTICS_CACHE_CONTROL = "public, s-maxage=300, stale-while-revalidate=3600"'));
  assert.ok(source.includes('const FAILED_ANALYTICS_CACHE_CONTROL = "no-store"'));
  assert.ok(
    source.includes("proxyResponse.ok ? PUBLIC_ANALYTICS_CACHE_CONTROL : FAILED_ANALYTICS_CACHE_CONTROL"),
    "cache-control selection must be conditional on proxyResponse.ok"
  );
  assert.ok(source.includes('cache: "no-store"'), "the backend fetch itself must not use Next's fetch-level cache");
  assert.ok(!source.includes("next: { revalidate"), "must not pass next: { revalidate } to fetch");
});

test("backend set resolver accepts URL slugs like journey-together, shared across page/shell/cards/market/value-history", () => {
  // The normalized-slug resolver lives once in pokemon_set_market_service.py
  // (resolve_pokemon_set_identifier) and is shared by every set route,
  // including pokemon_public_snapshot_service.py (page/shell/cards/market
  // dashboard/top-cards) — it must not be reimplemented per module.
  const marketSource = fs.readFileSync(marketServicePath, "utf8");
  const snapshotSource = fs.readFileSync(snapshotServicePath, "utf8");

  assert.ok(marketSource.includes("def resolve_pokemon_set_identifier"));
  assert.ok(marketSource.includes("def _normalise_set_lookup_key"));
  assert.ok(marketSource.includes("resolved set identifier by normalized slug"));
  assert.ok(marketSource.includes('row.get("name")'));
  assert.ok(marketSource.includes('row.get("canonical_key")'));

  assert.ok(!snapshotSource.includes("def _normalise_set_lookup_key"), "must not reimplement the normalized-slug fallback locally");
  assert.ok(snapshotSource.includes("resolve_pokemon_set_identifier(set_id, client=public_read_client)"));
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
  const helperEnd = source.indexOf("function CardDesirabilityMarketValidationContent", helperStart);
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

test("desirability evidence proof content renders from set payload validation data", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("function DesirabilityEvidenceCard"));
  assert.ok(source.includes("function DesirabilityProofContent"));
  assert.ok(source.includes('title="Desirability Evidence"'));
  assert.ok(source.includes('label: "Proof"'));
  assert.ok(source.includes('label: "Set Validation"'));
  assert.ok(source.includes('label: "Card Validation"'));
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
  assert.ok(
    source.includes("checklistState.setId === resolvedSetResourceId && checklistState.cards.length > 0"),
    "activeCardValidationData must only trust checklistState.cards when it belongs to the active set"
  );
  assert.ok(
    source.includes("? checklistState.cards\r\n        : initialCardAppealRows") ||
      source.includes("? checklistState.cards\n        : initialCardAppealRows"),
    "must fall back to the seeded initial rows when checklistState isn't for the active set yet"
  );
  assert.ok(source.includes("resolvePreferredCardAppealCorrelation({"));
  assert.ok(source.includes("cardsPayload: initialCardsPayload"));
  assert.ok(source.includes("previous: initialCardAppealMarketPriceCorrelation"));
  assert.ok(diagnosticsSource.indexOf("asObject(cardsPayload?.cardAppealMarketPriceCorrelation)") < diagnosticsSource.indexOf("asObject(checklistState?.cardAppealMarketPriceCorrelation)"));
});

test("card validation section renders from an explicit readiness contract instead of ad-hoc inline fallbacks", () => {
  // Regression guard: CardDesirabilityMarketValidationCard previously read
  // `checklistState.cards.length > 0 ? checklistState.cards : initialCardAppealRows`
  // and re-called resolvePreferredCardAppealCorrelation directly in the JSX,
  // with no notion of "cards/correlation haven't loaded yet" — so on
  // Insights/Pull-Rates first load (cards aren't seeded server-side there)
  // it rendered a permanent-looking "Not enough card appeal and market price
  // data yet." / n=0 empty state instead of a loading state, until switching
  // tabs happened to trigger the cards fetch. activeCardValidationData now
  // owns that readiness distinction.
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const memoStart = source.indexOf("const activeCardValidationData = useMemo(");
  assert.ok(memoStart >= 0, "must define an activeCardValidationData memo");
  const memoEnd = source.indexOf("const [topMarketCardsWindowKey", memoStart);
  const memoSource = source.slice(memoStart, memoEnd);

  assert.ok(memoSource.includes("hasUsableCardAppealCorrelation(correlation)"), "must classify readiness using hasUsableCardAppealCorrelation");
  assert.ok(memoSource.includes('status === "loading"'), "must treat an in-flight checklist fetch as loading");
  assert.ok(memoSource.includes('status === "idle"'), "must treat the pre-fetch idle state as loading");
  assert.ok(memoSource.includes("checklistState.setId !== resolvedSetResourceId"), "must treat a stale/mismatched set id as loading");
  assert.ok(memoSource.includes('setDetailTab === "insights"'), "must scope the loading classification to the insights tab");

  const renderStart = source.indexOf("<DesirabilityEvidenceCard");
  const renderEnd = source.indexOf("/>", renderStart);
  const renderSource = source.slice(renderStart, renderEnd);

  assert.ok(renderSource.includes("cards={activeCardValidationData.cards}"), "must render cards from the readiness contract");
  assert.ok(
    renderSource.includes("cardAppealMarketPriceCorrelation={activeCardValidationData.correlation}"),
    "must render correlation from the readiness contract instead of an inline resolvePreferredCardAppealCorrelation call"
  );
  assert.ok(
    renderSource.includes('dataLoading={activeCardValidationData.status === "loading"}'),
    "must pass the readiness contract's loading status through to the card"
  );
  assert.ok(
    !renderSource.includes("resolvePreferredCardAppealCorrelation({"),
    "must not re-resolve correlation inline in JSX now that activeCardValidationData owns it"
  );

  const componentStart = source.indexOf("function CardDesirabilityMarketValidationContent(");
  const componentEnd = source.indexOf("\n}\n", componentStart);
  const componentSource = source.slice(componentStart, componentEnd);

  assert.ok(componentSource.includes("dataLoading = false"), "component must accept a dataLoading prop");
  assert.ok(
    componentSource.includes('"Loading card appeal and market price data…"'),
    "component must render a distinct loading message instead of the permanent-looking \"not enough data\" copy while data is loading"
  );
  assert.ok(
    componentSource.indexOf('"Loading card appeal and market price data…"') <
      componentSource.indexOf('"Not enough card appeal and market price data yet."'),
    "the loading message must be checked before falling through to the permanent-looking not-enough-data copy"
  );
});

test("initial cards payload seeds checklist state before cards fetch", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const stateStart = source.indexOf("const [checklistState, setChecklistState] = useState(() => ({");
  const effectStart = source.indexOf("getPokemonSetCardsValidation(setId)", stateStart);
  const effectSource = source.slice(stateStart, effectStart);
  const thenStart = source.indexOf("getPokemonSetCardsValidation(setId)");
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

test("timeout fallback does not block cards, top chase, or set value fetches when set resource id is resolved", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const cardsEffectStart = source.indexOf("getPokemonSetCardsValidation(setId)");
  const marketStart = source.indexOf("getPokemonSetTopChase(setId, { window: topChaseSourceWindow");
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

test("Phase 4B: no tab may trigger a full /page fetch anymore; insights was removed alongside pull-rates", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(
    source.includes("const SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD = new Set([]);"),
    "no tab may trigger a full /page fetch now that insights has its own slim contract"
  );
  assert.ok(!/SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD = new Set\(\[[^\]]*(cards|overview|pull-rates|insights)/i.test(source), "cards/overview/pull-rates/insights must never be included");
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

test("overview top chase error handling keeps stale/seeded data instead of blanking the tab", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const marketEffectStart = source.indexOf("getPokemonSetTopChase(setId, { window: topChaseSourceWindow");
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

// ---------------------------------------------------------------------------
// Patch 2 — Temporal Forces title-card blank-state guard. A set switch can
// leave the shellPayload prop holding the previous set's data for a render or
// two; the title card must neither leak the previous set's metrics under the
// new set's name, nor flash "Coming soon"/"—" for metrics the (not-yet-
// matched) shell actually has. It must show a pending state until a matching
// shell arrives, and same-set cached data may render as stale.
// ---------------------------------------------------------------------------

test("buildSetHeaderSummary ignores a shell payload whose identity does not match the active set", async () => {
  const { buildSetHeaderSummary } = await import(pathToFileURL(setHeaderSummarySelectorPath).href);

  const previousSetShell = {
    set: { id: "prev-set", name: "Phantasmal Flames" },
    summary: { pack_score: 88, pack_rank: 3, pack_cost: 4.5, mean_value: 9.9, average_hit_value: 20, prob_profit: 0.6, prob_big_hit: 0.1 },
  };

  // Active set is Temporal Forces, but the shell prop still holds the previous
  // set. With the mismatch flag, none of the previous set's numbers may leak.
  const mismatched = buildSetHeaderSummary({
    explorePayload: null,
    shellPayload: previousSetShell,
    selectedTarget: { id: "temporal-forces", name: "Temporal Forces" },
    resolvedSetResourceId: "temporal-forces",
    explorePayloadIsFresh: false,
    shellPayloadIsForActiveSet: false,
  });
  assert.equal(mismatched.score, null, "previous set's score must not leak under the new set's title");
  assert.equal(mismatched.packCost, null, "previous set's pack cost must not leak");
  assert.equal(mismatched.expectedValue, null, "previous set's expected value must not leak");
  assert.notEqual(mismatched.set.name, "Phantasmal Flames", "previous set's name must not leak from the mismatched shell");
  assert.equal(mismatched.diagnostics.usedShellPayload, false, "a mismatched shell must not be recorded as used");
  assert.equal(mismatched.diagnostics.shellPayloadIgnoredIdentityMismatch, true, "the mismatch must be recorded in diagnostics");

  // With the matching flag, the same shell IS used (default true keeps the
  // pre-existing behavior for the common case).
  const matched = buildSetHeaderSummary({
    explorePayload: null,
    shellPayload: { set: { id: "temporal-forces", name: "Temporal Forces" }, summary: previousSetShell.summary },
    selectedTarget: { id: "temporal-forces", name: "Temporal Forces" },
    resolvedSetResourceId: "temporal-forces",
    explorePayloadIsFresh: false,
    shellPayloadIsForActiveSet: true,
  });
  assert.equal(matched.score, 88, "a matching shell must still populate the header metrics");
  assert.equal(matched.packCost, 4.5, "a matching shell must still populate pack cost");
  assert.equal(matched.diagnostics.usedShellPayload, true, "a matching shell must be recorded as used");
});

test("Patch 2: client gates the header shell on identity match and passes it into buildSetHeaderSummary", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const guardStart = source.indexOf("const shellPayloadIsForActiveSet = useMemo(");
  assert.ok(guardStart >= 0, "a shellPayloadIsForActiveSet identity guard must exist");
  const guardEnd = source.indexOf("}, [shellPayload, resolvedSetResourceId]);", guardStart);
  assert.ok(guardEnd > guardStart, "the shell guard memo must close on [shellPayload, resolvedSetResourceId]");
  const guardSource = source.slice(guardStart, guardEnd);
  assert.ok(guardSource.includes("getSetSnapshotIdentity(shellPayload)"), "the guard must derive the shell's own identity");
  assert.ok(guardSource.includes("setIdentityMatchesTarget(shellIdentity, resolvedSetResourceId)"), "the guard must compare shell identity to the active set");
  assert.ok(guardSource.includes("getSetIdentityTokens(shellIdentity).length === 0"), "an identity-less shell must stay usable (no false mismatch)");

  assert.ok(
    source.includes("const effectiveShellPayload = shellPayloadIsForActiveSet ? shellPayload : null;"),
    "an effectiveShellPayload must null out a mismatched shell"
  );
  // The summary/interpretation/shell-contract merges must consume the guarded
  // shell, not the raw prop, so a mismatched shell can't leak into them.
  assert.ok(
    source.includes("const summary = { ...(effectiveShellPayload?.summary || {}), ...(explorePayload?.summary || {}) };"),
    "the summary merge must use the guarded shell"
  );
  assert.ok(
    source.includes("const interpretation = explorePayload?.interpretation || effectiveShellPayload?.interpretation || {};"),
    "interpretation must fall back to the guarded shell"
  );
  assert.ok(
    source.includes("...(effectiveShellPayload || {}),") && source.includes("summary: { ...(effectiveShellPayload?.summary || {}), ...(explorePayload?.summary || {}) },"),
    "setShellContract must be built from the guarded shell"
  );
  assert.ok(
    source.includes("shellPayloadIsForActiveSet,"),
    "the guard flag must be threaded into buildSetHeaderSummary"
  );
});

test("Patch 2: set-switch pending state exists and replaces placeholder metric values", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const pendingStart = source.indexOf("const titleCardMetricsPending =");
  assert.ok(pendingStart >= 0, "a titleCardMetricsPending flag must exist");
  const pendingEnd = source.indexOf(";", pendingStart);
  const pendingSource = source.slice(pendingStart, pendingEnd);
  assert.ok(pendingSource.includes("!isPrimarySnapshotReady"), "pending requires no fresh explore payload");
  assert.ok(pendingSource.includes("!shellPayloadIsForActiveSet"), "pending requires no matching shell");
  assert.ok(
    pendingSource.includes("setHeaderSummary.score === null") && pendingSource.includes("setHeaderSummary.setValue.current === null"),
    "pending requires the header summary to have come out empty (no same-set cache filled it)"
  );

  // The known shell metrics must render the pending placeholder, not
  // "Coming soon", while pending.
  assert.ok(
    source.includes("const formatHeaderMetric = (value, formatter) =>") &&
      source.includes("titleCardMetricsPending\n        ? titleMetricPendingPlaceholder\n        : \"Coming soon\""),
    "header metric tiles must show the pending placeholder (not 'Coming soon') during a switch"
  );
  for (const field of [
    "setHeaderSummary.packCost",
    "setHeaderSummary.expectedValue",
    "setHeaderSummary.averageHitValue",
    "setHeaderSummary.averageLoss",
    "setHeaderSummary.chanceToBeatPackCost",
    "setHeaderSummary.chanceAtBigPull",
  ]) {
    assert.ok(source.includes(`formatHeaderMetric(${field}`), `${field} must route through formatHeaderMetric`);
  }
  // RIP score and set value get pending treatment too.
  assert.ok(
    source.includes("titleCardMetricsPending && setHeaderSummary.score === null ? ("),
    "the RIP score must render a pending skeleton instead of a placeholder score during a switch"
  );
  assert.ok(
    source.includes("setHeaderSummary.setValue.current === null\n                                    ? titleCardMetricsPending\n                                      ? titleMetricPendingPlaceholder"),
    "the set value must render the pending placeholder during a switch"
  );
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

  // Patch 2: the shell fallback now goes through the identity-guarded
  // effectiveShellPayload so a mismatched (previous-set) shell can't leak its
  // interpretation under the new set's title — behavior is otherwise unchanged
  // (the matching set's shell interpretation still survives tab switches).
  assert.ok(
    source.includes(
      "const interpretation = explorePayload?.interpretation || effectiveShellPayload?.interpretation || {};"
    ),
    "interpretation must fall back to the identity-guarded shell so Decision Signals / recommendation text survive tab switches without leaking a mismatched set"
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

// ---------------------------------------------------------------------------
// Phase 3A — lock in the split-contract architecture and guard against
// regressing back to the monolithic /market/dashboard payload.
// ---------------------------------------------------------------------------

test("Phase 3A: RipStatisticsPageClient does not import the live getPokemonSetMarketDashboard fetch", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const marketSource = fs.readFileSync(marketClientPath, "utf8");

  const importBlockStart = source.indexOf('from "@/lib/pokemon/pokemonSetMarketClient"');
  const importBlockStart2 = source.lastIndexOf("import {", importBlockStart);
  const importBlock = source.slice(importBlockStart2, importBlockStart);

  assert.ok(importBlock.includes("getCachedPokemonSetMarketDashboard"), "the cache-read helper must still be imported for the fallback path");
  assert.ok(!importBlock.includes("getPokemonSetMarketDashboard,"), "the live-fetch helper must not be imported");
  assert.ok(!importBlock.includes("getPokemonSetMarketDashboard\n"), "the live-fetch helper must not be imported (last import in block)");
  assert.ok(importBlock.includes("getPokemonSetTopChase"), "top chase must be imported");
  assert.ok(importBlock.includes("getPokemonSetMarketMovers"), "market movers must be imported");
  assert.ok(importBlock.includes("getPokemonSetOverview"), "overview must be imported");

  // The legacy helper is intentionally kept alive in the client module itself
  // (not deleted) for any remaining legacy caller — it just must not be
  // RipStatisticsPageClient's live source anymore.
  assert.ok(marketSource.includes("export async function getPokemonSetMarketDashboard("), "legacy helper must still exist in pokemonSetMarketClient.js");
  assert.ok(marketSource.includes("export function normalizeMarketDashboardPayload("), "normalizeMarketDashboardPayload must still exist");
});

test("Phase 3A: no live /market/dashboard fetch call exists anywhere in RipStatisticsPageClient", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const dashboardCallCount = (source.match(/getPokemonSetMarketDashboard\(/g) || []).length;
  assert.equal(dashboardCallCount, 0, "no call site may invoke the live getPokemonSetMarketDashboard fetch");
});

test("Phase 3A: Overview tab activation only ever hydrates marketDashboardState from cache/seed, never a live fetch", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  // The hydration-only effect is anchored by its own explanatory comment.
  const effectStart = source.indexOf("Top Chase Cards and Market Movers now fetch their own slim");
  assert.ok(effectStart >= 0, "the cache-hydration-only market dashboard effect must exist with its explanatory comment");
  const effectBodyEnd = source.indexOf("}, [", effectStart);
  const effectBody = source.slice(effectStart, effectBodyEnd);

  assert.ok(effectBody.includes('setDetailTab === "overview"'), "hydration must still be scoped to the overview tab");
  assert.ok(effectBody.includes("getCachedPokemonSetMarketDashboard("), "must read from cache");
  assert.ok(effectBody.includes("hydrateMarketDashboardStateFromCachedPayload("), "must hydrate via the cached-payload helper");
  assert.ok(!effectBody.includes("await getPokemonSetMarketDashboard"), "must never await a live fetch");
});

test("Phase 3A: Top Chase live fetch path calls getPokemonSetTopChase", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const topChaseEffectStart = source.indexOf("getPokemonSetTopChase(setId, { window: topChaseSourceWindow");
  assert.ok(topChaseEffectStart >= 0, "top chase effect must call getPokemonSetTopChase");
  const dispatchStart = source.lastIndexOf("dispatchTopChase({ type: \"loading\"", topChaseEffectStart);
  assert.ok(dispatchStart >= 0 && dispatchStart < topChaseEffectStart, "must dispatch loading before calling getPokemonSetTopChase");
});

test("Phase 3A: Market Movers live fetch path calls getPokemonSetMarketMovers with the selected window", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("const moversSourceWindow = marketMoversWindowKey || DEFAULT_MARKET_MOVERS_WINDOW"), "movers fetch must derive its window from the selected window state");
  assert.ok(source.includes("getPokemonSetMarketMovers(setId, { window: moversSourceWindow"), "must call getPokemonSetMarketMovers with the derived window");
  assert.ok(source.includes("selectedWindow={marketMoversWindowKey}"), "MarketMoversModule must be driven by the same selected-window state");
});

test("Phase 3A: dev-only warning fires when a legacy market dashboard payload backs the Overview fallback", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const warnStart = source.indexOf("Overview is using a legacy /market/dashboard payload as a fallback");
  assert.ok(warnStart >= 0, "must define a console.warn call for the legacy fallback path");
  const warnCallStart = source.lastIndexOf("console.warn(", warnStart);
  assert.ok(warnCallStart >= 0 && warnCallStart < warnStart, "the legacy-payload message must be inside a console.warn call");
  const warnGuardStart = source.lastIndexOf("if (isDevPerfLoggingEnabled) {", warnCallStart);
  assert.ok(warnGuardStart >= 0 && warnGuardStart < warnStart, "console.warn must be gated behind isDevPerfLoggingEnabled so it never fires in production");
  const warnBlockEnd = source.indexOf("dispatchMarketDashboard({", warnStart);
  const warnBlock = source.slice(warnGuardStart, warnBlockEnd);
  assert.ok(warnBlock.includes("legacy /market/dashboard payload"), "warning message must call out the legacy payload path");
});

test("Phase 3A: SET_PREFETCH_ADJACENT_LIMIT remains 0 and no fanout was reintroduced", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("const SET_PREFETCH_ADJACENT_LIMIT = 0"), "adjacent prefetch must remain disabled by default");
  const topChaseCallCount = (source.match(/getPokemonSetTopChase\(/g) || []).length;
  const marketMoversCallCount = (source.match(/getPokemonSetMarketMovers\(/g) || []).length;
  assert.equal(topChaseCallCount, 1, "top chase must be called exactly once (active set only, no adjacent fanout)");
  assert.equal(marketMoversCallCount, 1, "market movers must be called exactly once (active set only, no adjacent fanout)");
});

// ---------------------------------------------------------------------------
// Phase 3B — Cards tab uses a slim, paginated contract instead of the giant
// full /cards payload.
// Phase 3C — Insights' card validation section now also uses its own slim
// contract (getPokemonSetCardsValidation) instead of the full /cards
// payload. The legacy getPokemonSetCards/normalizePokemonSetCardsPayload
// helpers are kept in pokemonSetCardsClient.js for backward compatibility,
// but no normal set detail live effect calls them anymore.
// ---------------------------------------------------------------------------

test("Phase 3C: RipStatisticsPageClient imports getPokemonSetCardsPage and getPokemonSetCardsValidation, not the legacy getPokemonSetCards", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const cardsClientSource = fs.readFileSync(cardsClientPath, "utf8");

  const importBlockStart = source.lastIndexOf("import {", source.indexOf('from "@/lib/pokemon/pokemonSetCardsClient"'));
  const importBlockEnd = source.indexOf('from "@/lib/pokemon/pokemonSetCardsClient"');
  const importBlock = source.slice(importBlockStart, importBlockEnd);

  assert.ok(importBlock.includes("getPokemonSetCardsPage"), "must import getPokemonSetCardsPage");
  assert.ok(importBlock.includes("getPokemonSetCardsValidation"), "must import getPokemonSetCardsValidation for Insights");
  assert.ok(
    !importBlock.split(",").some((entry) => entry.trim() === "getPokemonSetCards"),
    "must not import the legacy getPokemonSetCards fetch function anymore — no live effect calls it"
  );
  assert.ok(cardsClientSource.includes("export async function getPokemonSetCardsPage"), "client must export getPokemonSetCardsPage");
  assert.ok(cardsClientSource.includes("export async function getPokemonSetCardsValidation"), "client must export getPokemonSetCardsValidation");
  assert.ok(cardsClientSource.includes("export function normalizePokemonSetCardsPayload"), "legacy normalizePokemonSetCardsPayload must not be removed");
  assert.ok(cardsClientSource.includes("export async function getPokemonSetCards("), "legacy getPokemonSetCards may still exist in the client for backward compatibility");
  assert.ok(cardsClientSource.includes("export function normalizePokemonSetCardsValidationPayload"), "client must export normalizePokemonSetCardsValidationPayload");
});

test("Phase 3B: Cards tab live path calls getPokemonSetCardsPage exactly once (active set only)", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const cardsPageCallCount = (source.match(/getPokemonSetCardsPage\(/g) || []).length;
  assert.equal(cardsPageCallCount, 1, "getPokemonSetCardsPage must be called from exactly one call site (active set only, no adjacent fanout)");

  const effectStart = source.indexOf("Cards tab: slim, paginated fetch (getPokemonSetCardsPage)");
  assert.ok(effectStart >= 0, "the cards-page fetch effect must exist with its explanatory comment");
  const effectBodyEnd = source.indexOf("}, [", effectStart);
  const effectBody = source.slice(effectStart, effectBodyEnd);
  assert.ok(effectBody.includes('shouldRenderCardsPage = setDetailTab === "cards" && cardsSubTab === "checklist"'), "must gate the fetch on the cards checklist sub-tab");
  assert.ok(effectBody.includes("getPokemonSetCardsPage(setId,"), "must call getPokemonSetCardsPage");
});

test("Phase 3B: Cards tab does not call the legacy getPokemonSetCards for its own live page load", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const shouldRenderChecklistStart = source.indexOf("const shouldRenderChecklist = setDetailTab ===");
  assert.ok(shouldRenderChecklistStart >= 0, "the full-cards effect's gate must exist");
  assert.ok(
    source.slice(shouldRenderChecklistStart, shouldRenderChecklistStart + 80).includes('setDetailTab === "insights"'),
    "the full-cards effect must gate its live fetch on insights only, not the cards tab"
  );
  assert.ok(
    !source.slice(shouldRenderChecklistStart, shouldRenderChecklistStart + 80).includes('"cards"'),
    "the full-cards effect's live-fetch gate must not reference the cards tab anymore"
  );

  const cardsPageEffectStart = source.indexOf("Cards tab: slim, paginated fetch (getPokemonSetCardsPage)");
  const cardsPageEffectEnd = source.indexOf("}, [", cardsPageEffectStart);
  const cardsPageEffectBody = source.slice(cardsPageEffectStart, cardsPageEffectEnd);
  assert.ok(!cardsPageEffectBody.includes("getPokemonSetCards("), "the cards-page effect must never call the legacy full getPokemonSetCards");
});

test("Phase 3C: getPokemonSetInitialSnapshots no longer fetches full cards for tab === \"cards\" or tab === \"insights\"", () => {
  const source = fs.readFileSync(initialSnapshotsServerPath, "utf8");

  assert.ok(!source.includes("const wantsCards ="), "wantsCards gating must be removed — no tab route-seeds the full cards snapshot anymore");
  assert.ok(!source.includes('tab === "cards" || tab === "insights"'), "must not fetch full cards for the cards tab anymore");

  const fnStart = source.indexOf("export async function getPokemonSetInitialSnapshots");
  const fnEnd = source.indexOf("\n}\n", fnStart);
  const fnSource = source.slice(fnStart, fnEnd);
  assert.ok(
    !fnSource.includes("getPokemonSetCardsInitialSnapshot("),
    "getPokemonSetInitialSnapshots must never call getPokemonSetCardsInitialSnapshot anymore (the function may still exist as a legacy helper)"
  );
});

test("Phase 3C: Insights card validation live path calls getPokemonSetCardsValidation and no longer calls the legacy getPokemonSetCards", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const serverSource = fs.readFileSync(initialSnapshotsServerPath, "utf8");

  assert.ok(!serverSource.includes("const wantsCards ="), "server seed must no longer fetch full cards for insights");
  const shouldRenderChecklistStart = source.indexOf("const shouldRenderChecklist = setDetailTab ===");
  assert.ok(
    source.slice(shouldRenderChecklistStart, shouldRenderChecklistStart + 80).includes('setDetailTab === "insights"'),
    "the client card validation live fetch must still run for the insights tab"
  );
  assert.ok(source.includes("getPokemonSetCardsValidation(setId)"), "the live card validation fetch call must exist for insights");

  const checklistEffectStart = shouldRenderChecklistStart;
  const checklistEffectEnd = source.indexOf("\n  }, [", checklistEffectStart);
  const checklistEffectBody = source.slice(checklistEffectStart, checklistEffectEnd);
  assert.ok(
    !checklistEffectBody.includes("getPokemonSetCards(setId)"),
    "Insights must no longer call the legacy full getPokemonSetCards(setId)"
  );

  const cardsPageEffectStart = source.indexOf("Cards tab: slim, paginated fetch (getPokemonSetCardsPage)");
  const cardsPageEffectEnd = source.indexOf("}, [", cardsPageEffectStart);
  const cardsPageEffectBody = source.slice(cardsPageEffectStart, cardsPageEffectEnd);
  assert.ok(cardsPageEffectBody.includes("getPokemonSetCardsPage(setId,"), "Cards tab must still use getPokemonSetCardsPage");
});

test("Phase 3B: cards page fetch is not fanned out across adjacent sets", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("const SET_PREFETCH_ADJACENT_LIMIT = 0"), "adjacent prefetch must remain disabled by default");
  const cardsPageCallCount = (source.match(/getPokemonSetCardsPage\(/g) || []).length;
  assert.equal(cardsPageCallCount, 1, "cards page must be fetched for the active set only, never adjacent sets");

  const warmupStart = source.indexOf("const warmSetDetailResources = useCallback");
  const warmupEnd = source.indexOf("const outcomeDistributionInfo", warmupStart);
  const warmupSource = source.slice(warmupStart, warmupEnd);
  assert.ok(!warmupSource.includes("getPokemonSetCardsPage("), "warmup must not fetch the cards page directly");
});

// ---------------------------------------------------------------------------
// Phase 4A — Pull Rates tab uses its own slim contract (getPokemonSetPullRates)
// instead of requiring the full /page payload. Phase 4B (below) does the same
// for Insights (getPokemonSetInsights), so no set-detail tab depends on the
// full /page payload anymore.
// ---------------------------------------------------------------------------

test("Phase 4A: RipStatisticsPageClient imports getPokemonSetPullRates and the client exports it", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const pullRatesClientSource = fs.readFileSync(pullRatesClientPath, "utf8");

  assert.ok(
    source.includes('import { getPokemonSetPullRates } from "@/lib/pokemon/pokemonSetPullRatesClient";'),
    "must import getPokemonSetPullRates from the new slim client"
  );
  assert.ok(
    pullRatesClientSource.includes("export async function getPokemonSetPullRates"),
    "client must export getPokemonSetPullRates"
  );
  assert.ok(
    pullRatesClientSource.includes("export function normalizePokemonSetPullRatesPayload"),
    "client must export normalizePokemonSetPullRatesPayload"
  );
});

test("Phase 4A: Pull Rates tab live path calls getPokemonSetPullRates", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const effectStart = source.indexOf("// Pull Rates tab fetch effect (Phase 4A)");
  const effectEnd = source.indexOf(
    "}, [setDetailMode, setDetailTab, requestedTargetId, selectedTarget, resolvedSetResourceId, canFetchSetDetailModules]);",
    effectStart
  );
  assert.ok(effectStart >= 0, "the pull rates fetch effect must exist");
  const effectBody = source.slice(effectStart, effectEnd);

  assert.ok(effectBody.includes('setDetailTab !== "pull-rates"'), "the effect must gate on the pull-rates tab");
  assert.ok(effectBody.includes("getPokemonSetPullRates(setId)"), "must call getPokemonSetPullRates for the active set");
});

test("Phase 4A: Pull Rates tab does not call fetchPokemonSetPageSnapshot", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const effectStart = source.indexOf("// Pull Rates tab fetch effect (Phase 4A)");
  const effectEnd = source.indexOf(
    "}, [setDetailMode, setDetailTab, requestedTargetId, selectedTarget, resolvedSetResourceId, canFetchSetDetailModules]);",
    effectStart
  );
  const effectBody = source.slice(effectStart, effectEnd);

  assert.ok(
    !effectBody.includes("fetchPokemonSetPageSnapshot("),
    "the pull rates effect must never call the legacy full-page fetch"
  );
});

test("Phase 4A: Cards tab still uses getPokemonSetCardsPage", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const cardsPageEffectStart = source.indexOf("Cards tab: slim, paginated fetch (getPokemonSetCardsPage)");
  const cardsPageEffectEnd = source.indexOf("}, [", cardsPageEffectStart);
  const cardsPageEffectBody = source.slice(cardsPageEffectStart, cardsPageEffectEnd);
  assert.ok(cardsPageEffectBody.includes("getPokemonSetCardsPage(setId,"), "Cards tab must still use getPokemonSetCardsPage");
});

test("Phase 4A: SET_PREFETCH_ADJACENT_LIMIT remains 0 and pull rates fetch is not fanned out", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  assert.ok(source.includes("const SET_PREFETCH_ADJACENT_LIMIT = 0"), "adjacent prefetch must remain disabled by default");
  const pullRatesCallCount = (source.match(/getPokemonSetPullRates\(/g) || []).length;
  assert.equal(pullRatesCallCount, 1, "pull rates must be fetched for the active set only, never adjacent sets");
});

// ---------------------------------------------------------------------------
// Phase 4B — Insights tab uses its own slim contract (getPokemonSetInsights)
// instead of requiring the full /page payload. No set-detail tab depends on
// the full /page payload anymore; the legacy /page endpoint and
// fetchPokemonSetPageSnapshot remain (now permanently inert on this page)
// only for non-"set" target types and any other legacy caller.
// ---------------------------------------------------------------------------

// Phase 4B originally moved Insights onto one slim getPokemonSetInsights
// fetch. The progressive-rendering refactor (Phase 11) split that into two
// independent fetches — critical (priorities 1-3) and secondary (priorities
// 4-5) — each with its own client module, fired in parallel via
// useSectionFetchState. The old pokemonSetInsightsClient.js / /insights
// endpoint are deliberately left in place (unused by this file) rather than
// deleted — see the plan's "don't delete existing endpoints" risk note.
test("Phase 11: RipStatisticsPageClient imports the split insights critical/secondary clients and both export their fetchers", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const criticalClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetInsightsCriticalClient.js");
  const secondaryClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetInsightsSecondaryClient.js");
  const criticalClientSource = fs.readFileSync(criticalClientPath, "utf8");
  const secondaryClientSource = fs.readFileSync(secondaryClientPath, "utf8");

  assert.ok(
    source.includes('import { getPokemonSetInsightsCritical } from "@/lib/pokemon/pokemonSetInsightsCriticalClient";'),
    "must import getPokemonSetInsightsCritical from the new slim client"
  );
  assert.ok(
    source.includes('import { getPokemonSetInsightsSecondary } from "@/lib/pokemon/pokemonSetInsightsSecondaryClient";'),
    "must import getPokemonSetInsightsSecondary from the new slim client"
  );
  assert.ok(criticalClientSource.includes("export async function getPokemonSetInsightsCritical"), "critical client must export its fetcher");
  assert.ok(secondaryClientSource.includes("export async function getPokemonSetInsightsSecondary"), "secondary client must export its fetcher");
  assert.ok(
    criticalClientSource.includes("export function normalizePokemonSetInsightsCriticalPayload"),
    "critical client must export its normalizer"
  );
  assert.ok(
    secondaryClientSource.includes("export function normalizePokemonSetInsightsSecondaryPayload"),
    "secondary client must export its normalizer"
  );
  assert.ok(!source.includes('import { getPokemonSetInsights } from "@/lib/pokemon/pokemonSetInsightsClient";'), "the old single-fetch import must be gone");
});

test("Phase 11: Insights tab fetches critical and secondary in parallel via useSectionFetchState, gated on the insights tab", () => {
  // This file has mixed CRLF/LF line endings — normalize before multi-line
  // indexOf/substring anchors (see feedback-crlf-line-endings-in-source-string-tests).
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(source.includes('import { useSectionFetchState } from "@/hooks/useSectionFetchState";'), "must import the shared fetch-state hook");

  const enabledStart = source.indexOf("const insightsFetchEnabled =");
  const enabledEnd = source.indexOf(";", enabledStart);
  const enabledSource = source.slice(enabledStart, enabledEnd);
  assert.ok(enabledSource.includes('setDetailTab === "insights"'), "fetching must be gated on the insights tab being active");
  assert.ok(enabledSource.includes("canFetchSetDetailModules"), "fetching must respect the shared canFetchSetDetailModules gate");

  assert.ok(
    source.includes("useSectionFetchState(\n    getPokemonSetInsightsCritical,\n    { setId: resolvedSetResourceId, enabled: insightsFetchEnabled }\n  );"),
    "critical fetch must use useSectionFetchState with the shared enabled flag"
  );
  assert.ok(
    source.includes("useSectionFetchState(\n    getPokemonSetInsightsSecondary,\n    { setId: resolvedSetResourceId, enabled: insightsFetchEnabled }\n  );"),
    "secondary fetch must use useSectionFetchState with the same shared enabled flag, so both fire in parallel"
  );
});

test("Phase 11: critical and secondary Insights payloads each merge only their own slice into explorePayload", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(
    source.includes("function adaptPokemonSetInsightsCriticalPayloadToExplorePayload(critical)"),
    "a dedicated critical adapter must exist"
  );
  assert.ok(
    source.includes("function adaptPokemonSetInsightsSecondaryPayloadToExplorePayload(secondary)"),
    "a dedicated secondary adapter must exist"
  );

  const criticalMergeStart = source.indexOf("if (insightsCriticalFetchState.status !== \"success\"");
  const secondaryMergeStart = source.indexOf("if (insightsSecondaryFetchState.status !== \"success\"");
  assert.ok(criticalMergeStart >= 0, "the critical merge effect must exist");
  assert.ok(secondaryMergeStart >= 0, "the secondary merge effect must exist");

  const criticalMergeSource = source.slice(criticalMergeStart, source.indexOf("}, [insightsCriticalFetchState.status", criticalMergeStart));
  const secondaryMergeSource = source.slice(secondaryMergeStart, source.indexOf("}, [insightsSecondaryFetchState.status", secondaryMergeStart));

  assert.ok(criticalMergeSource.includes("setExplorePayload((previous) => ("), "critical merge must use a functional update, not clobber concurrent secondary writes");
  assert.ok(criticalMergeSource.includes("...adaptPokemonSetInsightsCriticalPayloadToExplorePayload(insightsCriticalFetchState.data)"), "critical merge must spread only critical fields");
  assert.ok(secondaryMergeSource.includes("setExplorePayload((previous) => ("), "secondary merge must use a functional update, not clobber concurrent critical writes");
  assert.ok(
    secondaryMergeSource.includes("adaptPokemonSetInsightsSecondaryPayloadToExplorePayload(insightsSecondaryFetchState.data)"),
    "secondary merge must adapt the secondary payload"
  );
  assert.ok(secondaryMergeSource.includes("...secondarySlice"), "secondary merge must spread only the adapted secondary slice");
  // Stabilization pass: the secondary merge must be observable in perf debug
  // output with the row counts the DB-vs-UI investigation needs.
  assert.ok(secondaryMergeSource.includes('debugSetPagePerf("insights.secondary_merged"'), "secondary merge must emit a debug log");
  for (const field of ["setId", "topHitsCount", "percentilesCount", "distributionBinsCount", "rankingsCount", "historyTrendCount", "payloadSource"]) {
    assert.ok(secondaryMergeSource.includes(field), `secondary merge debug log must include ${field}`);
  }

  // Each merge only applies data recorded for the currently-resolved set,
  // guarding against a late response landing after a set switch (the same
  // class of guard isSetStateForActiveSet provides for the other per-tab
  // fetches, expressed here via useSectionFetchState's own setId field).
  assert.ok(criticalMergeSource.includes("insightsCriticalFetchState.setId !== resolvedSetResourceId"), "critical merge must guard against a stale set");
  assert.ok(secondaryMergeSource.includes("insightsSecondaryFetchState.setId !== resolvedSetResourceId"), "secondary merge must guard against a stale set");
});

test("Phase 4B: summary-only payloads do not count as loaded Insights data", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");
  const helperStart = source.indexOf("function hasInsightsPayloadData(payload)");
  const helperEnd = source.indexOf("function getResolvedPokemonSetResourceId", helperStart);
  assert.ok(helperStart >= 0, "hasInsightsPayloadData helper must exist");
  assert.ok(helperEnd > helperStart, "hasInsightsPayloadData helper must live near the insights adapter/readiness helpers");
  const helperSource = source.slice(helperStart, helperEnd);

  for (const expected of [
    "distribution_bins",
    "distributionBins",
    "threshold_bins",
    "thresholdBins",
    "percentiles",
    "top_hits",
    "topHits",
    "rankings",
    "history_trend",
    "historyTrend",
    "rip_statistics",
    "ripStatistics",
    "openingDesirability",
    "opening_desirability",
    "desirabilityValidation",
    "desirability_validation",
    "hasDesirabilityProofSignal",
  ]) {
    assert.ok(helperSource.includes(expected), `helper must inspect ${expected}`);
  }
  assert.ok(!helperSource.includes("payload.summary"), "summary alone must not count as insights data");
});

test("Insights readiness is declared after setDetailTab", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const setDetailTabIndex = source.indexOf("const [setDetailTab");
  const hasActiveInsightsPayloadIndex = source.indexOf("const hasActiveInsightsPayload =");

  assert.ok(setDetailTabIndex >= 0, "setDetailTab must be declared");
  assert.ok(hasActiveInsightsPayloadIndex >= 0, "hasActiveInsightsPayload must be declared");
  assert.ok(
    setDetailTabIndex < hasActiveInsightsPayloadIndex,
    "hasActiveInsightsPayload must not read setDetailTab before setDetailTab is initialized"
  );
});

test("Phase 4B/11: Insights tab does not call fetchPokemonSetPageSnapshot", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  const effectStart = source.indexOf("// Insights tab fetch effects (progressive-rendering split");
  const effectEnd = source.indexOf(
    "}, [insightsSecondaryFetchState.status, insightsSecondaryFetchState.setId, insightsSecondaryFetchState.data, resolvedSetResourceId]);",
    effectStart
  );
  assert.ok(effectStart >= 0, "the insights merge effects must exist");
  assert.ok(effectEnd > effectStart, "the secondary merge effect must close after the critical one");
  const effectBody = source.slice(effectStart, effectEnd);

  assert.ok(
    !effectBody.includes("fetchPokemonSetPageSnapshot("),
    "the insights fetch effects must never call the legacy full-page fetch"
  );
});

test("Phase 4B: SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD is empty and no server route seeds the full /page payload for any set-detail tab", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  assert.ok(
    source.includes("const SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD = new Set([]);"),
    "no tab may require the full /page payload anymore"
  );

  const setSlugPagePath = path.resolve(__dirname, "../../app/TCGs/Pokemon/Sets/[setSlug]/page.js");
  const setSlugPageSource = fs.readFileSync(setSlugPagePath, "utf8");
  assert.ok(
    !setSlugPageSource.includes('activeSetDetailTab === "insights"'),
    "the server route must no longer seed the full /page payload for insights"
  );
  assert.ok(
    !setSlugPageSource.includes('activeSetDetailTab === "pull-rates"'),
    "the server route must no longer seed the full /page payload for pull-rates"
  );
  assert.ok(
    setSlugPageSource.includes('const needsExplorePagePayload = requestedTargetType !== "set";'),
    "the full /page payload must only be seeded for non-set target types now"
  );
});

test("Phase 4B: Cards still uses getPokemonSetCardsPage, Pull Rates still uses getPokemonSetPullRates, card validation still uses getPokemonSetCardsValidation", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  assert.ok(source.includes("getPokemonSetCardsPage("), "Cards tab must still use getPokemonSetCardsPage");
  assert.ok(source.includes("getPokemonSetPullRates("), "Pull Rates tab must still use getPokemonSetPullRates");
  assert.ok(source.includes("getPokemonSetCardsValidation("), "card validation must still use getPokemonSetCardsValidation");
  assert.ok(source.includes("getPokemonSetOverview("), "Overview must still use getPokemonSetOverview");
  assert.ok(source.includes("getPokemonSetTopChase("), "Overview must still use getPokemonSetTopChase");
  assert.ok(source.includes("getPokemonSetMarketMovers("), "Overview must still use getPokemonSetMarketMovers");
});

test("Phase 4B/11: SET_PREFETCH_ADJACENT_LIMIT remains 0 and insights critical/secondary fetches are not fanned out", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  assert.ok(source.includes("const SET_PREFETCH_ADJACENT_LIMIT = 0"), "adjacent prefetch must remain disabled by default");
  const insightsCriticalCallCount = (source.match(/getPokemonSetInsightsCritical(?!\w)/g) || []).length;
  const insightsSecondaryCallCount = (source.match(/getPokemonSetInsightsSecondary(?!\w)/g) || []).length;
  // One import + one useSectionFetchState call site each (the fetch itself
  // happens inside the shared hook, not fanned out per adjacent set here).
  assert.equal(insightsCriticalCallCount, 2, "insights critical must be referenced for the active set's fetch only, never adjacent sets");
  assert.equal(insightsSecondaryCallCount, 2, "insights secondary must be referenced for the active set's fetch only, never adjacent sets");
});

// ---------------------------------------------------------------------------
// Phase 6A: set-switch stale-state guard (regression fix) — topChaseState,
// marketMoversState, overviewState, and cardsPageState each only reset to the
// newly-selected set's "loading"/empty shape once their own fetch effect
// fires (and those effects are gated on the matching tab being active, e.g.
// setDetailTab === "overview"). If the user switches sets while on a
// different tab (or the effect just hasn't committed yet), reading these
// reducer/state values raw at render time can render the *previous* set's
// cards/top-chase/movers/overview payload under the *new* set's title —
// exactly the class of bug activeMarketDashboardState/
// activeDirectSetValueState already guard against via a
// `.setId === resolvedSetResourceId` check. These assertions pin the same
// guard on the four modules that were missing it.
// ---------------------------------------------------------------------------

test("Phase 6A: topChaseState/marketMoversState/overviewState/cardsPageState are read through a resolvedSetResourceId-guarded derived value, not raw", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("const activeOverviewState ="), "overviewState must have a guarded derived value");
  assert.ok(
    source.includes("overviewState.setId === resolvedSetResourceId"),
    "overviewState must be guarded by a resolvedSetResourceId check before being read at render time"
  );
  assert.ok(source.includes("const activeTopChaseState ="), "topChaseState must have a guarded derived value");
  assert.ok(
    source.includes("topChaseState.setId === resolvedSetResourceId"),
    "topChaseState must be guarded by a resolvedSetResourceId check before being read at render time"
  );
  assert.ok(source.includes("const activeMarketMoversState ="), "marketMoversState must have a guarded derived value");
  assert.ok(
    source.includes("marketMoversState.setId === resolvedSetResourceId"),
    "marketMoversState must be guarded by a resolvedSetResourceId check before being read at render time"
  );
  assert.ok(source.includes("const activeCardsPageState ="), "cardsPageState must have a guarded derived value");
  assert.ok(
    source.includes("cardsPageState.setId === resolvedSetResourceId"),
    "cardsPageState must be guarded by a resolvedSetResourceId check before being read at render time"
  );

  // The raw reducer/state values must no longer be read directly anywhere
  // outside their own declaration and fetch effect (which legitimately read
  // their own previous value to decide the next dispatch/request). The one
  // exception is topChaseState.setId, which appears exactly once — inside
  // activeTopChaseState's own guard condition above.
  const rawOverviewReads = (source.match(/overviewState\.(payload|status)\b/g) || []).length;
  const rawTopChaseReads = (source.match(/topChaseState\.(payload|status|error)\b/g) || []).length;
  const topChaseSetIdReads = (source.match(/topChaseState\.setId\b/g) || []).length;
  const rawMarketMoversReads = (source.match(/marketMoversState\.(payload|status|error)\b/g) || []).length;
  const rawCardsPageReads = (source.match(/cardsPageState\.(cards|status|error|pagination)\b/g) || []).length;

  assert.equal(rawOverviewReads, 0, "overviewState.payload/status must not be read directly anymore — use activeOverviewState");
  assert.equal(rawTopChaseReads, 0, "topChaseState.payload/status/error must not be read directly anymore — use activeTopChaseState");
  assert.equal(topChaseSetIdReads, 1, "topChaseState.setId must only appear in activeTopChaseState's own guard condition");
  assert.equal(rawMarketMoversReads, 0, "marketMoversState.payload/status/error must not be read directly anymore — use activeMarketMoversState");
  assert.equal(rawCardsPageReads, 0, "cardsPageState.cards/status/error/pagination must not be read directly anymore — use activeCardsPageState");
});

// ---------------------------------------------------------------------------
// Phase 6B: duplicate request audit (regression fix) — browser measurement
// showed getPokemonSetCardsPage firing 3x on a single initial Cards-tab load
// (getPokemonSetCardsPage had no in-flight join, unlike every other slim
// endpoint in pokemonSetMarketClient.js), and getPokemonSetValueHistory
// re-firing on every tab switch (Cards -> Pull Rates -> Insights -> Overview)
// even when the "standard" scope was already loaded, because the effect only
// checked seed/dashboard-cache sources, never its own previously-fetched
// setValueHistoryState. These assertions pin both fixes.
// ---------------------------------------------------------------------------

test("Phase 6B: getPokemonSetCardsPage joins concurrent identical requests, same pattern as the slim market client", () => {
  const source = fs.readFileSync(cardsClientPath, "utf8");

  // Renamed in Phase 6C from cardsPageInflight/joinCardsPageRequest when the
  // same join was extended to getPokemonSetCardsValidation — keys are
  // namespaced per endpoint so the two never collide.
  assert.ok(source.includes("const cardsClientInflight = new Map();"), "cards client must have its own in-flight map");
  assert.ok(source.includes("function joinCardsClientRequest("), "cards client must expose a join helper");

  const fnStart = source.indexOf("export async function getPokemonSetCardsPage(");
  const fnEnd = source.indexOf("\nexport ", fnStart + 1);
  const fnSource = source.slice(fnStart, fnEnd < 0 ? source.length : fnEnd);

  assert.ok(fnStart >= 0, "getPokemonSetCardsPage must exist");
  assert.ok(fnSource.includes("joinCardsClientRequest("), "getPokemonSetCardsPage must route its fetch through the in-flight join");
  assert.ok(fnSource.includes("cacheKey = `cards-page:"), "the join key must be built from the resolved set id and request params");
});

test("Phase 6B: Cards tab fetch effect skips re-issuing an identical page/sort/filter request via a stable request-key ref", () => {
  // Normalize CRLF -> LF: this file has mixed line endings, and multi-line
  // anchors like "\n\n  useEffect(() => {" silently fail to match against a
  // "\r\n\r\n  useEffect(() => {" run without this.
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes("const lastCardsPageRequestKeyRef = useRef(null);"),
    "must track the last cards-page request key issued, to skip identical repeats across tab revisits"
  );

  const effectStart = source.indexOf('debugSetPagePerf("cards_page.tab_fetch_start"');
  const effectSectionStart = source.lastIndexOf("useEffect(() => {", effectStart);
  const effectSectionEnd = source.indexOf("\n\n  useEffect(() => {", effectStart);
  const effectSource = source.slice(effectSectionStart, effectSectionEnd);

  assert.ok(effectSectionStart >= 0 && effectSectionEnd > effectSectionStart);
  assert.ok(
    effectSource.includes("const cardsPageScopeKey = ["),
    "the scope key must be built from every param that changes the fetched resource (set, sort, search, movement filter)"
  );
  assert.ok(
    effectSource.includes("const cardsPageRequestKey = `${cardsPageScopeKey}|page:${requestedPage}`"),
    "the request key must be the scope key plus the requested page"
  );
  assert.ok(
    effectSource.includes("if (lastCardsPageRequestKeyRef.current === cardsPageRequestKey)") &&
      effectSource.includes("return undefined;"),
    "an identical repeated request key must skip re-fetching"
  );
  assert.ok(
    effectSource.includes("lastCardsPageRequestKeyRef.current = cardsPageRequestKey;"),
    "the effect must claim the request key before issuing the fetch"
  );
  assert.ok(
    effectSource.includes("lastCardsPageRequestKeyRef.current = null;"),
    "the claimed key must be released on error so a later retry isn't permanently blocked"
  );
});

test("Phase 6B: set value history direct-fetch effect skips scopes already present in its own setValueHistoryState", () => {
  // Normalize CRLF -> LF (see note above) so the multi-line effect-boundary
  // anchor matches.
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");
  const directFetchStart = source.indexOf('debugSetPagePerf("set_value.direct_fetch_start"');
  const directEffectStart = source.lastIndexOf("useEffect(() => {", directFetchStart);
  const directEffectEnd = source.indexOf("activeMarketDashboardDerivedState,\n  ]);", directFetchStart);
  const directEffectSource = source.slice(directEffectStart, directEffectEnd);

  assert.ok(directEffectStart >= 0 && directEffectEnd > directEffectStart);
  assert.ok(
    directEffectSource.includes(
      "const alreadyLoadedScopes =\n      setValueHistoryState.setId === setId ? setValueHistoryState.loadedScopes || [] : [];"
    ) || directEffectSource.includes("setValueHistoryState.setId === setId ? setValueHistoryState.loadedScopes || [] : [];"),
    "must check the live setValueHistoryState (not just seed/dashboard-cache sources) before deciding which scopes to fetch"
  );
  assert.ok(
    directEffectSource.includes("!seededLoadedScopes.includes(scope) && !alreadyLoadedScopes.includes(scope)"),
    "requestedScopes must exclude scopes already present in either the seed or the effect's own prior state"
  );
});

// ---------------------------------------------------------------------------
// Phase 6C: remaining same-pattern duplicate guards — browser measurement
// showed /pull-rates ×3-4, /cards/validation ×3-4, and /overview,
// /market/top-chase, /market/movers each ×4 on Overview revisit, from the
// same two gaps Phase 6B fixed for cards-page/value-history: no client-level
// in-flight join (concurrent StrictMode remount duplicates) and no effect
// request-key guard (sequential re-runs from tab revisits and prop-identity
// churn after router transitions). These assertions pin both fix layers.
// ---------------------------------------------------------------------------

test("Phase 6C: pull-rates, insights, and cards-validation clients join concurrent identical requests", () => {
  const pullRatesSource = fs.readFileSync(pullRatesClientPath, "utf8");
  assert.ok(pullRatesSource.includes("const pullRatesInflight = new Map();"), "pull-rates client must have an in-flight map");
  assert.ok(pullRatesSource.includes("joinPullRatesRequest(`pull-rates:"), "getPokemonSetPullRates must route through the join");

  const insightsSource = fs.readFileSync(insightsClientPath, "utf8");
  assert.ok(insightsSource.includes("const insightsInflight = new Map();"), "insights client must have an in-flight map");
  assert.ok(insightsSource.includes("joinInsightsRequest(`insights:"), "getPokemonSetInsights must route through the join");

  const cardsSource = fs.readFileSync(cardsClientPath, "utf8");
  const validationStart = cardsSource.indexOf("export async function getPokemonSetCardsValidation(");
  const validationEnd = cardsSource.indexOf("\nexport ", validationStart + 1);
  const validationSource = cardsSource.slice(validationStart, validationEnd < 0 ? cardsSource.length : validationEnd);
  assert.ok(validationStart >= 0, "getPokemonSetCardsValidation must exist");
  assert.ok(
    validationSource.includes("joinCardsClientRequest(") && validationSource.includes("cacheKey = `cards-validation:"),
    "getPokemonSetCardsValidation must route through the shared cards-client join with its own key namespace"
  );
});

test("Phase 6C: every per-tab module fetch effect has a request-key guard that skips identical repeats and releases on error/unsettled cleanup", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const modules = [
    { ref: "lastPullRatesRequestKeyRef", key: "pullRatesRequestKey", skipLog: "pull_rates.tab_fetch_skipped_duplicate" },
    { ref: "lastCardsValidationRequestKeyRef", key: "cardsValidationRequestKey", skipLog: "cards.tab_fetch_skipped_duplicate" },
    { ref: "lastOverviewRequestKeyRef", key: "overviewRequestKey", skipLog: "overview.tab_fetch_skipped_duplicate" },
    { ref: "lastTopChaseRequestKeyRef", key: "topChaseRequestKey", skipLog: "top_chase.tab_fetch_skipped_duplicate" },
    { ref: "lastMarketMoversRequestKeyRef", key: "marketMoversRequestKey", skipLog: "market_movers.tab_fetch_skipped_duplicate" },
  ];

  for (const { ref, key, skipLog } of modules) {
    assert.ok(source.includes(`const ${ref} = useRef(null);`), `${ref} must be declared`);
    assert.ok(
      source.includes(`if (${ref}.current === ${key}) {`),
      `${ref} must skip re-issuing an identical ${key}`
    );
    assert.ok(source.includes(`debugSetPagePerf("${skipLog}"`), `skipping must be observable via ${skipLog}`);
    assert.ok(source.includes(`${ref}.current = ${key};`), `${ref} must claim the key before fetching`);
    // Released on error (retry stays possible) and on unsettled cleanup (a
    // response ignored via isCancelled must not strand the tab in loading).
    const releaseCount = (source.match(new RegExp(`${ref}\\.current = null;`, "g")) || []).length;
    assert.ok(releaseCount >= 2, `${ref} must be released both on error and on unsettled cleanup (found ${releaseCount} release sites)`);
  }

  // The unsettled-cleanup pattern requires each guarded fetch to track
  // settlement — one requestSettled flag per guarded effect (5 above plus
  // the Phase 6B cards-page effect). Insights moved off this hand-rolled
  // requestSettled pattern in the progressive-rendering refactor — its
  // critical/secondary fetches track settlement inside the shared
  // useSectionFetchState hook instead (one implementation, reused, rather
  // than a duplicated inline flag per insights tier).
  const settledFlagCount = (source.match(/let requestSettled = false;/g) || []).length;
  assert.equal(settledFlagCount, 6, "every guarded fetch effect must track request settlement for its cleanup release");
});

// ---------------------------------------------------------------------------
// Phase 8B: hidden/unvalidated-era sets (SWSH pending validation — see
// lib/pokemon/pokemonSetPublicCoverage.js) are excluded from Explore and the
// public Sets catalog, but the set-switcher rail/dropdowns listed the raw
// targets payload, leaving hidden sets one dropdown away from unvalidated
// public analytics (e.g. Evolving Skies showing RIP Score 0.0 / F). The
// switcher option lists must apply the same centralized eligibility filter,
// while direct URLs to a hidden set keep working (the requested target stays
// in the list so the switcher renders a coherent selected option).
// ---------------------------------------------------------------------------

test("Phase 8B: set-switcher option lists filter hidden/unvalidated-era sets via the centralized coverage helper", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes(
      'import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";'
    ),
    "must import the centralized eligibility helper instead of a one-off era check"
  );
  assert.ok(
    !/era\s*===\s*["'`]Sword/i.test(source),
    "must not scatter a one-off `era === \"Sword & Shield\"` check instead of using the centralized helper"
  );

  const switcherMemoStart = source.indexOf("const switcherTargets = useMemo(() => {");
  assert.ok(switcherMemoStart >= 0, "must derive a dedicated switcherTargets list from the raw targets");
  const switcherMemoEnd = source.indexOf("}, [targets, requestedTargetId]);", switcherMemoStart);
  assert.ok(switcherMemoEnd > switcherMemoStart, "switcherTargets must recompute when targets or the requested target change");
  const switcherMemoSource = source.slice(switcherMemoStart, switcherMemoEnd);
  assert.ok(
    switcherMemoSource.includes("isPublicAnalyticsEligiblePokemonSet(target)"),
    "switcherTargets must filter through the centralized public-analytics eligibility helper"
  );
  assert.ok(
    switcherMemoSource.includes('String(target?.target_id || "") === requestedId'),
    "the currently requested target must stay listed even when ineligible, so direct URLs to a hidden set render a coherent switcher"
  );
});

test("Phase 8B: every set-switcher surface renders switcherTargets while non-switcher consumers keep the raw targets list", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes("targets={switcherTargets}"),
    "SetPageNavigationRail (set-detail rail) must receive the filtered switcher list"
  );

  // Explore-mode sidebar select, mobile tools select, and both hero set
  // pickers (set-detail and Explore-mode) — 4 inline option renders total.
  const switcherMapCount = (source.match(/switcherTargets\.map\(/g) || []).length;
  assert.equal(
    switcherMapCount,
    4,
    `all four inline switcher option lists must map over switcherTargets (found ${switcherMapCount})`
  );

  // Non-switcher consumers intentionally stay on the raw list: the
  // Desirability Validation scatter's sample and the adjacent-target route
  // prefetch are not switcher surfaces, and Phase 8B must not silently
  // change analytics-chart contents or prefetch behavior.
  assert.ok(
    source.includes("<DesirabilityEvidenceCard") && source.includes("targets={targets}"),
    "DesirabilityEvidenceCard must keep receiving the unfiltered targets list for its Set Validation mode"
  );
  assert.ok(
    source.includes('const currentIndex = targets.findIndex((target) => String(target?.id || "") === resolvedSetId);'),
    "adjacent-target prefetch must keep walking the unfiltered targets list"
  );
});

// ---------------------------------------------------------------------------
// Phase 9D.2: unified set-tab loading presentation. Every set-detail tab
// (Overview, Cards, Pull Rates, Insights) shows one shared branded loading
// panel (SetTabLoadingPanel, reusing the inDex logo + three-dot loader from
// the route-level loading screens) while that tab's critical data assets are
// loading. Generic circular spinners and per-tab skeleton shells are gone
// from the tab-level loading paths; per-card image placeholders remain for
// lazy image loading only.
// ---------------------------------------------------------------------------

const setTabLoadingPanelPath = path.resolve(__dirname, "SetTabLoadingPanel.jsx");
const inDexLogoLoaderPath = path.resolve(__dirname, "../brand/InDexLogoLoader.jsx");
const exploreRouteLoadingPath = path.resolve(__dirname, "../../app/Explore/loading.js");
const setSlugRouteLoadingPath = path.resolve(__dirname, "../../app/TCGs/Pokemon/Sets/[setSlug]/loading.js");

test("Phase 9D.2: one shared branded SetTabLoadingPanel exists and reuses InDexLogoLoader, with no generic circular spinner", () => {
  const panelSource = fs.readFileSync(setTabLoadingPanelPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    panelSource.includes('import InDexLogoLoader from "@/components/brand/InDexLogoLoader";'),
    "SetTabLoadingPanel must reuse the branded InDexLogoLoader"
  );
  assert.ok(panelSource.includes("<InDexLogoLoader"), "the panel must render the branded loader");
  assert.ok(panelSource.includes("fullScreen={false}"), "the in-tab loader must not use the fullscreen overlay variant");
  assert.ok(panelSource.includes('aria-busy="true"'), "the panel must announce a busy region");
  assert.ok(panelSource.includes("label={title}"), "the loader must receive the panel title as its accessible label");
  assert.ok(!panelSource.includes("animate-spin"), "no generic CSS circular spinner in the shared tab loading panel");

  // The branded loader itself still carries the logo + three-dot treatment
  // the route-level loading screens use.
  const loaderSource = fs.readFileSync(inDexLogoLoaderPath, "utf8").replace(/\r\n/g, "\n");
  assert.ok(loaderSource.includes("index-loader-logo"), "InDexLogoLoader must keep its logo frame");
  const dotCount = (loaderSource.match(/className="index-loader-dot"/g) || []).length;
  assert.equal(dotCount, 3, "InDexLogoLoader must keep the three-dot treatment");
});

test("Phase 9D.2: the page client uses the shared branded panel only for its remaining whole-tab gates (Cards, Insights)", () => {
  // Progressive-rendering refactor: Pull Rates and Overview both moved off
  // the page client's whole-tab SetTabLoadingPanel usage. Pull Rates
  // delegates to PullRatesTab.jsx; Overview gates each of its 5 sections
  // independently via SectionBoundary/SectionErrorBoundary instead of one
  // shared showOverviewCohesiveLoading gate (see the dedicated tests below).
  // Cards and Insights still gate their (not-yet-split) critical paths
  // behind the shared panel directly in this file.
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes('import SetTabLoadingPanel from "@/components/explore/SetTabLoadingPanel";'),
    "the page client must import the shared panel"
  );
  assert.ok(!source.includes("animate-spin"), "the generic circular spinner markup must be gone from the page client");

  const panelUsageCount = (source.match(/<SetTabLoadingPanel/g) || []).length;
  assert.equal(
    panelUsageCount,
    2,
    `Cards and Insights must each render the shared panel exactly once (found ${panelUsageCount})`
  );

  assert.ok(
    source.includes('import PullRatesTab from "@/components/pokemon/set-page/PullRates/PullRatesTab";'),
    "the page client must delegate the Pull Rates tab to the new section-split container"
  );
  assert.ok(
    !source.includes("pullRatesTabPending ? ("),
    "the old inline whole-tab pending branch for Pull Rates must be gone from the page client"
  );
  assert.ok(
    !source.includes("showOverviewCohesiveLoading"),
    "the Overview whole-tab cohesive loading gate must be gone from the page client"
  );
});

test("Phase 11: Overview renders 5 priority-ordered sections, each independently error-isolated, with no whole-tab loading gate", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const renderStart = source.indexOf('id="set-detail-overview" className="scroll-mt-24 space-y-5 md:scroll-mt-28"');
  assert.ok(renderStart >= 0, "the Overview section render must exist");
  const renderEnd = source.indexOf("</section>", renderStart);
  const renderSource = source.slice(renderStart, renderEnd);

  assert.ok(
    source.includes('import SectionErrorBoundary from "@/components/ui/SectionErrorBoundary";'),
    "the page client must import the shared render-error boundary"
  );
  assert.ok(
    source.includes('import SectionBoundary from "@/components/ui/SectionBoundary";'),
    "the page client must import the shared section boundary"
  );

  const errorBoundaryCount = (renderSource.match(/<SectionErrorBoundary/g) || []).length;
  assert.equal(errorBoundaryCount, 5, `Overview must wrap exactly 5 sections in SectionErrorBoundary (found ${errorBoundaryCount})`);

  const setValueIndex = renderSource.indexOf("<SetValueTrendCard");
  const perfIndex = renderSource.indexOf("<SectionBoundary");
  const moversIndex = renderSource.indexOf("<MarketMoversModule");
  const chaseIndex = renderSource.indexOf("<TopChaseCardsModule");
  const signalsIndex = renderSource.indexOf("<DecisionSignalsCard");
  assert.ok(
    setValueIndex >= 0 && perfIndex > setValueIndex && moversIndex > perfIndex && chaseIndex > moversIndex && signalsIndex > chaseIndex,
    "sections must render in priority order: Set Value, Performance vs Cost, Market Movers, Top Chase, Market Signals"
  );

  assert.ok(
    renderSource.includes("status={overviewPerformanceVsCostStatus}"),
    "Performance vs Cost must gate on its own /overview payload status independently of the other sections"
  );
  assert.ok(
    renderSource.includes("status={activeSetValueHistory.status}"),
    "Set Value must keep reading its own independent fetch status"
  );
  assert.ok(
    renderSource.includes("status={marketMoversStatus}"),
    "Market Movers must keep reading its own independent fetch status"
  );
  assert.ok(
    renderSource.includes("status={topPricedCardsStatus}"),
    "Top Chase Cards must keep reading its own independent fetch status"
  );
});

test("Phase 11: Overview reports section-level timing metrics via useSectionTiming", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes('import { useSectionTiming } from "@/hooks/useSectionTiming";'),
    "the page client must import the shared timing hook"
  );

  for (const metric of ["setValue", "performanceVsCost", "marketMovers", "topChase", "marketSignals"]) {
    assert.ok(
      source.includes(`useSectionTiming("${metric}",`),
      `Overview must report the ${metric}Ms metric via useSectionTiming`
    );
  }
});

// Progressive-rendering refactor: Pull Rates is the first tab split into
// priority-ordered section boundaries (Hit Rate Summary -> Pull Rate Table ->
// Source & Reference -> Advanced Odds), each independently gated via the
// shared SectionBoundary/SectionErrorBoundary primitives instead of one
// whole-tab SetTabLoadingPanel gate. The underlying fetch (pullRatesState,
// request-key dedupe, 8s timeout escape) is deliberately untouched in
// RipStatisticsPageClient.jsx — only PullRatesTab.jsx's render changed.
const pullRatesTabPath = path.resolve(__dirname, "../pokemon/set-page/PullRates/PullRatesTab.jsx");
const pullRateAssumptionsCardPath = path.resolve(__dirname, "../pokemon/set-page/PullRates/PullRateAssumptionsCard.jsx");

test("Phase 11: PullRatesTab composes 4 priority-ordered SectionBoundary sections and keeps the timeout/empty copy", () => {
  const source = fs.readFileSync(pullRatesTabPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes('import SectionBoundary from "@/components/ui/SectionBoundary";'),
    "PullRatesTab must use the shared SectionBoundary primitive"
  );
  assert.ok(
    source.includes('import SectionErrorBoundary from "@/components/ui/SectionErrorBoundary";'),
    "PullRatesTab must wrap sections in the shared render-error boundary"
  );

  const sectionBoundaryCount = (source.match(/<SectionBoundary/g) || []).length;
  assert.equal(sectionBoundaryCount, 4, `PullRatesTab must render exactly 4 section boundaries (found ${sectionBoundaryCount})`);

  const errorBoundaryCount = (source.match(/<SectionErrorBoundary/g) || []).length;
  assert.equal(errorBoundaryCount, 4, `each of the 4 sections must be wrapped in its own SectionErrorBoundary (found ${errorBoundaryCount})`);

  assert.ok(source.includes("<HitRateSummarySection"), "Hit Rate Summary (priority 2) must render");
  assert.ok(source.includes("<PullRateTableSection"), "Pull Rate Table (priority 3) must render");
  assert.ok(source.includes("<SourceReferenceSection"), "Source & Reference (priority 4) must render");
  assert.ok(source.includes("<AdvancedOddsSection"), "Advanced Odds (priority 5) must render");

  // Priority order must match the summary -> table -> sources -> advanced
  // sequence, so higher-priority content never renders after lower-priority
  // content in source order.
  const summaryIndex = source.indexOf("<HitRateSummarySection");
  const tableIndex = source.indexOf("<PullRateTableSection");
  const sourcesIndex = source.indexOf("<SourceReferenceSection");
  const advancedIndex = source.indexOf("<AdvancedOddsSection");
  assert.ok(
    summaryIndex < tableIndex && tableIndex < sourcesIndex && sourcesIndex < advancedIndex,
    "sections must render in priority order: summary, table, sources, advanced"
  );

  assert.ok(!source.includes("InlinePanelSkeleton"), "the old skeleton rows must be gone from the pending path");
  assert.ok(
    source.includes("Pull rates are taking longer than expected to load."),
    "the timeout escape must remain so the loader can never run indefinitely"
  );
  assert.ok(
    source.includes("Pull-rate data coming soon for this set."),
    "the settled-empty compact state must remain after the request resolves empty"
  );
});

test("Phase 11: the page client no longer inlines Pull Rates JSX and delegates to PullRatesTab with the untouched fetch state", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const renderStart = source.indexOf('setDetailTab === "pull-rates" ? (');
  assert.ok(renderStart >= 0, "the pull-rates render branch must exist");
  const renderEnd = source.indexOf(") : null}", renderStart);
  const renderSource = source.slice(renderStart, renderEnd);

  assert.ok(renderSource.includes("<PullRatesTab"), "must delegate to the new PullRatesTab container");
  assert.ok(renderSource.includes("pullRateAssumptions={pullRateAssumptions}"), "must pass through the existing pullRateAssumptions derivation");
  assert.ok(renderSource.includes("pullRatesTabPending={pullRatesTabPending}"), "must pass through the existing pending flag");
  assert.ok(renderSource.includes("pullRatesPendingTimedOut={pullRatesPendingTimedOut}"), "must pass through the existing timeout flag");
  assert.ok(renderSource.includes("activePullRatesState={activePullRatesState}"), "must pass through the existing set-id-guarded state");

  // The fetch effect itself — request-key dedupe, staleness guard, state
  // shape — must be untouched; this refactor only moved the render.
  assert.ok(source.includes("const [pullRatesState, setPullRatesState] = useState(() => ({"), "pullRatesState fetch state must remain in the page client, unmoved");
  assert.ok(source.includes("lastPullRatesRequestKeyRef"), "the request-key dedupe guard must remain in the page client");
});

test("Phase 11: PullRateAssumptionsCard exports PullRateTable/PullRateMobileRows/buildGroupsForRender for section-level reuse", () => {
  const source = fs.readFileSync(pullRateAssumptionsCardPath, "utf8").replace(/\r\n/g, "\n");
  assert.ok(source.includes("export function PullRateTable"), "PullRateTable must be exported for reuse by PullRateTableSection/AdvancedOddsSection");
  assert.ok(source.includes("export function PullRateMobileRows"), "PullRateMobileRows must be exported for reuse");
  assert.ok(source.includes("export { buildGroupsForRender }"), "buildGroupsForRender must be re-exported for reuse");
});

test("Phase 11: Insights' critical tier holds its own branded panel (not a whole-tab gate); Opening Outcomes/Desirability Evidence gate independently on the secondary tier", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes('const hasActiveInsightsPayload =\n    setDetailMode && setDetailTab === "insights"\n      ? hasInsightsPayloadData(explorePayload)\n      : Boolean(explorePayload);'),
    "active insights readiness must use hasInsightsPayloadData on the Insights tab only"
  );
  const loadingGateStart = source.indexOf("const activeInsightsCriticalStatus =");
  const loadingGateEnd = source.indexOf("const openingOutcomesViewHasData =", loadingGateStart);
  assert.ok(loadingGateStart >= 0 && loadingGateEnd > loadingGateStart, "the split insights loading gate block must exist");
  const loadingGateSource = source.slice(loadingGateStart, loadingGateEnd);
  assert.ok(loadingGateSource.includes("!hasActiveInsightsPayload"), "the secondary-tier pending/error gates must use insights-data readiness");
  assert.ok(!loadingGateSource.includes("!explorePayload"), "pending/error gates must not use raw explorePayload truthiness");
  assert.ok(loadingGateSource.includes("activeInsightsCriticalStatus === \"error\""), "the critical tier must have its own independent error gate");
  assert.ok(loadingGateSource.includes("activeInsightsSecondaryStatus === \"error\""), "the secondary tier must have its own independent error gate");

  assert.ok(
    source.includes("const showInsightsCohesiveLoading = insightsCriticalPending && !insightsCriticalPendingTimedOut;"),
    "the critical-tier panel must engage only while that fetch is genuinely pending (not after its own timeout)"
  );

  const branchStart = source.indexOf("{showInsightsCohesiveLoading ? (");
  assert.ok(branchStart >= 0, "the insights critical-tier loading branch must exist in the render");
  const branchSource = source.slice(branchStart, branchStart + 900);
  assert.ok(branchSource.includes("<SetTabLoadingPanel"), "Insights critical tier must use the shared branded panel");
  assert.ok(branchSource.includes("Loading RIP score…"), "Insights critical-tier loading title must exist");
  assert.ok(
    branchSource.includes("Pulling your set's RIP score and pillar breakdown."),
    "Insights critical-tier loading helper copy must exist"
  );

  assert.ok(
    source.includes('{(!setDetailMode || setDetailTab === "insights") && !showInsightsCohesiveLoading ? ('),
    "the insights region must stay hidden while the critical-tier panel shows, and /Explore (non set-detail) must be unaffected"
  );
  assert.ok(
    source.includes("Set insights are taking longer than expected to load."),
    "the secondary-tier timeout/error fallback copy must remain for the settled-failure path"
  );

  const insightsSectionStart = source.indexOf('{(!setDetailMode || setDetailTab === "insights") && !showInsightsCohesiveLoading ? (');
  const openingOutcomesStart = source.indexOf('title="Simulation Results"', insightsSectionStart);
  const openingOutcomesEnd = source.indexOf("</SectionCard>", openingOutcomesStart);
  assert.ok(openingOutcomesStart > insightsSectionStart, "Simulation Results (formerly Opening Outcomes) must still render under the Insights section");
  assert.ok(openingOutcomesEnd > openingOutcomesStart, "Simulation Results card body must be present");
  const openingOutcomesSource = source.slice(openingOutcomesStart, openingOutcomesEnd);
  assert.ok(
    openingOutcomesSource.includes("insightsSectionsBlocked ? ("),
    "Simulation Results must remain gated by insightsSectionsBlocked, now driven by the secondary-tier fetch independent of the critical tier"
  );

  // Both the hero (RipScoreBreakdownModule) and the secondary-tier sections
  // (DesirabilityEvidenceCard, Opening Outcomes) are wrapped in their own
  // SectionErrorBoundary for render-exception isolation.
  const insightsRegionEnd = source.indexOf("{effectiveViewMode === \"expert\" && !setDetailMode ? (", insightsSectionStart);
  const insightsRegionSource = source.slice(insightsSectionStart, insightsRegionEnd);
  const insightsErrorBoundaryCount = (insightsRegionSource.match(/<SectionErrorBoundary/g) || []).length;
  assert.equal(insightsErrorBoundaryCount, 3, `Insights must wrap RIP Score, Desirability Evidence, and Opening Outcomes each in their own SectionErrorBoundary (found ${insightsErrorBoundaryCount})`);
});

test("Phase 9D.2: Cards shows the branded panel only while the card page payload loads with no rows, and keeps per-card image placeholders", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const branchStart = source.indexOf(
    '{(effectiveCardsPageStatus === "idle" || effectiveCardsPageStatus === "loading") &&'
  );
  assert.ok(branchStart >= 0, "the cards initial-loading branch must cover idle and loading for the active set");
  const branchSource = source.slice(branchStart, branchStart + 1200);
  assert.ok(
    branchSource.includes("effectiveCardsPageCards.length === 0 ? ("),
    "the branded panel must only engage when no effective card rows exist yet"
  );
  assert.ok(branchSource.includes("<SetTabLoadingPanel"), "Cards must use the shared branded panel for the initial load");
  assert.ok(branchSource.includes("Loading cards…"), "Cards loading title must exist");
  assert.ok(
    branchSource.includes("Pulling the checklist page and card market fields for this set."),
    "Cards loading helper copy must exist"
  );
  assert.ok(!source.includes("CardGridSkeleton"), "the old card grid skeleton must be gone");

  // Lazy per-card image loading keeps card-shaped placeholders — it must not
  // regress to blank tiles, and it must not route through the tab-level panel.
  const tileStart = source.indexOf("function ChecklistCardTile(");
  assert.ok(tileStart >= 0, "ChecklistCardTile must exist");
  const tileSource = source.slice(tileStart, source.indexOf("\nfunction ", tileStart + 10));
  assert.ok(tileSource.includes("<CardImagePlaceholder"), "per-card image placeholders must remain for lazy image loads");
  assert.ok(!tileSource.includes("SetTabLoadingPanel"), "individual card image loading must not use the tab-level panel");
});

test("Phase 9D.2: route-level loading screens keep the fullscreen branded loader unchanged", () => {
  for (const routeLoadingPath of [exploreRouteLoadingPath, setSlugRouteLoadingPath]) {
    const routeSource = fs.readFileSync(routeLoadingPath, "utf8").replace(/\r\n/g, "\n");
    assert.ok(
      routeSource.includes('import InDexLogoLoader from "@/components/brand/InDexLogoLoader";'),
      `${path.basename(path.dirname(routeLoadingPath))}/loading.js must keep the branded loader`
    );
    assert.ok(routeSource.includes("fullScreen"), "route-level loading must remain fullscreen");
    assert.ok(!routeSource.includes("SetTabLoadingPanel"), "route-level loading must not switch to the in-tab panel");
  }
});

// ---------------------------------------------------------------------------
// Phase 10: Cards tab infinite scroll + section/sidebar/URL synchronization.
// Explicit Previous/Next paging is gone: a sentinel below the grid advances
// the page via IntersectionObserver (generous prefetch margin), responses for
// pages > 1 append (deduped) into the accumulated list for the same scope
// (set + sort + search + movement filter), and the already-rendered cards
// stay on screen while the next chunk loads (bottom inDex loader only, no
// grid blanking/dimming). The Cards tab's active section ("all-cards" |
// "market-movers") is derived from the URL `section` param so the sidebar
// highlight, section tab strip, and URL can never diverge.
// ---------------------------------------------------------------------------

test("Phase 10: cards pagination buttons are gone; an IntersectionObserver sentinel drives load-more with a generous prefetch margin", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(!source.includes("hasPreviousPage"), "the Previous button (and any hasPreviousPage read) must be gone");
  assert.ok(!/>\s*Previous\s*</.test(source), "no user-facing Previous button");
  assert.ok(!/setCardsPage\(\(page\) => page \+ 1\)/.test(source), "the Next button's manual page increment must be gone");

  // The scaffold mounts the page tree twice (desktop `hidden xl:block` +
  // mobile `xl:hidden`), so a single element ref would land on the hidden
  // mobile copy and never intersect on desktop — the sentinel must be located
  // by data attribute and every mounted instance observed.
  assert.ok(source.includes('<div data-cards-load-more-sentinel="true"'), "the sentinel element must render below the grid");
  assert.ok(
    source.includes('document.querySelectorAll("[data-cards-load-more-sentinel]")'),
    "the observer must find every mounted sentinel (desktop + mobile copies), not a single ref"
  );
  assert.ok(source.includes("for (const sentinel of sentinels)"), "every sentinel instance must be observed");
  assert.ok(!source.includes("cardsLoadMoreSentinelRef"), "the single-element sentinel ref must be gone");
  assert.ok(source.includes("new IntersectionObserver("), "load-more must be driven by IntersectionObserver");
  const rootMarginMatch = source.match(/rootMargin: "(\d+)px 0px"/);
  assert.ok(rootMarginMatch, "the observer must set a vertical rootMargin");
  const rootMargin = Number(rootMarginMatch[1]);
  assert.ok(rootMargin >= 800 && rootMargin <= 1200, `rootMargin must be a generous 800-1200px prefetch margin (got ${rootMargin})`);
  assert.ok(
    source.includes("typeof IntersectionObserver === \"undefined\""),
    "environments without IntersectionObserver must not crash"
  );
});

test("Phase 10: pages append into the accumulated list for the same scope, deduped by stable card identity", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(source.includes("function getChecklistCardKey(card)"), "a stable card identity helper must exist");
  assert.ok(
    source.includes("String(card?.id || card?.cardNumber || card?.card_number || card?.name || \"\")"),
    "identity must prefer id, then card number, then name — matching the grid's React keys"
  );
  assert.ok(source.includes("function dedupeChecklistCards(cards)"), "an append-dedupe helper must exist");

  const effectStart = source.indexOf("Cards tab: slim, paginated fetch (getPokemonSetCardsPage)");
  const effectEnd = source.indexOf("\n\n  // Pull Rates tab fetch effect", effectStart);
  const effectSource = source.slice(effectStart, effectEnd);
  assert.ok(effectStart >= 0 && effectEnd > effectStart, "cards page fetch effect must exist");

  assert.ok(effectSource.includes("const shouldAppend ="), "the success handler must decide append vs replace");
  assert.ok(
    effectSource.includes("previous.scopeKey === cardsPageScopeKey") && effectSource.includes("requestedPage > 1"),
    "append is allowed only for page > 1 responses whose scope matches the cards already in state"
  );
  assert.ok(
    effectSource.includes("dedupeChecklistCards([...previous.cards, ...payload.cards])"),
    "appended chunks must merge below the existing cards, deduped"
  );
  assert.ok(
    effectSource.includes('return { ...previous, status: "loading_more", error: null };'),
    "loading a further chunk must keep every rendered card in place (loading_more), never blank or swap the list"
  );
});

test("Phase 10: duplicate and stale load-more fetches are prevented", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // The observer callback is gated by a latest-value ref and an idempotent
  // page advance, and the fetch effect dedupes by request key.
  assert.ok(source.includes("const cardsLoadMoreGateRef = useRef("), "a latest-value gate ref must exist for the observer callback");
  assert.ok(source.includes("setCardsPage((page) => (page >= nextPage ? page : nextPage));"), "the page advance must be idempotent under duplicate observer fires");
  assert.ok(source.includes("!cardsPageIsFetching"), "load-more must be blocked while a cards request is already in flight");
  assert.ok(source.includes("cardsPage === activeCardsPageState.page"), "load-more must be blocked while a requested page has not merged yet");

  // A response landing after the user changed set/scope must not append into
  // the new view: effect cleanup cancels, cross-set responses are dropped by
  // the shared guard, and appends additionally require a scope match.
  const effectStart = source.indexOf("Cards tab: slim, paginated fetch (getPokemonSetCardsPage)");
  const effectEnd = source.indexOf("\n\n  // Pull Rates tab fetch effect", effectStart);
  const effectSource = source.slice(effectStart, effectEnd);
  assert.ok(effectSource.includes("let isCancelled = false;"), "in-flight responses must be cancellable");
  assert.ok(effectSource.includes("if (isCancelled) {"), "cancelled responses must be dropped");
  assert.ok(effectSource.includes('debugSetPagePerf("cards_page.tab_fetch_stale"'), "cross-set stale responses must be dropped");
  assert.ok(
    effectSource.includes("cardsLoadMoreGateRef.current.stateScopeKey !== cardsPageScopeKey"),
    "a page-N request of a brand-new scope must be skipped (the reset effect rewinds to page 1 in the same commit)"
  );
});

test("Phase 10: changing set/sort/search/movement filter rewinds to the first chunk", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const resetStart = source.indexOf("setCardsPage(1);");
  assert.ok(resetStart >= 0, "a scope-reset effect must rewind the page counter");
  const resetSource = source.slice(source.lastIndexOf("useEffect(() => {", resetStart), source.indexOf("]);", resetStart) + 3);
  for (const dep of ["cardSortMode", "cardMovementFilter", "cardSearchQuery", "resolvedSetResourceId"]) {
    assert.ok(resetSource.includes(dep), `the scope-reset effect must depend on ${dep}`);
  }
});

test("Phase 10: load-more failures keep the loaded cards, disable the sentinel, and offer an explicit Retry", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(source.includes("const cardsPageLoadMoreError = Boolean("), "a failed load-more must be distinguishable from a failed first load");
  assert.ok(source.includes("!activeCardsPageState.error"), "the sentinel gate must be disabled while an error is pending (no retry hammering)");
  assert.ok(source.includes("Couldn&apos;t load more cards."), "a failed load-more must surface explicit copy");
  assert.ok(source.includes("setCardsPageRetryNonce((nonce) => nonce + 1)"), "Retry must re-run the fetch effect via the retry nonce");
  assert.ok(source.includes("cardsPageRetryNonce,"), "the fetch effect must depend on the retry nonce");
});

test("Phase 10: bottom load-more state uses the branded inDex loader, and completion shows a subtle all-loaded note", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes('import InDexLogoLoader from "@/components/brand/InDexLogoLoader";'),
    "the page client must use the branded loader for load-more"
  );
  const loadingMoreStart = source.indexOf("{cardsPageIsLoadingMore ? (");
  assert.ok(loadingMoreStart >= 0, "a bottom loading-more state must render");
  const loadingMoreSource = source.slice(loadingMoreStart, loadingMoreStart + 700);
  assert.ok(loadingMoreSource.includes("<InDexLogoLoader"), "loading more must show the inDex logo/dots loader, not a generic spinner");
  assert.ok(loadingMoreSource.includes("index-loader-shell--compact"), "the bottom loader must use the compact footer scale");
  assert.ok(!source.includes("animate-spin"), "no generic circular spinner anywhere in the page client");

  assert.ok(source.includes("const cardsPageFullyLoaded = Boolean("), "completion must be derived from pagination");
  assert.ok(source.includes("cards loaded"), "completion must show a subtle all-loaded note");
});

test("Phase 10: the Cards section (all-cards | market-movers) is derived from the URL and drives the sidebar highlight and section tabs", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(source.includes("const [cardsSection, setCardsSection] = useState("), "a cards-section state must exist");
  assert.ok(
    source.includes('setCardsSection(nextSection === "market-movers" ? "market-movers" : "all-cards");'),
    "the URL-consumption effect must re-derive the cards section from the section param (URL is the source of truth)"
  );
  assert.ok(
    source.includes('"all-cards": { tab: "cards", targetId: "set-detail-cards", cardsSubTab: "checklist" }'),
    "all-cards must be a routable section target"
  );

  // Sidebar rail: both sections listed, highlight driven by the section.
  assert.ok(source.includes("activeCardsSection = \"all-cards\""), "the rail must accept the active cards section");
  assert.ok(source.includes("activeCardsSection={cardsSection}"), "the rail must be driven by the page's cards section");
  assert.ok(
    source.includes('active: activeCardsSubTab === "checklist" && activeCardsSection !== "market-movers"'),
    "All Cards must not be highlighted while the market-movers section is active"
  );
  assert.ok(
    source.includes('active: activeCardsSubTab === "checklist" && activeCardsSection === "market-movers"'),
    "Market Movers must be highlighted when its section is active"
  );

  // Section tab strip inside the Cards tab mirrors the same state.
  assert.ok(source.includes('{ value: "all-cards", label: "All Cards" }'), "the section tab strip must include All Cards");
  assert.ok(source.includes('{ value: "market-movers", label: "Market Movers" }'), "the section tab strip must include Market Movers");
  assert.ok(source.includes("value={cardsSection}"), "the section tab strip must render the active cards section");
});

test("Phase 10: entering a cards section applies its preset and routes through the URL, so movers and all-cards share the infinite grid", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const navStart = source.indexOf("const handleSetDetailNavSelect = (");
  const navEnd = source.indexOf("const handleViewSetValueTrend", navStart);
  const navSource = source.slice(navStart, navEnd);
  assert.ok(navStart >= 0 && navEnd > navStart, "handleSetDetailNavSelect must exist");
  assert.ok(
    navSource.includes('setCardsSection("market-movers");') && navSource.includes('setCardSortMode("30d-gainers");'),
    "entering Market Movers must preset the movers sort"
  );
  assert.ok(
    navSource.includes('setCardsSection("all-cards");') && navSource.includes('setCardSortMode("set-number");'),
    "entering All Cards must restore the default checklist view"
  );

  const viewAllStart = source.indexOf("const handleViewAllMarketMovers = () => {");
  const viewAllSource = source.slice(viewAllStart, source.indexOf("};", viewAllStart));
  assert.ok(viewAllSource.includes('setCardsSection("market-movers");'), "View-all-movers must activate the market-movers section");
  assert.ok(viewAllSource.includes('pushSetDetailRouteState({ tab: "cards", section: "market-movers" });'), "View-all-movers must reflect the section in the URL");

  // Both sections render the same checklist grid, so the movers view gets the
  // same append/sentinel mechanics and the fetch always carries the active
  // sort + movement filter (single call site, asserted elsewhere).
  const cardsPageCallCount = (source.match(/getPokemonSetCardsPage\(/g) || []).length;
  assert.equal(cardsPageCallCount, 1, "one shared paginated fetch serves both cards sections");
  assert.ok(source.includes("movementFilter: effectiveCardMovementFilter,"), "the shared fetch must carry the movement filter");
  assert.ok(source.includes("movementSort: movementSortValue,"), "the shared fetch must carry the movement sort");
});

// Progressive-rendering refactor: Cards priority 5 ("secondary metadata/
// deltas/badges after initial grid is usable") — the price/delta badge is
// deferred via startTransition per tile so the name/image commit first, with
// its width reserved from the tile's first render so no layout shift occurs
// when it pops in. Priority 3 (stable image placeholders) was already
// implemented before this refactor (aspect-[3/4] box, absolutely-positioned
// placeholder) and is asserted here too so a future edit can't regress it.
test("Phase 11: ChecklistCardTile defers price/delta badges via startTransition with a reserved-width skeleton", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes('import { startTransition, useCallback, useEffect, useId, useMemo, useReducer, useRef, useState, useTransition } from "react";'),
    "the page client must import the standalone startTransition function"
  );

  const tileStart = source.indexOf("function ChecklistCardTile({ card }) {");
  assert.ok(tileStart >= 0, "ChecklistCardTile must exist");
  const tileEnd = source.indexOf("\nfunction getChecklistCardMarketPrice", tileStart);
  const tileSource = source.slice(tileStart, tileEnd);

  assert.ok(tileSource.includes("const [isMetaRevealed, setIsMetaRevealed] = useState(false);"), "must track a deferred-reveal flag");
  assert.ok(
    tileSource.includes("startTransition(() => {\n      setIsMetaRevealed(true);\n    });"),
    "the reveal must be scheduled via startTransition, not a synchronous state update"
  );
  assert.ok(
    tileSource.includes('className="min-w-[4.5rem] shrink-0 text-right"'),
    "the badge slot must reserve its width before content is revealed, so reveal never shifts the name/number column"
  );
  assert.ok(
    tileSource.includes("animate-pulse rounded bg-[rgba(148,163,184,0.12)]"),
    "an unrevealed badge slot must show a quiet skeleton, not blank space"
  );

  // Priority 3, pre-existing: the image box is a fixed aspect-ratio
  // container with an absolutely-positioned placeholder, so swapping in the
  // loaded <img> never resizes the tile.
  assert.ok(tileSource.includes('className="relative aspect-[3/4] w-full'), "the image box must keep a fixed aspect-ratio container");
  assert.ok(tileSource.includes("<CardImagePlaceholder shimmer />"), "a shimmering placeholder must render while the image loads");
});

test("Phase 11: Cards reports cardsFirstBatchMs/cardsNextBatchMs section timing per page load", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes('import { markSectionTiming, debugSectionTiming } from "@/lib/perf/sectionTiming";'),
    "the page client must import the shared timing primitives"
  );

  const fetchStart = source.indexOf("getPokemonSetCardsPage(setId, {");
  assert.ok(fetchStart >= 0, "the cards page fetch call must exist");
  const fetchEnd = source.indexOf("\n      .catch((error) => {", fetchStart);
  const fetchSource = source.slice(fetchStart, fetchEnd);

  assert.ok(fetchSource.includes("const cardsBatchMetricName = requestedPage > 1 ? \"cardsNextBatch\" : \"cardsFirstBatch\";"), "must distinguish first batch from subsequent batches by requestedPage");
  assert.ok(fetchSource.includes("markSectionTiming(`${cardsBatchMetricName}_success`"), "must mark timing for each settled batch");
  assert.ok(fetchSource.includes('debugSectionTiming("[section-timing]", `${cardsBatchMetricName}Ms`'), "must log the cardsFirstBatchMs/cardsNextBatchMs metric per batch");
});

// ---------------------------------------------------------------------------
// Stabilization pass (post progressive-rendering + Overview seed): renderable
// data beats loading status. DB-backed sets (e.g. Paradox Rift,
// 5d3d5c23-7098-4393-ad63-6ad9372aee30: 60 performance points, 10 top_hits
// rows) were showing "history unavailable" / "taking longer than expected" /
// "no top_hits rows" purely from frontend state/merge/gating bugs. These
// tests pin the fixes.
// ---------------------------------------------------------------------------

test("Stabilization: Performance vs Cost never shows loading/empty when a performance series has points", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes("const hasPerformanceVsCostHistory ="),
    "a dedicated hasPerformanceVsCostHistory boolean must exist"
  );
  const hasHistoryStart = source.indexOf("const hasPerformanceVsCostHistory =");
  const hasHistoryEnd = source.indexOf(";", hasHistoryStart);
  const hasHistorySource = source.slice(hasHistoryStart, hasHistoryEnd);
  assert.ok(
    hasHistorySource.includes("Array.isArray(overviewPerformanceVsCostHistory)") &&
      hasHistorySource.includes("overviewPerformanceVsCostHistory.length > 0"),
    "hasPerformanceVsCostHistory must check the overview payload's series for points"
  );

  // Paradox Rift regression: explorePayload.history_trend is always written
  // by the insights secondary merge — an EMPTY array is truthy and used to
  // shadow the populated /overview series via ||.
  assert.ok(
    !source.includes("const historyTrend = explorePayload?.history_trend ||"),
    "an empty explorePayload.history_trend must never shadow the /overview series via ||"
  );
  assert.ok(
    source.includes("const historyTrend = hasNonEmptyArray(explorePayload?.history_trend)\n    ? explorePayload.history_trend\n    : overviewPerformanceVsCostHistory;"),
    "historyTrend must only prefer a NON-EMPTY explorePayload series over the overview series"
  );

  // Paradox-style state: seeded overview has performanceVsCostHistory points
  // while activeOverviewState is loading/idle — the SectionBoundary status
  // must resolve to success/success_stale (renders the chart), never
  // loading/idle/empty and never the error panel over renderable points.
  const statusStart = source.indexOf("const overviewPerformanceVsCostStatus =");
  const statusEnd = source.indexOf(";", statusStart);
  const statusSource = source.slice(statusStart, statusEnd);
  assert.ok(statusStart >= 0, "overviewPerformanceVsCostStatus must exist");
  assert.ok(
    statusSource.includes("hasPerformanceVsCostHistory"),
    "the status must key on hasPerformanceVsCostHistory"
  );
  assert.ok(
    statusSource.includes('? "success"') && statusSource.includes('"success_stale"'),
    "with points in hand the status must map to success/success_stale, never a loader"
  );
  assert.ok(
    statusSource.includes("activeOverviewState.status") &&
      !statusSource.includes('=== "loading"') &&
      !statusSource.includes('=== "idle"'),
    "the with-data branch must not depend on loading/idle checks — data presence alone decides"
  );
  assert.ok(
    source.includes("status={overviewPerformanceVsCostStatus}"),
    "the Performance vs Cost SectionBoundary must consume the derived status"
  );
});

test("Stabilization: insights secondary adapter maps simulationDrivers -> top_hits (and the other secondary-owned fields)", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");
  const adapterStart = source.indexOf("function adaptPokemonSetInsightsSecondaryPayloadToExplorePayload(secondary)");
  const adapterEnd = source.indexOf("\n}\n", adapterStart);
  const adapterSource = source.slice(adapterStart, adapterEnd);

  assert.ok(adapterStart >= 0, "the secondary adapter must exist");
  assert.ok(
    adapterSource.includes("top_hits: dualKeyCase(secondary?.simulationDrivers || [])"),
    "simulationDrivers from /insights/secondary must merge into explorePayload.top_hits"
  );
  for (const mapping of [
    "percentiles: dualKeyCase(outcomeDistribution.percentiles || [])",
    "distribution_bins: dualKeyCase(outcomeDistribution.distributionBins || [])",
    "rankings: dualKeyCase(secondary?.rarityContribution || [])",
    "history_trend: dualKeyCase(secondary?.historyTrend || [])",
  ]) {
    assert.ok(adapterSource.includes(mapping), `secondary adapter must keep mapping: ${mapping}`);
  }
});

test("Stabilization: navigation resets rebuild explorePayload from already-successful insights fetches instead of clobbering them", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // The reset effect's identity check can't vouch for a payload assembled
  // purely from the secondary fetch (it carries no `set` field) — the reset
  // must rebuild from the fetch states (guarded to the active set) rather
  // than return null and strand Insights on skeletons until timeout.
  const resetStart = source.indexOf("setExplorePayload((previous) => {");
  const resetEnd = source.indexOf('setSetPageSnapshotRefreshState({ status: "idle", setId: null, error: null });', resetStart);
  assert.ok(resetStart >= 0 && resetEnd > resetStart, "the navigation reset effect must exist");
  const resetSource = source.slice(resetStart, resetEnd);

  assert.ok(
    resetSource.includes('insightsCriticalFetchState.status === "success"') &&
      resetSource.includes("adaptPokemonSetInsightsCriticalPayloadToExplorePayload(insightsCriticalFetchState.data)"),
    "the reset must re-merge a successful critical fetch"
  );
  assert.ok(
    resetSource.includes('insightsSecondaryFetchState.status === "success"') &&
      resetSource.includes("adaptPokemonSetInsightsSecondaryPayloadToExplorePayload(insightsSecondaryFetchState.data)"),
    "the reset must re-merge a successful secondary fetch"
  );
  assert.ok(
    resetSource.includes("isSetStateForActiveSet(insightsCriticalFetchState.setId") &&
      resetSource.includes("isSetStateForActiveSet(insightsSecondaryFetchState.setId"),
    "re-merged slices must be guarded by the REQUEST set id (not payload.set completeness)"
  );
  assert.ok(
    resetSource.includes("return { ...(criticalSlice || {}), ...(secondarySlice || {}) };"),
    "when either slice exists the reset must return the rebuilt payload instead of null"
  );
});

test("Stabilization: insights pending timeout clears as soon as secondary renderable data exists", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const readinessStart = source.indexOf("const insightsSecondaryHasRenderableData =");
  assert.ok(readinessStart >= 0, "insightsSecondaryHasRenderableData must be declared");
  const readinessEnd = source.indexOf(";", readinessStart);
  const readinessSource = source.slice(readinessStart, readinessEnd);
  for (const field of [
    "top_hits",
    "distribution_bins",
    "percentiles",
    "rankings",
    "history_trend",
    "rip_statistics",
    "openingDesirability",
    "hasDesirabilityProofSignal",
  ]) {
    assert.ok(readinessSource.includes(field), `secondary readiness must inspect ${field}`);
  }

  // The clearing effect: once renderable data lands, a previously-fired
  // "taking longer than expected" timeout no longer describes reality.
  const clearEffectStart = source.indexOf("if (!insightsSecondaryHasRenderableData) {\n      return;\n    }");
  assert.ok(clearEffectStart >= 0, "a timeout-clearing effect keyed on secondary readiness must exist");
  const clearEffectSource = source.slice(clearEffectStart, clearEffectStart + 700);
  assert.ok(
    clearEffectSource.includes("setInsightsPendingTimeoutState"),
    "the clearing effect must reset insightsPendingTimeoutState"
  );

  // And the render-time flag is synchronously gated too, so the fallback copy
  // can't flash for the one commit before the effect runs.
  assert.ok(
    source.includes("const insightsPendingTimedOut =\n    !insightsSecondaryHasRenderableData &&"),
    "insightsPendingTimedOut must be impossible while renderable secondary data exists"
  );
});

test("Stabilization: Simulation Results renders data first, quiet placeholder while its fetch is in flight, empty copy only when settled", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const openingOutcomesStart = source.indexOf('title="Simulation Results"');
  const openingOutcomesEnd = source.indexOf("</SectionCard>", openingOutcomesStart);
  const openingOutcomesSource = source.slice(openingOutcomesStart, openingOutcomesEnd);

  const blockedIndex = openingOutcomesSource.indexOf("insightsSectionsBlocked ? (");
  const viewHasDataIndex = openingOutcomesSource.indexOf("!openingOutcomesViewHasData ? (");
  const loadingGuardIndex = openingOutcomesSource.indexOf('activeInsightsSecondaryStatus === "loading" ? (');
  const emptyCopyIndex = openingOutcomesSource.indexOf("{openingOutcomesEmptyViewCopy}");

  assert.ok(blockedIndex >= 0, "the blocked (no data at all) gate must exist");
  assert.ok(viewHasDataIndex > blockedIndex, "per-subtab data check must come after the blocked gate");
  assert.ok(
    loadingGuardIndex > viewHasDataIndex && loadingGuardIndex < emptyCopyIndex,
    "a sub-view with no rows must show a quiet placeholder while the secondary fetch is loading, before any empty verdict"
  );
  assert.ok(emptyCopyIndex >= 0, "the settled per-subtab empty copy must remain");
});

test("Simulation Results section targets: Opening Profit vs Cost routes to Insights while Overview's performance-vs-cost stays put", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // Backward-compatible deep links to the card + its default sub-view.
  assert.ok(source.includes('"opening-outcomes": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "outcome-distribution" }'));
  assert.ok(source.includes('"simulation-results": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "outcome-distribution" }'));

  // The technical Opening P vs C sub-view is its own section id (historical-trend)
  // so it does not collide with Overview's quick-read performance-vs-cost.
  assert.ok(source.includes('"opening-performance-cost": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "historical-trend" }'));
  assert.ok(source.includes('"simulation-metrics": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "simulation-metrics" }'));

  // Overview keeps its own Performance vs Cost chart, unchanged.
  assert.ok(source.includes('"performance-vs-cost": { tab: "overview", targetId: "set-detail-overview-performance", graphMode: "historical-trend" }'));

  // Metrics is a real graph section so scroll/highlight/URL-sync treat it like
  // the other sub-views.
  assert.ok(source.includes('const GRAPH_SECTION_KEYS = new Set(["outcome-distribution", "historical-trend", "simulation-drivers", "pack-breakdown", "value-contribution", "simulation-metrics"])'));
  assert.ok(source.includes('"simulation-metrics": "explore-outcomes"'));
});

test("Simulation Results compact Pack Paths and Value Structure use matrix/ribbon branches without hidden-row summaries", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const cardStart = source.indexOf('title="Simulation Results"');
  const cardEnd = source.indexOf("</SectionCard>", cardStart);
  assert.ok(cardStart >= 0 && cardEnd > cardStart, "Simulation Results card must be present");
  const cardSource = source.slice(cardStart, cardEnd);

  assert.ok(cardSource.includes('<SimulationResultsPanel id="set-detail-value-structure">'));
  assert.ok(cardSource.includes("<RarityContributionContent rankings={rankings} condensed />"));
  assert.ok(cardSource.includes('<SimulationResultsPanel id="set-detail-pack-breakdown">'));
  assert.ok(cardSource.includes("<PackBreakdownContent"));
  assert.ok(cardSource.includes("condensed"));

  assert.ok(source.includes("function PackPathsVisualization("), "Pack Paths compact branch must exist");
  assert.ok(source.includes("<PieChart>"), "Pack Paths must use a restrained donut branch for top-level paths");
  assert.ok(source.includes("function NormalStateMatrix("), "normal states must feed the all-states matrix branch");
  assert.ok(source.includes("buildNormalStateMatrixRows(normalStateRows)"), "normal states must be normalized before matrix rendering");
  assert.ok(source.includes("function RarityValueComposition("), "Value Structure composition branch must exist");
  assert.ok(source.includes("function ValueCompositionRibbon("), "Value Structure must use a composition ribbon");
  assert.ok(source.includes("function RarityDetailTile("), "Value Structure must show all rarity groups in a compact grid");
  assert.ok(!source.includes("<Treemap"), "Simulation Results compact views must not use the colorful treemap branch");
  assert.ok(!source.includes("+{hiddenRarityCount} more rarity groups"), "Value Structure must not hide extra rarity groups");
  assert.ok(!source.includes("+{hiddenCount} more states"), "Pack Paths must not hide extra normal states");

  assert.ok(cardSource.includes('label: "Value Structure"'));
  assert.ok(cardSource.includes('label: "Pack Paths"'));
  assert.ok(source.includes('"pack-breakdown": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "pack-breakdown" }'));
  assert.ok(source.includes('value: { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "value-contribution" }'));
});

test("Stabilization: Simulation Drivers warning appears only after the secondary fetch SUCCEEDED with truly empty top_hits", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  // The diagnostics warning must be out of rawWarnings (computed before the
  // fetch status exists) ...
  const rawWarningsStart = source.indexOf("const rawWarnings = [");
  const rawWarningsEnd = source.indexOf("];", rawWarningsStart);
  const rawWarningsSource = source.slice(rawWarningsStart, rawWarningsEnd);
  assert.ok(rawWarningsStart >= 0, "rawWarnings must exist");
  assert.ok(
    !rawWarningsSource.includes("simulationDrivers.diagnostics"),
    "the drivers diagnostics warning must not be an unconditional rawWarnings member"
  );

  // ... and re-added only as settled evidence.
  const visibleStart = source.indexOf("const simulationDriversWarningVisible =");
  const visibleEnd = source.indexOf(";", visibleStart);
  const visibleSource = source.slice(visibleStart, visibleEnd);
  assert.ok(visibleStart >= 0, "simulationDriversWarningVisible must exist");
  assert.ok(visibleSource.includes("topHits.length === 0"), "the warning requires truly empty top_hits");
  assert.ok(
    visibleSource.includes('activeInsightsSecondaryStatus === "success"'),
    "on set-detail pages the warning requires the secondary fetch to have succeeded"
  );
  assert.ok(
    !visibleSource.includes('activeInsightsSecondaryStatus === "error"'),
    "a failed fetch is not evidence of missing DB rows — the error path has its own copy"
  );

  assert.ok(source.includes("const visibleSetPageWarnings ="), "a gated warnings list must exist");
  assert.ok(
    source.includes("{visibleSetPageWarnings.length > 0 ? (") &&
      source.includes("{visibleSetPageWarnings.map((warning, index) => ("),
    "the warnings strip must render the gated list"
  );
});

test("Stabilization: useSectionFetchState dedupes auto-fetches by set id and releases the claim on error", () => {
  const sectionFetchStatePath = path.resolve(__dirname, "../../hooks/useSectionFetchState.js");
  const source = fs.readFileSync(sectionFetchStatePath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(
    source.includes("const autoFetchedSetIdRef = useRef(null);"),
    "the hook must track the last auto-fetched set id"
  );
  assert.ok(
    source.includes("if (autoFetchedSetIdRef.current === setId) {\n      return;\n    }\n    autoFetchedSetIdRef.current = setId;\n    runFetch(setId);"),
    "the auto-fetch effect must skip identical repeats (tab revisits, StrictMode double effects) and claim before fetching"
  );
  assert.ok(
    source.includes("if (autoFetchedSetIdRef.current === targetSetId) {\n          autoFetchedSetIdRef.current = null;\n        }"),
    "an error must release the claim so a revisit can retry"
  );
  // Manual refetch stays an explicit override.
  const refetchStart = source.indexOf("const refetch = useCallback(() => {");
  const refetchEnd = source.indexOf("}, [setId, runFetch]);", refetchStart);
  const refetchSource = source.slice(refetchStart, refetchEnd);
  assert.ok(refetchSource.includes("runFetch(setId);"), "refetch must still force a fetch");
});

// ---------------------------------------------------------------------------
// Patch 3 — Desirability Evidence N/A handling. Uncomputed proof fields
// (final RIP rank/score, score/rank deltas, top-10 card value) must read
// "Not computed yet" rather than a bare "N/A" that looks broken, and Price
// Relation must reuse the already-computed cardAppealMarketPriceCorrelation
// (pearson/spearman) instead of showing "n/a" — never recompute.
// ---------------------------------------------------------------------------

test("Patch 3: uncomputed proof fields render 'Not computed yet' instead of bare N/A", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(source.includes('const PROOF_NOT_COMPUTED_LABEL = "Not computed yet";'), "a shared 'Not computed yet' label must exist");
  assert.ok(source.includes("function formatProofRankOrNotComputed(value)"), "a rank formatter that yields the not-computed label must exist");
  assert.ok(source.includes("function formatProofDeltaOrNotComputed(value, suffix"), "a delta formatter that yields the not-computed label must exist");

  // Final RIP Rank / Score Delta / Rank Delta must route through the
  // not-computed formatters, not the bare N/A ones.
  assert.ok(
    source.includes('<ProofMetric label="Final RIP Rank" value={formatProofRankOrNotComputed(finalRank)} />'),
    "Final RIP Rank must use the not-computed formatter"
  );
  assert.ok(
    source.includes("<ProofMetric label=\"Score Delta\" value={formatProofDeltaOrNotComputed(validation.desirability_score_delta ?? validation.desirabilityScoreDelta)} />"),
    "Score Delta must use the not-computed formatter"
  );
  assert.ok(
    source.includes('<ProofMetric label="Rank Delta" value={formatProofDeltaOrNotComputed(rankDelta, " ranks")} />'),
    "Rank Delta must use the not-computed formatter"
  );
});

test("Patch 3: Top 10 Cards honors missing_data_flags and null rank with 'Not computed yet'", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const flagStart = source.indexOf("const top10CardValueNotComputed =");
  assert.ok(flagStart >= 0, "a top10CardValueNotComputed flag must exist");
  const flagEnd = source.indexOf(";", flagStart);
  const flagSource = source.slice(flagStart, flagEnd);
  assert.ok(flagSource.includes('missingDataFlags') && flagSource.includes('"top_10_card_value"'), "must consult missing_data_flags");
  assert.ok(
    flagSource.includes("toNumber(validation.top_10_card_value_rank ?? validation.top10CardValueRank) === null"),
    "must also treat a null top-10 rank as not computed"
  );
  assert.ok(
    source.includes("value={top10CardValueNotComputed ? PROOF_NOT_COMPUTED_LABEL : formatProofRank(validation.top_10_card_value_rank ?? validation.top10CardValueRank)}"),
    "the Top 10 Cards tile must render the not-computed label when flagged/null"
  );
});

test("Patch 3: Price Relation reuses cardAppealMarketPriceCorrelation instead of raw N/A", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  const resolverStart = source.indexOf("function resolveCardAppealPriceRelation(validation, cardAppealMarketPriceCorrelation)");
  assert.ok(resolverStart >= 0, "a Price Relation resolver must exist");
  const resolverEnd = source.indexOf("\n}\n", resolverStart);
  const resolverSource = source.slice(resolverStart, resolverEnd);
  assert.ok(
    resolverSource.includes("validation?.card_appeal_vs_market_price_correlation ?? validation?.cardAppealVsMarketPriceCorrelation"),
    "must prefer the persisted desirabilityValidation correlation field first"
  );
  assert.ok(
    resolverSource.includes("toNumber(correlation.pearson) ?? toNumber(correlation.spearman)"),
    "must fall back to the existing cardAppealMarketPriceCorrelation pearson/spearman"
  );

  // The proof card must consume the resolver and pass the correlation down.
  assert.ok(
    source.includes("const priceRelationValue = resolveCardAppealPriceRelation(validation, cardAppealMarketPriceCorrelation);"),
    "the proof card must resolve Price Relation via the shared resolver"
  );
  assert.ok(
    source.includes("value={priceRelationValue === null ? PROOF_NOT_COMPUTED_LABEL : formatCorrelationValue(priceRelationValue)}"),
    "Price Relation must show the resolved correlation, or 'Not computed yet' only when truly absent"
  );
  assert.ok(
    source.includes("cardAppealMarketPriceCorrelation={cardAppealMarketPriceCorrelation}"),
    "DesirabilityEvidenceCard must pass the correlation into DesirabilityProofContent"
  );
});

test("Patch 3: Desirability Impact and Signal Check blocks still render (regression guard)", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8").replace(/\r\n/g, "\n");

  assert.ok(source.includes('<h3 className="text-sm font-semibold text-[var(--text-primary)]">Desirability Impact</h3>'), "Desirability Impact block must remain");
  assert.ok(source.includes('<h3 className="text-sm font-semibold text-[var(--text-primary)]">Desirability Signal Check</h3>'), "Desirability Signal Check block must remain");
  // RIP Core Rank keeps the plain formatter (the investigation found it
  // populated) — only the confirmed-null fields switched to not-computed.
  assert.ok(source.includes('<ProofMetric label="RIP Core Rank" value={formatProofRank(coreRank)} />'), "RIP Core Rank keeps the plain rank formatter");
});
