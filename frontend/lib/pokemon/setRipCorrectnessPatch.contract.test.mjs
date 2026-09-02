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

test("the old free-standing EV realization deep-dive row is not resurrected", () => {
  // The row/component this used to guard were removed because their data
  // came from the "global context" publication, which can legitimately lag
  // the set's own calculation run. That is a staleness bug, not a reason to
  // ban the metric forever: it now rides the same-run simulation-evidence
  // payload instead (see the invariant below), rendered inline as a compact
  // headline rather than a duplicate section/row.
  assert.doesNotMatch(decision, /deep-dive-ev-realization|EvRepresentativenessSection/);
});

test("EV realization headline only ever renders from the same calculationRunId as the active simulation", () => {
  const report = read("components/explore/SimulationFullReport.jsx");
  const selector = read("components/explore/evRepresentativenessSelector.mjs");
  // The headline lives in the same-run simulation evidence report, not in a
  // dedicated section/request.
  assert.match(report, /evRep\?\.realizationHorizon/);
  assert.doesNotMatch(report, /EvRepresentativenessSection/);
  // Its selector refuses to project anything for a mismatched run.
  assert.match(selector, /String\(value\.calculationRunId\) !== String\(expectedCalculationRunId\)/);

  const sameRun = selectSameRunRipSimulation(
    {
      contractVersion: "pokemon-set-rip-simulation-evidence-v1",
      setId: "set-a",
      calculationRunId: "run-a",
      evRepresentativeness: { calculationRunId: "run-a", contractVersion: "ev_representativeness_public_v1", methodVersion: "ev_representativeness_v1", realizationHorizon: { targetEvRatio: 0.8, openerProbability: 0.8, packCount: 420, status: "confirmed" } },
    },
    { setId: "set-a", calculationRunId: "run-a" },
  );
  assert.equal(sameRun.evRepresentativeness.realizationHorizon.packCount, 420);

  // A stale/different-run evRepresentativeness block never survives the
  // same-run gate, even when the rest of the simulation payload matches.
  const staleRun = selectSameRunRipSimulation(
    {
      contractVersion: "pokemon-set-rip-simulation-evidence-v1",
      setId: "set-a",
      calculationRunId: "run-a",
      evRepresentativeness: { calculationRunId: "run-old", contractVersion: "ev_representativeness_public_v1", methodVersion: "ev_representativeness_v1", realizationHorizon: { targetEvRatio: 0.8, openerProbability: 0.8, packCount: 420, status: "confirmed" } },
    },
    { setId: "set-a", calculationRunId: "run-a" },
  );
  assert.equal(staleRun, null);
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
