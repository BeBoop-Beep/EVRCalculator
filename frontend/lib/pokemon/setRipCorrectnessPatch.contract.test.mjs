import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { resolveRankingsPlanAccess } from "../access/indexPlanAccess.mjs";
import { selectSetRipRankContext } from "./pokemonSetRipRankContextClient.mjs";
import { selectSameRunRipSimulation } from "./pokemonSetRipProgressiveClient.mjs";

const read = (file) => fs.readFileSync(path.resolve(file), "utf8");
const page = read("components/explore/RipStatisticsPageClient.jsx");
const decision = read("components/explore/RipDecisionPage.jsx");
const marketClient = read("lib/pokemon/pokemonSetMarketClient.js");
const mobile = read("components/pokemon/set-page/Market/SetMarketMobile.jsx");
const backend = read("../backend/api/main.py");

test("latest published rank context remains usable and explicitly stale", () => {
  const context = selectSetRipRankContext({ contractVersion: "pokemon-set-rip-rank-context-v1", setId: "set-a", rankingCalculationRunId: "rank-old", rankingUpdatedAt: "2026-08-26", productFamilyRankings: { families: { etb: { products: [{ setId: "set-a", familyRank: 2 }] } } } }, { setId: "set-a", calculationRunId: "set-current" });
  assert.equal(context.freshness, "latest_published");
  assert.equal(context.productFamilyRankings.families.etb.products[0].familyRank, 2);
  assert.match(decision, /Product Rank, RIP Score and Tier use the latest global Rankings publication/);
  assert.match(decision, /rankContextStatus === "error"/);
  assert.doesNotMatch(decision, /rankContextFreshness === "latest_published"[\s\S]{0,500}Retry rank context/);
});

test("same-run rank context is current while a different publication stays latest-published", () => {
  const payload = { contractVersion: "pokemon-set-rip-rank-context-v1", setId: "set-a", rankingCalculationRunId: "run-a", productFamilyRankings: { families: {} } };
  assert.equal(selectSetRipRankContext(payload, { setId: "set-a", calculationRunId: "run-a" }).freshness, "current");
  assert.equal(selectSetRipRankContext(payload, { setId: "set-a", calculationRunId: "run-b" }).freshness, "latest_published");
});

test("rank-context request gate uses canonical plan access: Basic 0, Plus 1, Premium 1", () => {
  const requestCounts = [null, "plus", "premium"].map((index_plan) =>
    Number(resolveRankingsPlanAccess({ index_plan }).canViewRankingsIntelligence),
  );
  assert.deepEqual(requestCounts, [0, 1, 1]);
  assert.match(page, /useRankingsAccess\(\)/);
  assert.match(page, /if \(!canViewProductRipIntelligence \|\| !setId \|\| !expectedCalculationRunId\) return/);
  assert.match(page, /canViewProductRipIntelligence=\{canViewProductRipIntelligence\}/);
});

test("Best Way hero score comes from the selected family rank row", () => {
  assert.match(decision, /heroPick\.familyRankInfo\?\.overallRipLeaderScore/);
  assert.doesNotMatch(decision, /score\(heroProduct\.overallRipScore\)/);
});

test("rank context owns ranks while ripDecision continues to own economics", () => {
  const call = page.slice(page.indexOf("<RipDecisionPage"), page.indexOf("<RipDecisionPage") + 5000);
  assert.match(call, /ripDecision=\{ripBootstrap\?\.ripDecision/);
  assert.match(call, /productFamilyRankings=\{ripRankContext\?\.productFamilyRankings/);
  assert.doesNotMatch(call, /compatibleRipGlobalContext/);
});

test("product identities and Best Way artwork, title and CTA use canonical product-detail hrefs", () => {
  assert.match(decision, /<Link href=\{href\} aria-label=\{`View \$\{product\.label\}`\}>\{content\}<\/Link>/);
  assert.ok((decision.match(/href=\{buildSealedProductHref\(heroProduct\.sealedProductId\)\}/g) || []).length >= 3);
  assert.match(decision, /event\.target\.closest\("a,button,\[role='button'\]"\)/);
  assert.match(decision, /event\.key === "Enter"/);
});

test("simulation profile is same-run and no longer comes from rank context", () => {
  const simulation = selectSameRunRipSimulation({ contractVersion: "pokemon-set-rip-simulation-evidence-v1", setId: "set-a", calculationRunId: "run-a", distributionBins: [], thresholdBins: [], openingOutcomeProfile: { calculationRunId: "run-a", buckets: [] } }, { setId: "set-a", calculationRunId: "run-a" });
  assert.equal(simulation.openingOutcomeProfile.calculationRunId, "run-a");
  assert.equal(selectSameRunRipSimulation({ ...simulation, openingOutcomeProfile: { calculationRunId: "old" } }, { setId: "set-a", calculationRunId: "run-a" }), null);
  assert.match(page, /openingOutcomeProfile=\{compatibleRipSimulation\?\.openingOutcomeProfile/);
  assert.doesNotMatch(page, /openingOutcomeProfile=\{ripRankContext/);
});

test("dead EV realization disclosure is completely absent", () => {
  assert.doesNotMatch(decision, /When Does EV Start Looking Real|deep-dive-ev-realization|EvRepresentativenessSection/);
});

test("sealed summary is aggregate-only and full products stay deferred", () => {
  const summaryRoute = backend.slice(backend.indexOf('market/sealed-summary'), backend.indexOf('market/sealed-summary') + 2600);
  assert.match(summaryRoute, /setPageConsumerMarket/);
  assert.doesNotMatch(summaryRoute, /setPageConsumerTopProducts/);
  assert.match(marketClient, /sealed-summary:\$\{resolvedSetId\}/);
  assert.match(marketClient, /sealed-consumer:\$\{resolvedSetId\}/);
  assert.match(mobile, /sealedSummaryState=\{sealedSummaryState\}/);
  assert.match(mobile, /sealedState=\{sealedProductsState\}/);
});
