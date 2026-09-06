import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { buildRipDecisionModel } from "./ripDecisionModel.mjs";
import { selectChaseAccessibilityPresentation } from "./chaseAccessibilityPresentationSelector.mjs";
import { selectOverallRipExplanationHierarchy } from "./overallRipExplanationHierarchySelector.mjs";

const directory = path.dirname(new URL(import.meta.url).pathname.slice(1));
const ripPagePath = path.resolve(directory, "RipDecisionPage.jsx");
const marketBasedPath = path.resolve(directory, "MarketBasedOpeningQualityBreakdown.jsx");
const analysisClientPath = path.resolve(
  directory,
  "..",
  "pokemon",
  "set-page",
  "Analysis",
  "PokemonSetAnalysisClient.jsx",
);

const ripPageSource = () => fs.readFileSync(ripPagePath, "utf8");
const analysisSource = () => fs.readFileSync(analysisClientPath, "utf8");
const marketBasedSource = () => fs.readFileSync(marketBasedPath, "utf8");

// ---------------------------------------------------------------------------
// Set RIP (RipDecisionPage.jsx)
// ---------------------------------------------------------------------------

test("A: Opening Snapshot contains Overall RIP, Market-Based Opening Quality, Financial RIP, Chase Accessibility and Collector Appeal", () => {
  const source = ripPageSource();
  assert.ok(source.includes('data-rip-section="opening-snapshot"'));
  const snapshotStart = source.indexOf('data-rip-section="opening-snapshot"');
  const snapshotEnd = source.indexOf(
    'data-rip-section="compare-products"',
    snapshotStart,
  );
  const snapshot = source.slice(snapshotStart, snapshotEnd);
  assert.ok(snapshot.includes("metrics.overall"), "Overall RIP renders in the snapshot");
  assert.ok(snapshot.includes("MARKET_BASED_LABEL"), "Market-Based label renders in the snapshot");
  assert.ok(snapshot.includes("metrics.financial"), "Financial RIP renders in the snapshot");
  assert.ok(
    snapshot.includes("ChaseAccessibilitySnapshotCard"),
    "Chase Accessibility renders in the snapshot",
  );
  assert.ok(snapshot.includes("metrics.collector"), "Collector Appeal renders in the snapshot");
});

test("B: Financial RIP and Chase Accessibility are grouped beneath the Market-Based container in the snapshot", () => {
  const source = ripPageSource();
  const groupStart = source.indexOf("data-market-based-summary-group");
  assert.ok(groupStart >= 0, "the Market-Based summary group must exist");
  const groupOpenTag = source.indexOf(">", source.indexOf("<div", groupStart - 40));
  // Find the matching close by locating the Collector ScoreSurface, which is
  // rendered as this group's sibling, not its child.
  const collectorIndex = source.indexOf("metric={metrics.collector}", groupStart);
  const financialInGroupIndex = source.indexOf("metric={metrics.financial}", groupStart);
  const chaseInGroupIndex = source.indexOf(
    "ChaseAccessibilitySnapshotCard",
    groupStart,
  );
  assert.ok(
    financialInGroupIndex > groupStart && financialInGroupIndex < collectorIndex,
    "Financial RIP renders before Collector Appeal, inside the Market-Based group",
  );
  assert.ok(
    chaseInGroupIndex > groupStart && chaseInGroupIndex < collectorIndex,
    "Chase Accessibility renders before Collector Appeal, inside the Market-Based group",
  );
});

test("C: Market-Based never fabricates its own score, rank, or tier", () => {
  const source = ripPageSource();
  assert.ok(
    !/marketBased\s*:\s*{[^}]*score\s*:/.test(source.replace(/\s+/g, " ")),
    "no marketBased score field is assembled in the page",
  );
  assert.ok(
    !source.includes("metrics.marketBased"),
    "Market-Based is never registered as a fourth scored metric card",
  );
  // The model itself must not compute a numeric score for the grouping.
  const model = buildRipDecisionModel({
    canonical: {
      overall: { relativeScore: 50, rank: 5, rankedSetCount: 10 },
      financialRip: { relativeScore: 70, rank: 3, rankedSetCount: 10 },
      collectorAppeal: { relativeScore: 60, rank: 4, rankedSetCount: 10 },
    },
    summary: {},
  });
  assert.equal(model.marketBased.score, undefined);
  assert.equal(model.marketBased.rank, undefined);
  assert.equal(model.marketBased.tier, undefined);
  assert.equal(model.chaseAccessibility.rank, null);
  assert.equal(model.chaseAccessibility.tier, null);
});

test("D: the Market-Based CTA targets the combined Market-Based breakdown, not two separate destinations", () => {
  const source = ripPageSource();
  assert.ok(source.includes('"View Market-Based breakdown"'));
  assert.ok(source.includes('scrollToSection("set-detail-market-based")'));
  assert.ok(source.includes('id="set-detail-market-based"'));
  // The old two-destination pattern (a bare Financial-only anchor) is gone.
  assert.ok(!source.includes('id="set-detail-financial-rip"'));
});

test("E: the Financial RIP six-component breakdown remains present, reused verbatim", () => {
  const marketBased = marketBasedSource();
  assert.ok(marketBased.includes("<FinancialRipV3Breakdown canonical={canonical}"));
  const source = ripPageSource();
  assert.ok(source.includes("<MarketBasedOpeningQualityBreakdown"));
  assert.ok(source.includes('depth="full"'));
});

test("F: the Chase Accessibility breakdown uses real public fields from the shared selector, never invented ones", () => {
  const marketBased = marketBasedSource();
  assert.ok(marketBased.includes("selectChaseAccessibilityPresentation"));
  for (const field of [
    "chase.displayAccessibility",
    "chase.chaseDepth",
    "chase.mappedHcMass",
  ]) {
    assert.ok(marketBased.includes(field), `${field} must be read from the shared selector`);
  }
  // No independent re-derivation of the raw metric anywhere in the container.
  assert.ok(!marketBased.includes("A_raw"));
  assert.ok(!marketBased.includes("saturating"));
});

test("G: no Chase Accessibility rank is ever fabricated", () => {
  const marketBased = marketBasedSource();
  assert.ok(marketBased.includes("chase.rank !== null"));
  // A missing rank is OMITTED entirely, never shown as an "unavailable" line
  // (that would incorrectly read as an error to users).
  assert.ok(!marketBased.includes("Cohort rank not yet available"));
  assert.ok(!/chase\.rank\s*=\s*(?!null)/.test(marketBased));
  const snapshotSource = ripPageSource();
  assert.ok(
    !snapshotSource.match(/ChaseAccessibilitySnapshotCard[\s\S]{0,600}rank/),
    "the Opening Snapshot's Chase Accessibility card never renders a rank",
  );
});

test("H: Top Chase / Chase Reality remains a separate, untouched section", () => {
  const source = ripPageSource();
  assert.ok(source.includes('data-rip-section="chase-reality"'));
  assert.ok(source.includes("function ChaseReality"));
  assert.ok(source.includes("chase={decision.topChase}"));
  // Top Chase must never be rendered through the Chase Accessibility contract.
  assert.ok(!source.includes("selectChaseAccessibilityPresentation"));
  assert.ok(
    !source.match(/function ChaseReality[\s\S]{0,2000}chaseAccessibility/i),
    "Top Chase must not read Chase Accessibility fields",
  );
});

// ---------------------------------------------------------------------------
// Set Analysis (PokemonSetAnalysisClient.jsx)
// ---------------------------------------------------------------------------

test("I: Set Analysis nav contains Market-Based instead of Financial RIP", () => {
  const source = analysisSource();
  assert.ok(source.includes('["market-based","Market-Based","shield"]'));
  assert.ok(!source.includes('["financial-rip","Financial RIP","shield"]'));
  const sectionsLine = source.match(/const SECTIONS = \[.*\];/)[0];
  assert.ok(!sectionsLine.includes("Financial RIP"), "the nav tab array itself must not carry a Financial RIP tab");
});

test("J: Set Analysis Overview uses the same Overall -> Market-Based -> Collector hierarchy as Set RIP", () => {
  const source = analysisSource();
  const overviewStart = source.indexOf('activeSection==="overview"');
  const overviewSection = source.slice(overviewStart, source.indexOf("</section>", overviewStart));
  assert.ok(overviewSection.includes('label="Overall RIP"'));
  assert.ok(overviewSection.includes("Market-Based Opening Quality"));
  assert.ok(overviewSection.includes('label="Financial RIP"'));
  assert.ok(overviewSection.includes("chaseAccessibility.label"));
  assert.ok(overviewSection.includes('label="Collector Appeal"'));
  assert.ok(
    overviewSection.includes(
      "The published Overall RIP, Market-Based Opening Quality, and Collector Appeal",
    ),
  );
});

test("K: Set Analysis Market-Based section contains Financial RIP and Chase Accessibility together", () => {
  const source = analysisSource();
  assert.ok(source.includes('activeSection==="market-based"'));
  assert.ok(source.includes("<MarketBasedOpeningQualityBreakdown canonical={canonical}"));
  assert.ok(!source.includes("<FinancialRipV3Breakdown"));
});

test("L: Collector Appeal remains its own separate section on Set Analysis", () => {
  const source = analysisSource();
  assert.ok(source.includes('activeSection==="collector-appeal"'));
  assert.ok(source.includes("<CollectorAppealBreakdown canonical={canonical}"));
});

test("M: Set RIP and Set Analysis share one Chase Accessibility implementation, not two", () => {
  const ripSource = ripPageSource();
  const analysis = analysisSource();
  assert.ok(ripSource.includes('from "./MarketBasedOpeningQualityBreakdown.jsx"'));
  assert.ok(
    analysis.includes(
      'from "@/components/explore/MarketBasedOpeningQualityBreakdown"',
    ),
  );
  // Neither surface defines its own independent Chase Accessibility rendering
  // component — both import the one shared container.
  assert.ok(!ripSource.includes("function ChaseAccessibilityFullPanel"));
  assert.ok(!analysis.includes("function ChaseAccessibilityFullPanel"));
});

// ---------------------------------------------------------------------------
// Global
// ---------------------------------------------------------------------------

test("N: no forbidden weight-disclosure strings in the touched files", () => {
  const forbidden = ["86%", "4.44%", "95.56%"];
  for (const filePath of [ripPagePath, analysisClientPath, marketBasedPath]) {
    const source = fs.readFileSync(filePath, "utf8");
    for (const token of forbidden) {
      assert.ok(!source.includes(token), `${token} must not appear in ${filePath}`);
    }
  }
  // "90%"/"10%"/"4%" are allowed ONLY as pull-rate/metric copy, never as an
  // "X% Financial + Y% Chase" style sentence.
  const ripSource = ripPageSource();
  assert.ok(!/\d+%\s*Financial\s*\+\s*\d+%\s*Chase/i.test(ripSource));
  assert.ok(!/\d+%\s*Market-Based\s*\+\s*\d+%\s*Collector/i.test(ripSource));
});

test("O: no client-side Overall/Chase/Market-Based scoring arithmetic is introduced", () => {
  for (const filePath of [ripPagePath, analysisClientPath, marketBasedPath]) {
    const source = fs
      .readFileSync(filePath, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");
    assert.ok(
      !/chaseAccessibility\.rawAccessibility\s*\*/.test(source),
      `${filePath} must not recompute the Chase Accessibility raw score`,
    );
    assert.ok(
      !/overall(Score)?\s*=\s*financial.*\*.*\+.*collector/i.test(source),
      `${filePath} must not recompute an Overall RIP weighted sum`,
    );
  }
});

test("P: a V10 historical fixture does not falsely claim Chase Accessibility was part of that score", () => {
  const explanation = selectOverallRipExplanationHierarchy({
    overall: { relativeScore: 70, rank: 2, rankedSetCount: 10 },
    financialRip: { relativeScore: 80, rank: 1, rankedSetCount: 10 },
    collectorAppeal: { relativeScore: 60, rank: 3, rankedSetCount: 10 },
  });
  assert.equal(explanation.version, "v10");
  assert.equal(explanation.marketBased, null);
  assert.equal(explanation.weights.chaseAccessibility, null);
  assert.ok(!explanation.headline.toLowerCase().includes("chase"));

  // The Chase Accessibility selector itself is also honest when no v11
  // contract block is present at all: it reports unavailable, not a
  // borrowed/fabricated value.
  const chase = selectChaseAccessibilityPresentation({
    overall: { relativeScore: 70 },
  });
  assert.equal(chase.available, false);
  assert.equal(chase.rawAccessibility, null);
});
