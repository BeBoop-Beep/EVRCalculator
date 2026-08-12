// Phase 2A — set-page request gating contract.
//
// These tests assert *what the set page does not request*. The Phase 0 baseline
// found a cold RIP visit issuing Pull Rates, Insights Critical, Insights
// Secondary, Value History and Top Chase in parallel. The Phase 2A audit proved
// four of those five have real, currently-visible RIP consumers, so this file
// pins both halves of that result: the deferral that was made, and the four
// requests that must stay eager because RIP renders them. A future change that
// "optimizes" one of the eager four away is a visible-output regression, and
// these tests are the tripwire for it.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
// RipStatisticsPageClient.jsx has mixed CRLF/LF line endings; normalize before
// any multi-line slice/indexOf anchoring.
const pageSource = fs
  .readFileSync(path.join(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

function sliceEffect(startAnchor, endAnchor) {
  const start = pageSource.indexOf(startAnchor);
  assert.notEqual(start, -1, `missing anchor: ${startAnchor}`);
  const end = pageSource.indexOf(endAnchor, start);
  assert.notEqual(end, -1, `missing end anchor: ${endAnchor}`);
  return pageSource.slice(start, end);
}

// --- DEFERRED: Value History -------------------------------------------------

test("the 365d value-history fetch is gated to Market (plus a shell-seed fallback)", () => {
  const effect = sliceEffect("const titleCardNeedsCanonicalScopeFetch", "getPokemonSetValueHistory(setId");
  assert.ok(
    effect.includes("shellSetValueVisiblePoints.length === 0"),
    "the canonical scope must only be force-fetched when the shell seed is absent"
  );
  assert.ok(
    effect.includes('setDetailTab === "market" || titleCardNeedsCanonicalScopeFetch'),
    "the canonical scope must be requested for Market or as a shell-seed fallback, not unconditionally"
  );
  // The pre-Phase-2A shape requested the canonical scope on every tab.
  assert.ok(
    !/new Set\(\[\s*\n\s*CANONICAL_SET_VALUE_SCOPE,/.test(effect),
    "value history must no longer request the canonical scope unconditionally on every tab"
  );
});

test("Market still requests both the canonical scope and the user-selected trend scope", () => {
  const effect = sliceEffect("const titleCardNeedsCanonicalScopeFetch", "getPokemonSetValueHistory(setId");
  assert.ok(
    effect.includes('...(setDetailTab === "market" ? [setValueTrendScope || CANONICAL_SET_VALUE_SCOPE] : [])'),
    "Market must keep requesting its selected Set Value Trend scope"
  );
});

test("gating value history did not remove its scope de-duplication", () => {
  const effect = sliceEffect("const titleCardNeedsCanonicalScopeFetch", "getPokemonSetValueHistory(setId");
  // Returning to a tab must not refetch a scope this effect already loaded.
  assert.ok(effect.includes("alreadyLoadedScopes"), "already-loaded scopes must still be filtered out");
  assert.ok(effect.includes("seededLoadedScopes"), "server/dashboard-seeded scopes must still be filtered out");
  assert.ok(
    effect.includes("if (requestedScopes.length === 0)"),
    "an empty scope list must short-circuit before any request is issued"
  );
});

test("value history requests its scopes in parallel, not as a waterfall", () => {
  const effect = sliceEffect("const titleCardNeedsCanonicalScopeFetch", "  }, [");
  assert.ok(
    effect.includes("Promise.all("),
    "multiple requested scopes must be issued concurrently"
  );
});

// --- KEPT EAGER ON RIP: proven RIP consumers ---------------------------------

test("Pull Rates stays eager on RIP because RIP renders its rarity odds", () => {
  const effect = sliceEffect(
    "  // Pull Rates tab fetch effect (Phase 4A)",
    "getPokemonSetPullRates(setId)"
  );
  assert.ok(
    effect.includes('if (setDetailTab !== "pull-rates" && setDetailTab !== "overview")'),
    "RIP must keep fetching pull rates: RipDecisionPage's Opening Odds reads rarityOddsDenominator from it"
  );
  // The consumer that makes it RIP-critical.
  assert.ok(
    pageSource.includes("pullRateAssumptions={pullRateAssumptions}"),
    "RIP must still pass pullRateAssumptions into RipDecisionPage"
  );
});

test("Top Chase stays eager on RIP because RIP renders a chase preview", () => {
  const effect = sliceEffect("const shouldFetchTopChase", "getPokemonSetTopChase(setId");
  assert.ok(
    effect.includes('setDetailTab === "overview" || setDetailTab === "market"'),
    "Top Chase is shared RIP/Market data and must not be gated to Market alone"
  );
  assert.ok(
    effect.includes("lastTopChaseRequestKeyRef"),
    "RIP<->Market switching must still share a single Top Chase fetch per set/window"
  );
});

test("Insights Critical and Secondary both stay eager: RIP renders percentiles and desirability", () => {
  // Secondary owns outcomeDistribution.percentiles, which RIP reads above the
  // fold as p50/p95 in RipDecisionPage — it is not below-fold data despite the
  // name, so it must not be viewport-gated.
  assert.ok(pageSource.includes("getPokemonSetInsightsSecondary"), "secondary insights must still be fetched");
  assert.ok(pageSource.includes("getPokemonSetInsightsCritical"), "critical insights must still be fetched");
  assert.ok(pageSource.includes("const percentileP50 = getPercentileValue(percentiles, 50)"));
  assert.ok(pageSource.includes("const percentileP95 = getPercentileValue(percentiles, 95)"));
  assert.ok(pageSource.includes("p50={percentileP50}"), "RIP must still render p50 from secondary insights");
  assert.ok(pageSource.includes("p95={percentileP95}"), "RIP must still render p95 from secondary insights");
});

// --- ALREADY GATED: must not regress back to eager ----------------------------

test("Market-only requests do not fire on RIP", () => {
  const overview = sliceEffect("const shouldRenderMarketOverviewData", "getPokemonSetOverview(setId");
  assert.ok(
    overview.includes('const shouldRenderMarketOverviewData = setDetailTab === "market"'),
    "the slim /overview payload is Market-owned"
  );
  const movers = sliceEffect("const isMarketMoversConsumer", "getPokemonSetMarketMovers(setId");
  assert.ok(
    movers.includes('const isMarketMoversConsumer = setDetailTab === "market"'),
    "market movers is Market-owned"
  );
});

test("Cards requests do not fire on RIP, Market or Pull Rates", () => {
  assert.ok(
    pageSource.includes('setDetailMode && (setDetailTab === "cards" || setDetailTab === "insights")'),
    "cards are only needed by the Cards tab"
  );
  const cardsPage = sliceEffect("  // Cards tab: slim, paginated fetch", "getPokemonSetCardsPage(setId, {");
  assert.ok(
    /setDetailTab !== "cards"/.test(cardsPage) || /setDetailTab === "cards"/.test(cardsPage),
    "the Cards page fetch must be gated on the Cards tab"
  );
});

test("the legacy full-page snapshot fetch remains permanently inert", () => {
  // SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD is empty, so no tab can trigger
  // the monolithic /page payload. Proven-dead, but left in place per scope.
  const declaration = sliceEffect("const SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD", "\n");
  assert.ok(
    /=\s*new Set\(\[\]\)/.test(declaration),
    "no tab may reintroduce the full-page snapshot fetch"
  );
});

// --- Direct tab landings own their data immediately ---------------------------

test("every tab-gated fetch keys off setDetailTab directly, so a direct URL load fetches without interaction", () => {
  // The gates are plain `setDetailTab === ...` reads inside effects that run on
  // mount, not click handlers — a direct ?tab=<x> landing therefore fetches on
  // first commit rather than waiting for a user interaction.
  for (const anchor of [
    'const shouldRenderMarketOverviewData = setDetailTab === "market"',
    'const isMarketMoversConsumer = setDetailTab === "market"',
    'if (setDetailTab !== "pull-rates" && setDetailTab !== "overview")',
    'const shouldFetchTopChase = setDetailTab === "overview" || setDetailTab === "market"',
  ]) {
    assert.ok(pageSource.includes(anchor), `missing tab-owned fetch gate: ${anchor}`);
    const context = pageSource.slice(pageSource.indexOf(anchor) - 2000, pageSource.indexOf(anchor));
    assert.ok(
      context.includes("useEffect("),
      `${anchor} must be evaluated inside an effect (mount-driven), not an interaction handler`
    );
  }
});
