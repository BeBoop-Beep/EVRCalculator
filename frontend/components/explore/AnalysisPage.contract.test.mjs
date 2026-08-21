import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pageSource = fs.readFileSync(path.join(here, "RipStatisticsPageClient.jsx"), "utf8");
const ripSource = fs.readFileSync(path.join(here, "RipDecisionPage.jsx"), "utf8");

// Set-specific simulation and scoring evidence belongs to RIP. The legacy
// Analysis destination must not survive as a competing information architecture.

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

test("legacy Analysis is removed from set navigation and redirects to RIP", () => {
  assert.ok(!pageSource.includes('{ value: "insights", label: "Analysis"'));
  assert.ok(pageSource.includes('analysis: "overview"'));
  assert.ok(pageSource.includes('analytics: "overview"'));
  assert.ok(pageSource.includes('{!setDetailMode && !showInsightsCohesiveLoading ? ('));
});

test("Analysis no longer owns market observation", () => {
  // Analysis explains the opening MODEL. Market observation (set value, the
  // Top 10 market table, 7D movers, sealed pricing) belongs to the Market tab.
  const marketSection = pageSource.slice(
    pageSource.indexOf('{setDetailTab === "market" ? ('),
    pageSource.indexOf("RETIRED: the pre-RIP-page Overview composition")
  );
  assert.ok(marketSection.length > 0, "the Market section must exist to own these modules");
  // Market's composition was redesigned into three sections; set value and
  // sealed pricing are now lenses inside SetMarketOverviewSection rather than
  // standalone cards. What this test is actually about — that market
  // observation lives on Market and nowhere else — is unchanged.
  for (const moduleName of ["SevenDayMarketMoversTicker", "SetMarketOverviewSection", "TopChaseCardsPanel"]) {
    assert.ok(marketSection.includes(moduleName), `${moduleName} is Market-owned`);
  }
  assert.ok(!pageSource.includes('title="Market Snapshot"'), "the invented Analysis Market Snapshot must not survive");
  assert.ok(!pageSource.includes('title="Market Analysis"'), "Analysis must not render a market-analysis card");

  for (const forbidden of ["SetValueTrendCard", "SevenDayMarketMoversTicker", "SealedMarketTrendCard", "TopChaseCardsModule"])
    assert.ok(!ripSource.includes(forbidden), `${forbidden} must not return to RIP`);
  assert.ok(ripSource.includes("RipDistributionChart"), "the existing distribution moves to RIP");
});

test("Analysis keeps current terminology and canonical model families", () => {
  for (const label of ["Expected Value", "Typical Opening", "Strong Upside", "Jackpot Upside"])
    assert.ok(pageSource.includes(label), `${label} must survive the structural revert`);
  for (const retired of ["Typical Pack", "Realistic Upside", "God Pull Upside"])
    assert.ok(!pageSource.includes(retired), `${retired} is a retired label and must not come back`);
  for (const component of ["Win Frequency", "Typical Retention", "Loss Resilience", "Strong Upside Quality", "Jackpot Upside Quality", "Base Economic Efficiency"])
    assert.ok(fs.readFileSync(path.join(here, "financialRipV3Selector.mjs"), "utf8").includes(`title: "${component}"`));
  assert.ok(!pageSource.includes("Relative RIP Index: 100 / 100"));
});
