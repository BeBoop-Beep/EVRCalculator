import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const read = (file) => fs.readFileSync(path.resolve(file), "utf8");
const page = read("components/explore/RipStatisticsPageClient.jsx");
const decision = read("components/explore/RipDecisionPage.jsx");
const cache = read("lib/pokemon/pokemonSetRipResourceClient.mjs");
const proxy = read("lib/pokemon/setRipProjectionProxy.js");

test("simulation and advanced are near-viewport resources, never mount-time RIP effects", () => {
  assert.match(decision, /IntersectionObserver/);
  assert.match(decision, /rootMargin: "800px 0px"/);
  assert.match(decision, /ref=\{simulationSectionRef\}/);
  assert.match(decision, /ref=\{advancedSectionRef\}/);
  assert.match(page, /onSimulationApproach=\{loadRipSimulation\}/);
  assert.match(page, /onAdvancedApproach=\{loadRipAdvanced\}/);
});

test("RIP distribution has one same-run source and dead props are removed", () => {
  assert.match(page, /distributionBins=\{compatibleRipSimulation\?\.distributionBins \?\? \[\]\}/);
  for (const prop of ["chaseCards", "simulationDrivers", "packPaths", "normalStateRows", "p50", "p95", "p99"]) {
    assert.doesNotMatch(decision, new RegExp(`\\b${prop}\\s*=`));
  }
  assert.doesNotMatch(page.slice(page.indexOf("<RipDecisionPage"), page.indexOf("<RipDecisionPage") + 5000), /getPokemonSetInsightsSecondary|simulationDrivers=|packPaths=|normalStateRows=/);
});

test("page-lifetime caches are run-keyed bounded timed and retryable", () => {
  assert.match(cache, /MAX_ENTRIES = 8/);
  assert.match(cache, /TTL_MS = 5 \* 60 \* 1000/);
  assert.match(cache, /BROWSER_TIMEOUT_MS = 20_000/);
  assert.match(cache, /setId.*calculationRunId/);
  assert.match(cache, /cache\.delete\(key\)/);
  assert.match(proxy, /TIMEOUT_MS = 9000/);
});

test("Basic never approaches advanced while entitled users get localized retries", () => {
  assert.match(decision, /entry\.target === advancedSectionRef\.current && canViewProductRipIntelligence/);
  assert.match(decision, /Retry simulation evidence/);
  assert.match(decision, /Retry advanced evidence/);
  assert.match(decision, /Retry rank context/);
});
