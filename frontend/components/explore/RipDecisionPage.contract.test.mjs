import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { buildRipDecisionModel } from "./ripDecisionModel.mjs";

const directory = path.dirname(new URL(import.meta.url).pathname.slice(1));
const pagePath = path.resolve(directory, "RipDecisionPage.jsx");
const cssPath = path.resolve(directory, "RipDecisionPage.module.css");
const evidencePath = path.resolve(directory, "RipStoryEvidence.jsx");

test("RIP page follows the progressive decision narrative", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const ids = ["decision", "why-it-ranks", "financial-explanation", "simulation-evidence", "simulation-drivers", "collector-explanation", "collector-drivers"];
  const positions = ids.map((id) => source.indexOf(`data-rip-section=\"${id}\"`));
  assert.ok(positions.every((position) => position >= 0));
  assert.deepEqual([...positions].sort((a, b) => a - b), positions);
});

test("score anatomy represents Overall once above two supporting dimensions", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  for (const key of ["overall", "financial", "collector"]) assert.ok(source.includes(`key: "${key}"`));
  assert.equal((source.match(/label: "Overall RIP"/g) || []).length, 1);
  assert.ok(source.indexOf("metrics.overall") < source.indexOf("styles.supportingScores"));
  for (const cta of ["How Overall RIP works", "Explore Financial RIP", "Explore Collector Appeal"]) assert.ok(source.includes(cta));
  assert.ok(source.includes("prefers-reduced-motion: reduce"));
  assert.ok(source.includes('tabIndex={-1}'));
  assert.ok(source.includes("getRipTierPresentation(metric.tier"));
  assert.ok(source.includes("data-score-tier"));
  assert.ok(!source.includes('"--score-accent"'), "category accent does not style score surfaces");
});

test("Overall score hero accepts dynamic product context and degrades without art", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes('productType = "booster_pack"'));
  assert.ok(source.includes('productLabel = "Booster Pack"'));
  assert.ok(source.includes("productContext?.productImage"));
  assert.ok(source.includes("productImage.src || productContext.productImage"));
  assert.ok(!source.includes("Ascended Heroes"));
});

test("product art separates on desktop and remains in-card on mobile", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const css = fs.readFileSync(cssPath, "utf8");
  assert.ok(source.includes("styles.overallProductRow"));
  assert.ok(source.includes("styles.desktopProductArt"));
  assert.ok(source.includes("productContext.productImage"), "compact in-card image remains dynamic");
  assert.match(css, /\.productArt \{ display: none;/);
  assert.match(css, /@media \(max-width:767px\)[\s\S]*\.productArt \{ display: block;/);
  assert.match(css, /\.desktopProductArt \{ display: none; \}/);
  assert.match(css, /\.anatomy \{ position: relative;/);
  assert.match(css, /\.overallProductRow \{ width: min\(100%,52rem\); \}/);
  assert.doesNotMatch(css, /\.overallProductRow[^}]*grid-template-columns/);
  assert.match(css, /left: calc\(50% - 26rem -/);
  assert.match(css, /@media \(min-width:768px\) and \(max-width:1179px\)[\s\S]*\.desktopProductArt \{ display: none;/);
});

test("canonical public scores preserve zero and never fall back to legacy summary values", () => {
  const model = buildRipDecisionModel({
    canonical: {
      overall: { relativeScore: 0, absoluteScore: 4, rank: 22, rankedSetCount: 22 },
      financialRip: { relativeScore: 80, absoluteScore: 42, rank: 4, rankedSetCount: 22 },
      collectorAppeal: { relativeScore: 88, absoluteScore: 67, rank: 2, rankedSetCount: 22 },
    },
    summary: { rip: { score: 99 }, ripCore: { score: 99 } },
  });
  assert.equal(model.overall.publicScore, 0);
  assert.equal(model.financial.publicScore, 80);
  assert.equal(model.collector.publicScore, 88);
  assert.equal(buildRipDecisionModel({ canonical: { overall: {}, financialRip: {}, collectorAppeal: {} } }).overall.publicScore, null);
});

test("Financial explanation mounts the canonical six-row component before simulation evidence", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes("<FinancialRipV3Breakdown"));
  assert.ok(source.indexOf('data-rip-section="financial-explanation"') < source.indexOf('data-rip-section="simulation-evidence"'));
  assert.ok(!source.includes("Profit/Safety/Stability"));
  assert.ok(!source.includes("Weight "));
});

test("simulation reuses one distribution chart and existing top-hit evidence", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const evidence = fs.readFileSync(evidencePath, "utf8");
  assert.equal((source.match(/<RipDistributionChart/g) || []).length, 1);
  for (const label of ["Expected Value", "Typical Opening", "Chance to Beat Cost", "Strong Upside", "Jackpot Upside"]) assert.ok(source.includes(label));
  assert.ok(source.includes("simulationDrivers={topHits}") || source.includes("drivers={simulationDrivers}"));
  assert.ok(evidence.includes("driver.ev_contribution"));
  assert.ok(evidence.includes("driver.current_near_mint_price"));
  assert.ok(source.includes("<SimulationFullReport"));
  assert.ok(evidence.includes("View value structure details"));
});

test("Collector story keeps two factors and diagnostic depth separate", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes("<CollectorAppealBreakdown"));
  assert.ok(source.includes("Additional collector diagnostics"));
  assert.ok(source.includes("selectCollectorRankDrivers"));
  assert.ok(source.includes("collectorDrivers"));
  assert.ok(source.includes("Not part of the current Collector Appeal score"));
  assert.ok(source.includes("What Are You Chasing?"));
  assert.ok(source.includes("View all modeled pull rates"));
  const evidence = fs.readFileSync(evidencePath, "utf8");
  assert.ok(evidence.includes("Share of set demand"));
  assert.ok(!evidence.includes("Demand {subject"));
});

test("responsive structure avoids fixed-width overflow and keeps supporting scores together", () => {
  const css = fs.readFileSync(cssPath, "utf8");
  assert.match(css, /\.supportingScores[^}]*repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /@media \(max-width:767px\)/);
  assert.match(css, /\.scoreSurface[^}]*min-width:\s*0/);
  assert.ok(!css.includes("overflow-x: auto"));
});

test("mobile rebuild flattens context shells while preserving meaningful inner cards", () => {
  const css = fs.readFileSync(cssPath, "utf8");
  assert.match(css, /\.page > \.panel:not\(:first-child\)[^}]*border:\s*0/);
  assert.match(css, /\.page > \.panel:not\(:first-child\)[^}]*background:\s*transparent/);
  assert.match(css, /\.scoreSurface[^}]*border:/, "score cards remain bounded objects");
  assert.match(css, /\.driverCard[^}]*border:/, "driver cards remain bounded objects");
});

test("mobile analytical rows and collector subjects use compact disclosures", () => {
  const rowSource = fs.readFileSync(path.resolve(directory, "RipMetricDisclosureRow.jsx"), "utf8");
  const evidence = fs.readFileSync(evidencePath, "utf8");
  const chart = fs.readFileSync(path.resolve(directory, "RipDistributionChart.jsx"), "utf8");
  assert.ok(rowSource.includes("data-rip-metric-interpretation"));
  assert.ok(rowSource.includes("aria-expanded={isOpen}"));
  assert.ok(rowSource.includes("aria-controls={panelId}"));
  assert.ok(evidence.includes("subjectMobileList"));
  assert.ok(evidence.includes("representative = subject.accessiblePath || subject.elitePath"));
  assert.ok(evidence.includes('<SubjectPath label="More attainable"'));
  assert.ok(evidence.includes('<SubjectPath label="Elite chase"'));
  assert.ok(chart.includes("data-mobile-chart-layout"));
  assert.ok(chart.includes("compact={isMobile}"));
});
