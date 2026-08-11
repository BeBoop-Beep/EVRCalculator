import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pageSource = fs.readFileSync(path.join(here, "RipStatisticsPageClient.jsx"), "utf8");
const ripSource = fs.readFileSync(path.join(here, "RipDecisionPage.jsx"), "utf8");

// The six-section "research paper" Analysis wrapper (RIP Score / Simulation /
// Value Structure / Market / Sealed / Methodology) was reverted. Analysis is
// once again the previous deep analytical experience that already lived in this
// file, and it no longer owns any market-observation module.

test("the six-section Analysis wrapper is gone", () => {
  for (const marker of [
    "data-analysis-page",
    "analysis-rip-score",
    "analysis-simulation",
    "analysis-value-structure",
    "analysis-market",
    "analysis-sealed",
    "analysis-methodology",
  ]) {
    assert.ok(!pageSource.includes(marker), `${marker} must not survive the revert`);
  }
});

test("the previous deep Analysis implementation is re-enabled for set detail", () => {
  assert.ok(
    pageSource.includes('{(!setDetailMode || setDetailTab === "insights") && !showInsightsCohesiveLoading ? ('),
    "the previous Insights/Analysis render gate must include setDetailMode + insights again"
  );
  for (const moduleName of [
    "RipScoreBreakdownModule",
    "RipDistributionChart",
    "SimulationMetricsContent",
    "TopEVDriversContent",
    "CollectorAppealBreakdown",
    "PackValueHistoryChart",
  ]) {
    assert.ok(pageSource.includes(moduleName), `${moduleName} remains mounted for Analysis`);
  }
});

test("Analysis no longer owns market observation", () => {
  // Analysis explains the opening MODEL. Market observation (set value, the
  // Top 10 market table, 7D movers, sealed pricing) belongs to the Market tab.
  const marketSection = pageSource.slice(
    pageSource.indexOf('{setDetailTab === "market" ? ('),
    pageSource.indexOf("RETIRED: the pre-RIP-page Overview composition")
  );
  assert.ok(marketSection.length > 0, "the Market section must exist to own these modules");
  for (const moduleName of ["SetValueTrendCard", "SevenDayMarketMoversTicker", "SealedMarketTrendCard", "TopChaseCardsModule"]) {
    assert.ok(marketSection.includes(moduleName), `${moduleName} is Market-owned`);
  }
  assert.ok(!pageSource.includes('title="Market Snapshot"'), "the invented Analysis Market Snapshot must not survive");
  assert.ok(!pageSource.includes('title="Market Analysis"'), "Analysis must not render a market-analysis card");

  for (const forbidden of ["SetValueTrendCard", "SevenDayMarketMoversTicker", "SealedMarketTrendCard", "TopChaseCardsModule", "RipDistributionChart"])
    assert.ok(!ripSource.includes(forbidden), `${forbidden} must not return to RIP`);
});

test("Analysis keeps current terminology and canonical model families", () => {
  for (const label of ["Expected Value", "Typical Opening", "Strong Upside", "Jackpot Upside"])
    assert.ok(pageSource.includes(label), `${label} must survive the structural revert`);
  for (const retired of ["Typical Pack", "Realistic Upside", "God Pull Upside"])
    assert.ok(!pageSource.includes(retired), `${retired} is a retired label and must not come back`);
  for (const component of ["Win Frequency", "Typical Retention", "Loss Resilience", "Strong Upside", "Jackpot Upside", "Base Economic Efficiency"])
    assert.ok(fs.readFileSync(path.join(here, "financialRipV3Selector.mjs"), "utf8").includes(`title: "${component}"`));
  assert.ok(!pageSource.includes("Relative RIP Index: 100 / 100"));
});
