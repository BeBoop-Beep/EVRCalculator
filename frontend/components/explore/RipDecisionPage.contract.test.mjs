import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { buildRipDecisionModel } from "./ripDecisionModel.mjs";

const directory = path.dirname(new URL(import.meta.url).pathname.slice(1));
const pagePath = path.resolve(directory, "RipDecisionPage.jsx");
const cssPath = path.resolve(directory, "RipDecisionPage.module.css");
const evidencePath = path.resolve(directory, "RipStoryEvidence.jsx");

test("the primary page is now five sections: hero, compare, chase (merged with desirability), why it ranks, simulation — then one Deep Dive", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const renderStart = source.indexOf(
    "return (",
    source.indexOf("export default function RipDecisionPage"),
  );
  const rendered = source.slice(renderStart);
  const tokens = [
    'data-rip-section="hero-recommendation"',
    'data-rip-section="compare-products"',
    'data-rip-section="chase-summary"',
    'data-rip-section="why-it-ranks"',
    'data-rip-section="simulation-evidence"',
    'data-rip-section="deep-dive"',
    "<EvContributionSection",
    "<ProductOpeningValue",
    'data-rip-section="financial-explanation"',
    'data-rip-section="collector-explanation"',
  ];
  const positions = tokens.map((token) => rendered.indexOf(token));
  assert.ok(
    positions.every((position) => position >= 0),
    "every section must render",
  );
  assert.deepEqual(
    [...positions].sort((a, b) => a - b),
    positions,
  );
});

test("Opening Snapshot no longer renders — it duplicated Simulation Evidence", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.equal(source.includes('data-rip-section="opening-snapshot"'), false);
  assert.equal(source.includes(">Opening Snapshot<"), false);
  assert.equal(
    source.includes("spectrumSteps"),
    false,
    "the spectrum computation was removed with its only consumer",
  );
});

test("Most Desirable Pokémon is merged into What Are You Chasing, not a separate top-level section", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.equal(
    source.includes('data-rip-section="desirable-pokemon"'),
    false,
    "no separate top-level section",
  );
  const chaseStart = source.indexOf('data-rip-section="chase-summary"');
  const chaseArticleEnd = source.indexOf("</article>", chaseStart);
  const subjectsIndex = source.indexOf("<CollectorDriverSubjects", chaseStart);
  assert.ok(
    chaseStart >= 0 &&
      subjectsIndex > chaseStart &&
      subjectsIndex < chaseArticleEnd,
    "Most Desirable Pokémon renders inside the same <article> as Top Chase",
  );
});

test("Other Major Value Chases was deleted, not just unmounted", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.equal(
    source.includes("MaterialCards"),
    false,
    "the component and its usage are both gone",
  );
  assert.equal(source.includes("Other Major Value Chases"), false);
  assert.equal(
    source.includes("selectMarketChaseCards"),
    false,
    "its only data selector is unused now",
  );
});

test("methodology never precedes the decision surface, and EV contribution / break-even / Set RIP construction all live inside Deep Dive, collapsed", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const renderStart = source.indexOf(
    "return (",
    source.indexOf("export default function RipDecisionPage"),
  );
  const rendered = source.slice(renderStart);
  const heroIndex = rendered.indexOf('data-rip-section="hero-recommendation"');
  const compareIndex = rendered.indexOf('data-rip-section="compare-products"');
  const chaseIndex = rendered.indexOf('data-rip-section="chase-summary"');
  const whyIndex = rendered.indexOf('data-rip-section="why-it-ranks"');
  const simIndex = rendered.indexOf('data-rip-section="simulation-evidence"');
  const deepDiveIndex = rendered.indexOf('data-rip-section="deep-dive"');
  for (const methodology of [
    'data-rip-section="financial-explanation"',
    'data-rip-section="collector-explanation"',
    "<EvContributionSection",
    "<ProductOpeningValue",
    "deep-dive-set-rip-breakdown",
  ]) {
    const methodologyIndex = rendered.indexOf(methodology);
    assert.ok(
      heroIndex < methodologyIndex,
      `${methodology} must come after the hero recommendation`,
    );
    assert.ok(
      compareIndex < methodologyIndex,
      `${methodology} must come after the product comparison`,
    );
    assert.ok(
      chaseIndex < methodologyIndex,
      `${methodology} must come after the chase`,
    );
    assert.ok(
      whyIndex < methodologyIndex,
      `${methodology} must come after Why It Ranks`,
    );
    assert.ok(
      simIndex < methodologyIndex,
      `${methodology} must come after Simulation Evidence`,
    );
    assert.ok(
      deepDiveIndex < methodologyIndex,
      `${methodology} must render inside Deep Dive`,
    );
  }
  // EV contribution and break-even are now DeepDiveRow children (collapsed
  // disclosures), not their own primary-flow <article> sections.
  assert.equal(
    rendered.includes(
      'data-rip-section="ev-contribution" className={`${styles.panel}',
    ),
    false,
    "EV contribution is no longer its own top-level panel",
  );
  assert.equal(
    rendered.includes('data-rip-section="break-even"'),
    false,
    "break-even is no longer its own top-level section id",
  );
  assert.ok(
    source.includes("<EvContributionSection rankings={rankings} bare />"),
    "EV contribution renders in bare mode inside a DeepDiveRow",
  );
});

test("the deep dive is collapsed and accessible rather than deleted", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(
    source.includes("<FinancialRipV3Breakdown"),
    "existing component is reused, not rewritten",
  );
  assert.ok(
    source.includes("<CollectorAppealBreakdown"),
    "existing component is reused, not rewritten",
  );
  assert.ok(source.includes("financialDeepDiveOpen"));
  assert.ok(source.includes("collectorDeepDiveOpen"));
  assert.ok(source.includes('id="deep-dive-financial-rip"'));
  assert.ok(source.includes('id="deep-dive-collector-appeal"'));
  assert.ok(source.includes("defaultOpen={financialDeepDiveOpen}"));
  assert.ok(source.includes("defaultOpen={collectorDeepDiveOpen}"));
  assert.ok(
    source.includes("function DeepDiveRow"),
    "deep dive rows share one collapsible primitive",
  );
  assert.ok(
    source.includes("aria-expanded={open}") &&
      source.includes("aria-controls={panelId}"),
    "every deep dive row is independently disclosure-accessible",
  );
});

test("decision sections keep critical information visible and probabilistic", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes("50/50 Chance to Pull One"));
  assert.ok(source.includes("90% Chance to Pull One"));
  assert.ok(source.includes("It is not guaranteed"));
  assert.equal(source.includes(">Gross Pack Spend<"), false);
  assert.ok(source.includes("not a guaranteed acquisition cost"));
  assert.ok(source.includes('data-chase-state="unavailable"'));
  assert.ok(!source.includes("you will pull"));
  assert.ok(!source.includes("Cost to acquire"));
  assert.ok(!source.includes("Expected cost"));
});

test("the primary decision layer uses break-even vocabulary, not valuation claims", () => {
  const product = fs.readFileSync(
    path.resolve(directory, "ProductOpeningValue.jsx"),
    "utf8",
  );
  assert.ok(product.includes("Model Break-Even"));
  for (const forbidden of [
    "Buy Price",
    "Target Price",
    "Fair Value",
    "Guaranteed Value",
    "Recommended Price",
  ]) {
    assert.ok(
      !product.includes(forbidden),
      `${forbidden} overstates what the model publishes`,
    );
  }
});

test("no cross-format recommendation or ranking is introduced", () => {
  const product = fs.readFileSync(
    path.resolve(directory, "ProductOpeningValue.jsx"),
    "utf8",
  );
  const selector = fs.readFileSync(
    path.resolve(directory, "ripDecisionContract.mjs"),
    "utf8",
  );
  for (const forbidden of [
    "Best Product",
    "Best Buy",
    "Recommended",
    "Guaranteed profit",
    "Investment",
  ]) {
    assert.ok(
      !product.includes(forbidden),
      `${forbidden} implies an unvalidated cross-format verdict`,
    );
  }
  // Products are never reordered: the contract's order is the presentation order.
  assert.ok(
    !product.includes(".sort("),
    "product rows must not be sorted in the UI",
  );
  assert.ok(
    !selector.includes(".sort("),
    "the selector must not rank products",
  );
  assert.ok(
    product.includes("Above model break-even"),
    "edge is described economically",
  );
});

test("score anatomy is compact and no longer the first thing on the page", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  for (const key of ["overall", "financial", "collector"])
    assert.ok(source.includes(`key: "${key}"`));
  assert.equal((source.match(/label: "Overall RIP"/g) || []).length, 1);
  for (const cta of [
    "How Overall RIP works",
    "Explore Financial RIP",
    "Explore Collector Appeal",
  ])
    assert.ok(source.includes(cta));
  assert.ok(source.includes("prefers-reduced-motion: reduce"));
  assert.ok(source.includes("tabIndex={-1}"));
  assert.ok(source.includes("getRipTierPresentation(metric.tier"));
  assert.ok(source.includes("data-score-tier"));
  assert.ok(
    !source.includes('"--score-accent"'),
    "category accent does not style score surfaces",
  );
  // The full-width hero anatomy (oversized Overall surface, "Built from"
  // connector, flanking product art) is gone from the first viewport.
  assert.ok(
    !source.includes("styles.anatomy"),
    "the giant anatomy diagram is retired",
  );
  assert.ok(
    !source.includes("styles.connector"),
    "the 'Built from' connector is retired",
  );
  assert.ok(
    source.includes("styles.compactScores"),
    "three scores render as one compact row",
  );
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
  assert.ok(
    source.includes("productContext.productImage"),
    "compact in-card image remains dynamic",
  );
  assert.match(css, /\.productArt \{ display: none;/);
  assert.match(
    css,
    /@media \(max-width:767px\)[\s\S]*\.productArt \{ display: block;/,
  );
});

test("the break-even chart is readable without colour and never scrolls sideways", () => {
  const css = fs.readFileSync(cssPath, "utf8");
  const product = fs.readFileSync(
    path.resolve(directory, "ProductOpeningValue.jsx"),
    "utf8",
  );
  // Position, sign, written percentage and a stated side all carry the meaning.
  assert.ok(
    product.includes("percent(edge, { signed: true })"),
    "the percentage is always written out",
  );
  assert.ok(
    product.includes("edgeSideLabel"),
    "the side of break-even is stated in words",
  );
  assert.ok(product.includes("sr-only"), "each row narrates itself");
  assert.ok(
    product.includes("data-direction"),
    "colour is a reinforcement hook, not the only channel",
  );
  // A real zero-line element, so it survives forced-colours and print.
  assert.match(css, /\.breakEvenZero \{ position: absolute;[^}]*left: 50%;/);
  assert.match(
    css,
    /@media \(max-width:767px\)[\s\S]*\.breakEvenButton[^}]*grid-template-areas/,
  );
  assert.ok(!css.includes("overflow-x: auto"));
});

test("canonical public scores preserve zero and never fall back to legacy summary values", () => {
  const model = buildRipDecisionModel({
    canonical: {
      overall: {
        relativeScore: 0,
        absoluteScore: 4,
        rank: 22,
        rankedSetCount: 22,
      },
      financialRip: {
        relativeScore: 80,
        absoluteScore: 42,
        rank: 4,
        rankedSetCount: 22,
      },
      collectorAppeal: {
        relativeScore: 88,
        absoluteScore: 67,
        rank: 2,
        rankedSetCount: 22,
      },
    },
    summary: { rip: { score: 99 }, ripCore: { score: 99 } },
  });
  assert.equal(model.overall.publicScore, 0);
  assert.equal(model.financial.publicScore, 80);
  assert.equal(model.collector.publicScore, 88);
  assert.equal(
    buildRipDecisionModel({
      canonical: { overall: {}, financialRip: {}, collectorAppeal: {} },
    }).overall.publicScore,
    null,
  );
});

test("Financial explanation mounts the canonical component, now after the evidence", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes("<FinancialRipV3Breakdown"));
  const renderStart = source.indexOf(
    "return (",
    source.indexOf("export default function RipDecisionPage"),
  );
  const rendered = source.slice(renderStart);
  assert.ok(
    rendered.indexOf('data-rip-section="simulation-evidence"') <
      rendered.indexOf('data-rip-section="financial-explanation"'),
    "methodology follows the evidence rather than leading the page",
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
    assert.ok(
      source.includes(field),
      `${field} must come straight from ripDecision.topChase`,
    );
  }
  assert.ok(
    source.includes("chase={decision.topChase}"),
    "the chase is the contract's chase",
  );
  // EV contribution is rate x price and names a different card; it must never
  // be used to derive pull odds.
  assert.ok(
    !source.includes("ev_contribution"),
    "chase odds must not derive from EV contribution",
  );
  assert.ok(
    !source.includes("Modeled Chase Odds Not Yet Available"),
    "the stale unavailable headline is gone",
  );
});

test("the decision contract is normalized once and reaches the page as a prop", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const client = fs.readFileSync(
    path.resolve(directory, "RipStatisticsPageClient.jsx"),
    "utf8",
  );
  assert.ok(
    source.includes("selectRipDecisionContract(ripDecision)"),
    "one normalization boundary",
  );
  assert.ok(
    client.includes("ripDecision={explorePayload?.ripDecision"),
    "the snapshot field is actually passed",
  );
  // No second fetch: the snapshot already carries the contract.
  assert.ok(
    !source.includes("fetch("),
    "the decision layer must not fetch per product or per card",
  );
});

test("ripDecisionContract.mjs is the only decision parser on the RIP page surface", () => {
  // Scope note: Rankings (rankingsPresentation.mjs) reads its own chase paths
  // off the rankings row and is explicitly out of scope for this pass. This
  // guards the set-detail RIP page surface only.
  const surface = [
    "RipDecisionPage.jsx",
    "ProductOpeningValue.jsx",
    "ripDecisionModel.mjs",
  ];
  const offenders = surface.filter((name) => {
    const source = fs
      .readFileSync(path.join(directory, name), "utf8")
      // Comments may name the contract; only real property access counts.
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");
    return /ripDecision\??\.(sealedProducts|topChase|currentRunAvailable|products)/.test(
      source,
    );
  });
  assert.deepEqual(
    offenders,
    [],
    "decision parsing must not spread across components",
  );
});

test("opening value renders three distinct unavailable states", () => {
  const product = fs.readFileSync(
    path.resolve(directory, "ProductOpeningValue.jsx"),
    "utf8",
  );

  // Each state is separately addressable in the DOM and separately worded.
  assert.ok(
    product.includes("data-opening-value-state"),
    "the state is exposed for QA",
  );
  for (const state of [
    "not-published",
    "no-current-run",
    "no-modeled-products",
  ]) {
    assert.ok(
      product.includes(`"${state}"`),
      `${state} must be a distinct branch`,
    );
  }
  assert.ok(product.includes("not published in this set's current snapshot"));
  assert.ok(
    product.includes("No current calculation run is available for this set"),
  );
  assert.ok(
    product.includes(
      "No currently modeled sealed products are available for this set",
    ),
  );

  // A current run with zero products must not be described as having no run.
  const noRunIndex = product.indexOf("decision?.available === false");
  const notPublishedIndex = product.indexOf(
    "decision?.contractPresent === false",
  );
  assert.ok(
    notPublishedIndex >= 0 && noRunIndex > notPublishedIndex,
    "an absent contract is checked before the run state",
  );
  // No branch reaches past the normalized contract for older rows.
  const code = product
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");
  for (const fallback of [
    "previousProducts",
    "lastKnown",
    "historicalProducts",
  ]) {
    assert.ok(
      !code.includes(fallback),
      "unavailable states must not reach for historical rows",
    );
  }
});

test("gross-spend pack price is never guessed across multiple loose-pack SKUs", () => {
  const selector = fs.readFileSync(
    path.resolve(directory, "ripDecisionContract.mjs"),
    "utf8",
  );
  // Scope to the loose-pack function itself: Math.min/max are legitimate
  // elsewhere in this module (the break-even axis clamps to its domain).
  const start = selector.indexOf("export function selectLoosePackMarketPrice");
  assert.ok(start >= 0, "the loose-pack selector must exist");
  const body = selector.slice(start, selector.indexOf("\n}", start));

  assert.ok(
    body.includes("packs.length === 1"),
    "exactly one priced single-pack SKU, or no price",
  );
  for (const policy of ["Math.min", "Math.max", "sort(", "reduce("]) {
    assert.ok(
      !body.includes(policy),
      `${policy} would be an undeclared loose-pack quote policy`,
    );
  }
});

test("the removed secondary chase list leaves no dangling selector, and the obsolete decision model block stays gone", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  // The market-value "other chases" list this selector fed was deleted
  // (see the "Other Major Value Chases was deleted" test); its selector
  // must not linger unused.
  assert.equal(source.includes("selectMarketChaseCards"), false);
  assert.ok(
    !source.includes("model.decision"),
    "the obsolete decision model block is gone",
  );
});

test("simulation reuses one distribution chart and existing top-hit evidence", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const evidence = fs.readFileSync(evidencePath, "utf8");
  assert.equal((source.match(/<RipDistributionChart/g) || []).length, 1);
  for (const label of [
    "Expected Value",
    "Typical Opening",
    "Chance to Beat Cost",
    "Strong Upside",
    "Jackpot Upside",
  ])
    assert.ok(source.includes(label));
  assert.ok(
    source.includes("rankings={rankings}"),
    "published rarity contribution remains available in Deep Dive",
  );
  assert.ok(evidence.includes("driver.ev_contribution"));
  assert.ok(evidence.includes("driver.current_near_mint_price"));
  assert.ok(source.includes("<SimulationFullReport"));
  assert.ok(evidence.includes("View value structure details"));
});

test("Collector story keeps the two scored factors and omits the research-only Dual-Path diagnostic", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes("<CollectorAppealBreakdown"));
  assert.ok(source.includes("selectCollectorRankDrivers"));
  assert.ok(source.includes("collectorDrivers"));
  assert.equal(source.includes("Additional collector diagnostics"), false);
  assert.equal(source.includes("Dual-Path Depth"), false);
  assert.equal(source.includes("selectCollectorDiagnostic"), false);
  assert.ok(source.includes("What Are You Chasing?"));
  assert.ok(source.includes("View all modeled pull rates"));
  const evidence = fs.readFileSync(evidencePath, "utf8");
  assert.ok(evidence.includes("Set Demand"));
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
  assert.match(
    css,
    /\.page > \.panel:not\(:first-child\)[^}]*background:\s*transparent/,
  );
  assert.match(
    css,
    /\.scoreSurface[^}]*border:/,
    "score cards remain bounded objects",
  );
  assert.match(
    css,
    /\.driverCard[^}]*border:/,
    "driver cards remain bounded objects",
  );
});

test("mobile analytical rows and collector subjects use compact disclosures", () => {
  const rowSource = fs.readFileSync(
    path.resolve(directory, "RipMetricDisclosureRow.jsx"),
    "utf8",
  );
  const evidence = fs.readFileSync(evidencePath, "utf8");
  const chart = fs.readFileSync(
    path.resolve(directory, "RipDistributionChart.jsx"),
    "utf8",
  );
  assert.ok(rowSource.includes("data-rip-metric-interpretation"));
  assert.ok(rowSource.includes("aria-expanded={isOpen}"));
  assert.ok(rowSource.includes("aria-controls={panelId}"));
  assert.ok(evidence.includes("subjectMobileList"));
  assert.ok(
    evidence.includes(
      "representative = subject.elitePath || subject.accessiblePath",
    ),
  );
  assert.ok(evidence.includes('<SubjectPath label="Elite chase"'));
  assert.ok(evidence.includes('<SubjectPath label="More attainable"'));
  assert.ok(chart.includes("data-mobile-chart-layout"));
  assert.ok(chart.includes("compact={isMobile}"));
});
