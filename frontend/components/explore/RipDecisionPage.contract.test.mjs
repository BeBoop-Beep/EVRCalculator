import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { buildRipDecisionModel } from "./ripDecisionModel.mjs";

const directory = path.dirname(new URL(import.meta.url).pathname.slice(1));
const pagePath = path.resolve(directory, "RipDecisionPage.jsx");
const cssPath = path.resolve(directory, "RipDecisionPage.module.css");
const evidencePath = path.resolve(directory, "RipStoryEvidence.jsx");

test("the page leads with the decision, not with the scoring model", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const renderStart = source.indexOf("return (", source.indexOf("export default function RipDecisionPage"));
  const rendered = source.slice(renderStart);
  // QUESTION -> ANSWER -> EVIDENCE -> why it scores that way. Product economics
  // and the chase precede every methodology section.
  const tokens = [
    'data-rip-section="decision"',
    "<ProductOpeningValue",
    "<ChaseReality",
    "<MaterialCards",
    'data-rip-section="simulation-evidence"',
    'data-rip-section="simulation-drivers"',
    'data-rip-section="why-it-ranks"',
    'data-rip-section="financial-explanation"',
    'data-rip-section="collector-explanation"',
    'data-rip-section="collector-drivers"',
  ];
  const positions = tokens.map((token) => rendered.indexOf(token));
  assert.ok(positions.every((position) => position >= 0), "every section must render");
  assert.deepEqual([...positions].sort((a, b) => a - b), positions);
});

test("the primary verdict and header binding use Set RIP V1, not the old pack rank", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const client = fs.readFileSync(path.resolve(directory, "RipStatisticsPageClient.jsx"), "utf8");
  assert.ok(source.includes('setRip = null'));
  assert.ok(source.includes('"Set RIP Rank"'));
  assert.ok(source.includes('data-set-rip-family-evidence'));
  assert.ok(!source.includes('"Booster Pack RIP Rank"'));
  assert.ok(client.includes("const activeSetRip = explorePayload?.setRipV1"));
  assert.ok(client.includes('<SetPageIcon name="trophy" />Set RIP'));
});

test("canonical product and chase sections bind to nested ripDecision data", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const selector = fs.readFileSync(path.resolve(directory, "ripDecisionContract.mjs"), "utf8");
  const product = fs.readFileSync(path.resolve(directory, "ProductOpeningValue.jsx"), "utf8");
  assert.ok(selector.includes("ripDecision?.sealedProducts?.products"));
  assert.ok(selector.includes("normalizeTopChase(ripDecision.topChase)"));
  for (const label of ["Overall RIP", "Financial RIP", "Collector Appeal", "Pack Count", "Product Family"]) {
    assert.ok(product.includes(`label: "${label}"`));
  }
  assert.ok(source.includes("chase={decision.topChase}"));
});

test("methodology never precedes the decision surface", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const renderStart = source.indexOf("return (", source.indexOf("export default function RipDecisionPage"));
  const rendered = source.slice(renderStart);
  for (const methodology of [
    'data-rip-section="financial-explanation"',
    'data-rip-section="collector-explanation"',
    'data-rip-section="why-it-ranks"',
  ]) {
    assert.ok(
      rendered.indexOf("<ProductOpeningValue") < rendered.indexOf(methodology),
      `${methodology} must come after product opening value`
    );
    assert.ok(
      rendered.indexOf("<ChaseReality") < rendered.indexOf(methodology),
      `${methodology} must come after the chase`
    );
  }
});

test("the deep dive is collapsed and accessible rather than deleted", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes("<FinancialRipV3Breakdown"), "existing component is reused, not rewritten");
  assert.ok(source.includes("<CollectorAppealBreakdown"), "existing component is reused, not rewritten");
  assert.ok(source.includes("financialDeepDiveOpen"));
  assert.ok(source.includes("collectorDeepDiveOpen"));
  assert.ok(source.includes('aria-controls="financial-rip-deep-dive"'));
  assert.ok(source.includes('aria-controls="collector-appeal-deep-dive"'));
  assert.ok(source.includes("aria-expanded={financialDeepDiveOpen}"));
  assert.ok(source.includes("aria-expanded={collectorDeepDiveOpen}"));
});

test("decision sections keep critical information visible and probabilistic", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes("50% modeled chance"));
  assert.ok(source.includes("90% modeled chance"));
  assert.ok(source.includes("not guaranteed outcomes"));
  assert.ok(source.includes('data-chase-state="unavailable"'));
  assert.ok(!source.includes("you will pull"));
  // Gross spend is spend, never an acquisition cost: each opened pack also
  // produces other cards.
  assert.ok(source.includes("gross pack spend"));
  assert.ok(!source.includes("Cost to acquire"));
  assert.ok(!source.includes("Expected cost"));
});

test("the primary decision layer uses break-even vocabulary, not valuation claims", () => {
  const product = fs.readFileSync(path.resolve(directory, "ProductOpeningValue.jsx"), "utf8");
  assert.ok(product.includes("Model Break-Even"));
  for (const forbidden of ["Buy Price", "Target Price", "Fair Value", "Guaranteed Value", "Recommended Price"]) {
    assert.ok(!product.includes(forbidden), `${forbidden} overstates what the model publishes`);
  }
});

test("no cross-format recommendation or ranking is introduced", () => {
  const product = fs.readFileSync(path.resolve(directory, "ProductOpeningValue.jsx"), "utf8");
  const selector = fs.readFileSync(path.resolve(directory, "ripDecisionContract.mjs"), "utf8");
  for (const forbidden of ["Best Product", "Best Buy", "Recommended", "Guaranteed profit", "Investment"]) {
    assert.ok(!product.includes(forbidden), `${forbidden} implies an unvalidated cross-format verdict`);
  }
  // Products are never reordered: the contract's order is the presentation order.
  assert.ok(!product.includes(".sort("), "product rows must not be sorted in the UI");
  assert.ok(!selector.includes(".sort("), "the selector must not rank products");
  assert.ok(product.includes("Above model break-even"), "edge is described economically");
});

test("score anatomy is compact and no longer the first thing on the page", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  for (const key of ["overall", "financial", "collector"]) assert.ok(source.includes(`key: "${key}"`));
  assert.equal((source.match(/label: "Overall RIP"/g) || []).length, 1);
  for (const cta of ["How Overall RIP works", "Explore Financial RIP", "Explore Collector Appeal"]) assert.ok(source.includes(cta));
  assert.ok(source.includes("prefers-reduced-motion: reduce"));
  assert.ok(source.includes("tabIndex={-1}"));
  assert.ok(source.includes("getRipTierPresentation(metric.tier"));
  assert.ok(source.includes("data-score-tier"));
  assert.ok(!source.includes('"--score-accent"'), "category accent does not style score surfaces");
  // The full-width hero anatomy (oversized Overall surface, "Built from"
  // connector, flanking product art) is gone from the first viewport.
  assert.ok(!source.includes("styles.anatomy"), "the giant anatomy diagram is retired");
  assert.ok(!source.includes("styles.connector"), "the 'Built from' connector is retired");
  assert.ok(source.includes("styles.compactScores"), "three scores render as one compact row");
});

test("Overall score hero accepts dynamic product context and degrades without art", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes('productType = "booster_pack"'));
  assert.ok(source.includes('productLabel = "Booster Pack"'));
  assert.ok(source.includes("productContext?.productImage"));
  assert.ok(source.includes("productImage.src || productContext.productImage"));
  assert.ok(!source.includes("Ascended Heroes"));
});

test("product art stays in-card on the compact score surfaces", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const css = fs.readFileSync(cssPath, "utf8");
  assert.ok(source.includes("productContext.productImage"), "compact in-card image remains dynamic");
  assert.match(css, /\.productArt \{ display: none;/);
  assert.match(css, /@media \(max-width:767px\)[\s\S]*\.productArt \{ display: block;/);
});

test("the break-even chart is readable without colour and never scrolls sideways", () => {
  const css = fs.readFileSync(cssPath, "utf8");
  const product = fs.readFileSync(path.resolve(directory, "ProductOpeningValue.jsx"), "utf8");
  // Position, sign, written percentage and a stated side all carry the meaning.
  assert.ok(product.includes('percent(edge, { signed: true })'), "the percentage is always written out");
  assert.ok(product.includes("edgeSideLabel"), "the side of break-even is stated in words");
  assert.ok(product.includes("sr-only"), "each row narrates itself");
  assert.ok(product.includes("data-direction"), "colour is a reinforcement hook, not the only channel");
  // A real zero-line element, so it survives forced-colours and print.
  assert.match(css, /\.breakEvenZero \{ position: absolute;[^}]*left: 50%;/);
  assert.match(css, /@media \(max-width:767px\)[\s\S]*\.breakEvenButton[^}]*grid-template-areas/);
  assert.ok(!css.includes("overflow-x: auto"));
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

test("Financial explanation mounts the canonical component, now after the evidence", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes("<FinancialRipV3Breakdown"));
  const renderStart = source.indexOf("return (", source.indexOf("export default function RipDecisionPage"));
  const rendered = source.slice(renderStart);
  assert.ok(
    rendered.indexOf('data-rip-section="simulation-evidence"') <
      rendered.indexOf('data-rip-section="financial-explanation"'),
    "methodology follows the evidence rather than leading the page"
  );
  assert.ok(!source.includes("Profit/Safety/Stability"));
  assert.ok(!source.includes("Weight "));
});

test("Chase Reality reads the canonical contract and never reconstructs odds", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  // The four published chase fields, read verbatim.
  for (const field of [
    "chase.currentMarketPrice",
    "chase.impliedOddsOneInN",
    "chase.packsFor50PercentChance",
    "chase.packsFor90PercentChance",
  ]) {
    assert.ok(source.includes(field), `${field} must come straight from ripDecision.topChase`);
  }
  assert.ok(source.includes("chase={decision.topChase}"), "the chase is the contract's chase");
  // EV contribution is rate x price and names a different card; it must never
  // be used to derive pull odds.
  assert.ok(!source.includes("ev_contribution"), "chase odds must not derive from EV contribution");
  assert.ok(!source.includes("Modeled Chase Odds Not Yet Available"), "the stale unavailable headline is gone");
});

test("the decision contract is normalized once and reaches the page as a prop", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const client = fs.readFileSync(path.resolve(directory, "RipStatisticsPageClient.jsx"), "utf8");
  assert.ok(source.includes("selectRipDecisionContract(ripDecision)"), "one normalization boundary");
  assert.ok(client.includes("ripDecision={explorePayload?.ripDecision"), "the snapshot field is actually passed");
  // No second fetch: the snapshot already carries the contract.
  assert.ok(!source.includes("fetch("), "the decision layer must not fetch per product or per card");
});

test("ripDecisionContract.mjs is the only decision parser on the RIP page surface", () => {
  // Scope note: Rankings (rankingsPresentation.mjs) reads its own chase paths
  // off the rankings row and is explicitly out of scope for this pass. This
  // guards the set-detail RIP page surface only.
  const surface = ["RipDecisionPage.jsx", "ProductOpeningValue.jsx", "ripDecisionModel.mjs"];
  const offenders = surface.filter((name) => {
    const source = fs
      .readFileSync(path.join(directory, name), "utf8")
      // Comments may name the contract; only real property access counts.
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");
    return /ripDecision\??\.(sealedProducts|topChase|currentRunAvailable|products)/.test(source);
  });
  assert.deepEqual(offenders, [], "decision parsing must not spread across components");
});

test("opening value renders three distinct unavailable states", () => {
  const product = fs.readFileSync(path.resolve(directory, "ProductOpeningValue.jsx"), "utf8");

  // Each state is separately addressable in the DOM and separately worded.
  assert.ok(product.includes("data-opening-value-state"), "the state is exposed for QA");
  for (const state of ["not-published", "no-current-run", "no-modeled-products"]) {
    assert.ok(product.includes(`"${state}"`), `${state} must be a distinct branch`);
  }
  assert.ok(product.includes("not published in this set's current snapshot"));
  assert.ok(product.includes("No current calculation run is available for this set"));
  assert.ok(product.includes("No currently modeled sealed products are available for this set"));

  // A current run with zero products must not be described as having no run.
  const noRunIndex = product.indexOf('decision?.available === false');
  const notPublishedIndex = product.indexOf("decision?.contractPresent === false");
  assert.ok(
    notPublishedIndex >= 0 && noRunIndex > notPublishedIndex,
    "an absent contract is checked before the run state"
  );
  // No branch reaches past the normalized contract for older rows.
  const code = product.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  for (const fallback of ["previousProducts", "lastKnown", "historicalProducts"]) {
    assert.ok(!code.includes(fallback), "unavailable states must not reach for historical rows");
  }
});

test("gross-spend pack price is never guessed across multiple loose-pack SKUs", () => {
  const selector = fs.readFileSync(path.resolve(directory, "ripDecisionContract.mjs"), "utf8");
  // Scope to the loose-pack function itself: Math.min/max are legitimate
  // elsewhere in this module (the break-even axis clamps to its domain).
  const start = selector.indexOf("export function selectLoosePackMarketPrice");
  assert.ok(start >= 0, "the loose-pack selector must exist");
  const body = selector.slice(start, selector.indexOf("\n}", start));

  assert.ok(body.includes("packs.length === 1"), "exactly one priced single-pack SKU, or no price");
  for (const policy of ["Math.min", "Math.max", "sort(", "reduce("]) {
    assert.ok(!body.includes(policy), `${policy} would be an undeclared loose-pack quote policy`);
  }
});

test("the secondary chase list excludes the canonical Top Chase", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(
    source.includes("selectMarketChaseCards(chaseCards, { excludeCard: decision.topChase })"),
    "Other Major Value Chases must not repeat the Top Chase"
  );
  assert.ok(!source.includes("model.decision"), "the obsolete decision model block is gone");
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
