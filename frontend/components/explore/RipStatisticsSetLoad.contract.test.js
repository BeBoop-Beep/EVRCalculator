const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const test = require("node:test");
const assert = require("node:assert/strict");

const ripPageClientPath = path.resolve(__dirname, "RipStatisticsPageClient.jsx");
const marketDashboardStatePath = path.resolve(__dirname, "marketDashboardState.mjs");
const marketClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetMarketClient.js");
const cardsClientPath = path.resolve(__dirname, "../../lib/pokemon/pokemonSetCardsClient.js");
const dashboardRoutePath = path.resolve(
  __dirname,
  "../../app/api/tcgs/pokemon/sets/[setId]/market/dashboard/route.js"
);
const cardsRoutePath = path.resolve(__dirname, "../../app/api/tcgs/pokemon/sets/[setId]/cards/route.js");
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
  const directEffectEnd = source.indexOf("}, [setDetailMode, resolvedSetResourceId, setValueTrendScope]);", directFetchStart);
  const directEffectSource = source.slice(directEffectStart, directEffectEnd);

  assert.ok(source.includes("getPokemonSetValueHistory"));
  assert.ok(source.includes("const [setValueHistoryState, setSetValueHistoryState] = useState"));
  assert.ok(directFetchStart >= 0);
  assert.ok(directFetchEnd > directFetchStart);
  assert.ok(directFetchSource.includes("requestedScopes.map"));
  assert.ok(directFetchSource.includes("CANONICAL_SET_VALUE_SCOPE"));
  assert.ok(directEffectSource.includes("resolvedSetResourceId"));
  assert.ok(!directEffectSource.includes('setDetailTab === "overview"'));
  assert.ok(!directEffectSource.includes("shouldRenderMarketData"));
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
