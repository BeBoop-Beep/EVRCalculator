const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const test = require("node:test");
const assert = require("node:assert/strict");

const ripPageClientPath = path.resolve(__dirname, "RipStatisticsPageClient.jsx");
const marketDashboardStatePath = path.resolve(__dirname, "marketDashboardState.mjs");
const marketClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetMarketClient.js");
const cardsClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetCardsClient.js");
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

test("cards warmup caches normalized payload and does not clear stale cards on failure", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const warmupStart = source.indexOf("prefetchPokemonSetCards(resolvedSetId).then");
  const warmupEnd = source.indexOf("prefetchPokemonSetMarketDashboard", warmupStart);
  const warmupSource = source.slice(warmupStart, warmupEnd);
  const catchStart = source.indexOf(".catch((error) => {", source.indexOf("getPokemonSetCards(setId)"));
  const catchEnd = source.indexOf("});", catchStart);
  const catchSource = source.slice(catchStart, catchEnd);

  assert.ok(warmupSource.includes("checklistCacheRef.current.set(resolvedSetId, payload)"));
  assert.ok(catchSource.includes('previous.status === "success" && previous.setId === setId ? "success" : "error"'));
  assert.ok(catchSource.includes("previous.cards"));
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

  assert.ok(resolverStart >= 0);
  assert.ok(resolverEnd > resolverStart);
  assert.ok(resolverSource.includes("setIdentityMatchesTarget(selectedTarget, requestedResourceId)"));
  assert.ok(selectedReturnIndex >= 0);
  assert.ok(requestedReturnIndex > selectedReturnIndex);
  assert.ok(snapshotReturnIndex > requestedReturnIndex);
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

test("set value history fetches directly on every set detail tab", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const directFetchStart = source.indexOf('debugSetPagePerf("set_value.direct_fetch_start"');
  const directFetchEnd = source.indexOf('debugSetPagePerf("set_value.direct_fetch_ready"', directFetchStart);
  const directFetchSource = source.slice(directFetchStart, directFetchEnd);
  const directEffectStart = source.lastIndexOf("useEffect(() => {", directFetchStart);
  const directEffectEnd = source.indexOf("}, [setDetailMode, resolvedSetResourceId]);", directFetchStart);
  const directEffectSource = source.slice(directEffectStart, directEffectEnd);

  assert.ok(source.includes("getPokemonSetValueHistory"));
  assert.ok(source.includes("const [setValueHistoryState, setSetValueHistoryState] = useState"));
  assert.ok(directFetchStart >= 0);
  assert.ok(directFetchEnd > directFetchStart);
  assert.ok(directEffectSource.includes("const requestedScopes = SET_VALUE_SCOPE_OPTIONS.map((scope) => scope.key);"));
  assert.ok(directFetchSource.includes("requestedScopes.map"));
  assert.ok(directFetchSource.includes("CANONICAL_SET_VALUE_SCOPE"));
  assert.ok(directEffectSource.includes("resolvedSetResourceId"));
  assert.ok(!directEffectSource.includes("setValueTrendScope"));
  assert.ok(!directEffectSource.includes('setDetailTab === "overview"'));
  assert.ok(!directEffectSource.includes("shouldRenderMarketData"));
});

test("set value history warmup fetches all scopes after shell render", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const warmupStart = source.indexOf("const warmSetDetailResources = useCallback");
  const warmupEnd = source.indexOf("const resolvedSetId = String(setId || \"\").trim();", warmupStart);
  const warmupSource = source.slice(warmupStart, warmupEnd);

  assert.ok(warmupStart >= 0);
  assert.ok(warmupEnd > warmupStart);
  assert.ok(warmupSource.includes("SET_VALUE_SCOPE_OPTIONS.map((scope) =>"));
  assert.ok(warmupSource.includes("getPokemonSetValueHistory(resolvedSetId, { days: 365, scope: scope.key })"));
  assert.ok(warmupSource.includes("markSetPagePerformance(\"set_value_ready\""));
  assert.ok(warmupSource.includes("scopes: results"));
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
  assert.ok(source.includes("buildMarketDashboardStateFromPayload(activeMarketDashboardState.payload)"));
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
  assert.ok(ripSource.includes("normalizeMarketDashboardWindow"));
  assert.ok(ripSource.includes('const DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW = "365d"'));
  assert.ok(ripSource.includes("getTopMarketCardsCacheKey(resolvedSetId, DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW)"));
  assert.ok(dashboardRoute.includes("normalizeMarketDashboardWindow(window)"));
});

test("overview initial market dashboard request uses 365d snapshot source", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const marketSource = fs.readFileSync(marketClientPath, "utf8");
  const apiSource = fs.readFileSync(backendApiPath, "utf8");

  assert.ok(source.includes('const DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW = "365d"'));
  assert.ok(source.includes("const dashboardSourceWindow = DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW"));
  assert.ok(source.includes("getPokemonSetMarketDashboard(setId, { window: dashboardSourceWindow })"));
  assert.ok(source.includes("prefetchPokemonSetMarketDashboard(resolvedSetId, { window: DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW })"));
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
  assert.ok(source.includes("const summary = explorePayload?.summary || {};"));

  for (const field of requiredFields) {
    assert.ok(snapshotBuilderSource.includes(field), `snapshot builder propagates ${field}`);
    assert.ok(source.includes(field), `frontend normalizer accepts ${field}`);
  }

  const summaryStart = source.indexOf("const summary = explorePayload?.summary || {};");
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

test("header set value compact sparkline disables floating tooltip overlay", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const labelIndex = source.indexOf("{setValueMetricLabel}");
  const sparklineStart = source.indexOf("<CompactSparkline", labelIndex);
  const sparklineEnd = source.indexOf("/>", sparklineStart);
  const setValueSparklineSource = source.slice(sparklineStart, sparklineEnd);

  assert.ok(labelIndex >= 0);
  assert.ok(sparklineStart > labelIndex);
  assert.ok(setValueSparklineSource.includes("points={setValueSparklinePoints}"));
  assert.ok(setValueSparklineSource.includes('valueKey="setValue"'));
  assert.ok(setValueSparklineSource.includes("showTooltip={false}"));
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

test("card appeal market validation can hydrate from initial set page snapshot correlation", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("initialCardAppealMarketPriceCorrelation"));
  assert.ok(source.includes("explorePayload?.cardAppealMarketPriceCorrelation || explorePayload?.card_appeal_market_price_correlation"));
  assert.ok(source.includes("initialCardAppealRows"));
  assert.ok(source.includes("checklistState.cards.length > 0 ? checklistState.cards : initialCardAppealRows"));
  assert.ok(source.includes("checklistState.cardAppealMarketPriceCorrelation || initialCardAppealMarketPriceCorrelation"));
});
