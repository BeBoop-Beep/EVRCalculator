const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const ripPageClientPath = path.resolve(__dirname, "RipStatisticsPageClient.jsx");
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

test("set detail dependent fetches use one stable resolved set resource id", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");

  assert.ok(source.includes("function getResolvedPokemonSetResourceId"));
  assert.ok(source.includes("const resolvedSetResourceId = useMemo("));
  assert.ok(source.includes("const setId = resolvedSetResourceId;"));
  assert.ok(source.includes('routeSetId: requestedTargetId'));
  assert.ok(source.includes('resolvedSetId: setId'));
});

test("overview shares a single market dashboard request for value trend and top chase cards", () => {
  const source = fs.readFileSync(ripPageClientPath, "utf8");
  const dashboardCallCount = (source.match(/getPokemonSetMarketDashboard\(/g) || []).length;

  assert.equal(dashboardCallCount, 1);
  assert.ok(source.includes("buildMarketDashboardStateFromPayload(payload)"));
  assert.ok(source.includes("setTopMarketCardsState({"));
  assert.ok(source.includes("setSetValueHistoryState({"));
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
