import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pageSource = fs.readFileSync(path.join(here, "RipStatisticsPageClient.jsx"), "utf8");
const ripSource = fs.readFileSync(path.join(here, "RipDecisionPage.jsx"), "utf8");

test("Analysis follows the locked six-section causal narrative", () => {
  const markers = [
    "analysis-rip-score",
    "analysis-simulation",
    "analysis-value-structure",
    "analysis-market",
    "analysis-sealed",
    "analysis-methodology",
  ].map((marker) => pageSource.indexOf(`id=\"${marker}\"`));
  assert.ok(markers.every((position) => position >= 0));
  assert.deepEqual(markers, [...markers].sort((left, right) => left - right));
});

test("Analysis owns the migrated production evidence modules", () => {
  for (const moduleName of [
    "RipScoreBreakdownModule",
    "RipDistributionChart",
    "SimulationMetricsContent",
    "TopChaseCardsModule",
    "TopEVDriversContent",
    "SetValueTrendCard",
    "SevenDayMarketMoversTicker",
    "SealedMarketTrendCard",
  ]) assert.ok(pageSource.includes(moduleName), `${moduleName} remains mounted`);

  for (const forbidden of ["SetValueTrendCard", "SevenDayMarketMoversTicker", "SealedMarketTrendCard", "TopChaseCardsModule", "RipDistributionChart"])
    assert.ok(!ripSource.includes(forbidden), `${forbidden} must not return to RIP`);
});

test("Analysis uses current terminology and canonical model families", () => {
  for (const label of ["Expected Value", "Typical Opening", "Strong Upside", "Jackpot Upside"])
    assert.ok(pageSource.includes(label));
  for (const component of ["Win Frequency", "Typical Retention", "Loss Resilience", "Strong Upside", "Jackpot Upside", "Base Economic Efficiency"])
    assert.ok(fs.readFileSync(path.join(here, "financialRipV3Selector.mjs"), "utf8").includes(`title: \"${component}\"`));
  assert.ok(pageSource.includes("Relative RIP Index is cohort-relative"));
  assert.ok(!pageSource.includes("Relative RIP Index: 100 / 100"));
});

test("methodology uses keyboard-native disclosures and states unavailable contracts honestly", () => {
  assert.ok(pageSource.includes("<details"));
  assert.ok(pageSource.includes("<summary"));
  assert.ok(pageSource.includes("Collector Appeal factor weights are not disclosed"));
  assert.ok(pageSource.includes("cards-falling breadth are omitted"));
});
