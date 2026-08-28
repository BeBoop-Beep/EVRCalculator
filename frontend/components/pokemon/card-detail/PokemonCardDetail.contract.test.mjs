import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(
  path.join(
    process.cwd(),
    "components/pokemon/card-detail/PokemonCardDetailClient.jsx",
  ),
  "utf8",
);
const market = fs.readFileSync(
  path.join(
    process.cwd(),
    "components/pokemon/card-detail/AssetMarketPanel.jsx",
  ),
  "utf8",
);
const marketModel = fs.readFileSync(
  path.join(
    process.cwd(),
    "components/pokemon/card-detail/assetMarketModel.mjs",
  ),
  "utf8",
);
const canonicalMarketChart = fs.readFileSync(
  path.join(process.cwd(), "components/explore/MarketPriceHistoryChart.jsx"),
  "utf8",
);
const page = fs.readFileSync(
  path.join(
    process.cwd(),
    "app/TCGs/Pokemon/Sets/[setSlug]/Cards/[cardId]/page.js",
  ),
  "utf8",
);
const detailModel = fs.readFileSync(
  path.join(
    process.cwd(),
    "components/pokemon/card-detail/cardDetailModel.mjs",
  ),
  "utf8",
);
const styles = fs.readFileSync(
  path.join(process.cwd(), "app/styles/globals.css"),
  "utf8",
);

test("variant selection preserves canonical route and accessible radio state", () => {
  assert.match(
    source,
    /getPokemonCardDetail\([\s\S]*?detail\.set\.id,[\s\S]*?detail\.card\.id,[\s\S]*?variantId/,
  );
  assert.match(source, /buildPokemonCardDetailHref\([\s\S]*?cardVariantId: variantId/);
  assert.match(source, /role="radiogroup"/);
  assert.match(source, /aria-checked=/);
});

test("unsupported cards retain public market identity with precise pull-model status", () => {
  assert.match(source, /not_pullable_by_current_model/);
  assert.match(source, /legacy_run_variant_detail_unavailable/);
  assert.match(source, /pull_model_configuration_missing/);
  assert.doesNotMatch(source, /· Not modeled/);
  assert.match(source, /Card artwork unavailable/);
  assert.match(source, /onError=\{\(\) => setFailed\(true\)\}/);
  assert.match(source, /hasIndexPlusAccess\(user\?\.index_plan\)/);
  assert.doesNotMatch(source, /plan\s*===\s*["']plus["']/);
});

test("identity is rarity plus number and excludes subtype metadata", () => {
  assert.match(
    source,
    /detail\.card\.rarity,[\s\S]*?detail\.card\.printedNumber \|\| detail\.card\.cardNumber/,
  );
  assert.doesNotMatch(source, /subtypes\?\.join|detail\.card\.subtypes/);
});

test("market shell exposes raw, disabled graded, canonical windows, chart and truthful fallback", () => {
  for (const label of [
    "Raw",
    "Graded · Coming Soon",
    "Showing history since tracking began",
  ])
    assert.ok(market.includes(label), `missing ${label}`);
  for (const label of ["1D", "7D", "30D", "3M", "6M", "1Y", "ALL"])
    assert.ok(marketModel.includes(label), `missing ${label}`);
  assert.match(
    market,
    /title="Graded market data is coming soon"[\s\S]*?disabled|disabled[\s\S]*?title="Graded market data is coming soon"/,
  );
  assert.match(market, /MarketWindowSelector/);
  assert.match(market, /MarketPriceHistoryChart/);
  assert.match(market, /data-market-coverage-status/);
  assert.match(market, /data-partial=/);
  assert.doesNotMatch(market, /text-4xl|sm:text-5xl/);
  assert.match(market, /<MarketValueChange[\s\S]*?value=\{market\?\.currentPrice\}/);
  assert.match(canonicalMarketChart, /ChartFrame/);
  assert.match(canonicalMarketChart, /MarketTrendTooltipCard/);
  assert.match(canonicalMarketChart, /POSITIVE_VALUE_COLOR/);
  assert.match(canonicalMarketChart, /NEGATIVE_VALUE_COLOR/);
  assert.doesNotMatch(market, /PSA|BGS|CGC/);
});

test("journey and product economics use canonical fields with recovery disclosure", () => {
  assert.match(detailModel, /Object\.freeze\(\[0\.5, 0\.75, 0\.9, 0\.95\]\)/);
  for (const label of [
    "Choose How You Open It",
    "Gross Chase Spend",
    "Recovery-adjusted Cost",
  ])
    assert.ok(source.includes(label), `missing ${label}`);
  assert.match(
    source,
    /Fees, shipping, condition discounts,[\s\S]*?liquidity,[\s\S]*?sell-through/i,
  );
  assert.doesNotMatch(
    source,
    /Overall RIP|Financial RIP|Collector Appeal|RIP Tier/,
  );
});

test("probability journey renders its canonical curve and all milestone markers", () => {
  assert.match(source, /chase\.modeledProbability/);
  assert.match(source, /cumulativePullProbability\(probability, packs\)/);
  assert.match(source, /data-probability-journey-chart/);
  assert.match(source, /data-probability-curve/);
  assert.match(source, /data-probability-marker=/);
  assert.match(detailModel, /Object\.freeze\(\[0\.5, 0\.75, 0\.9, 0\.95\]\)/);
  assert.doesNotMatch(source, /<title[\s>]/);
  assert.match(
    source,
    /aria-label="Cumulative pull probability by packs opened"/,
  );
  assert.match(source, /data-probability-milestone-rail/);
  assert.doesNotMatch(source, /label=\{`\$\{label\} Chance to Pull`\}/);
  assert.match(source, /custom|role="status"/);
});

test("card detail shares the dynamic set atmosphere and establishes its stacking context", () => {
  assert.match(
    source,
    /optimizedImageUrl\([\s\S]*?detail\.set\.heroImageUrl[\s\S]*?detail\.set\.logoImageUrl[\s\S]*?detail\.set\.symbolImageUrl[\s\S]*?SET_LOGO_WIDTH/,
  );
  assert.match(source, /<PageArtworkAtmosphere[\s\S]*?src=\{artwork\}/);
  assert.match(source, /relative isolate/);
  assert.doesNotMatch(source, /Ascended Heroes.*artwork|Black Bolt.*artwork/);
});

test("normal card-detail interactions use Market teal while the lock remains amber", () => {
  assert.match(
    styles,
    /\.card-detail-environment[\s\S]*--accent: rgb\(45, 212, 191\)/,
  );
  assert.match(source, /text-amber-300/);
  assert.match(source, /border-amber-300\/40/);
});

test("product choices use compact labels, scalable desktop navigation, and a mobile select", () => {
  assert.match(source, /product\.productName[\s\S]*?\|\|[\s\S]*?product\.productFamilyLabel/);
  assert.match(
    source,
    /md:grid-cols-\[minmax\(15rem,19rem\)_minmax\(0,1fr\)\]/,
  );
  assert.match(source, /<select[\s\S]*?id="product-select"/);
  assert.match(source, /max-h-\[22rem\].*overflow-y-auto/);
  assert.match(
    source,
    /selected\.sealedProductId === product\.sealedProductId/,
  );
});

test("collector hierarchy keeps actual scores and honest unavailable scarcity", () => {
  assert.match(source, /primary\s*\/>/);
  assert.match(source, /intelligence\?\.cardAppeal/);
  assert.match(source, /intelligence\?\.pokemonDemand/);
  assert.match(source, /intelligence\?\.treatmentPrestige/);
  assert.match(source, /intelligence\?\.scarcity/);
  assert.match(source, /"Unavailable"/);
  assert.doesNotMatch(source, /0 \/ 10/);
  assert.match(source, /<InfoPopover text=\{info\}/);
  assert.match(source, /How much extra value does the market give a card just because of its treatment, once we remove the effects of Pokémon popularity and rarity\/pull odds\?/);
  assert.doesNotMatch(source, /Scale: SIR 9\.6/);
  for (const label of [
    "Card Appeal",
    "Pokémon Demand",
    "Card Treatment",
    "Scarcity",
  ])
    assert.ok(source.includes(`label="${label}"`));
});

test("product economics use the shared supported-first display price rule", () => {
  assert.match(source, /productDisplayPrice\(selected\)/);
  assert.doesNotMatch(source, /selected\.productMarketCost/);
});

test("canonical metadata excludes variant query", () => {
  assert.match(
    page,
    /const path = `\/TCGs\/Pokemon\/Sets\/\$\{encodeURIComponent\(detail\.set\.slug\)\}\/Cards\/\$\{encodeURIComponent\(detail\.card\.id\)\}`/,
  );
  assert.doesNotMatch(page, /path.*variant/);
  assert.match(page, /notFound\(\)/);
  assert.match(page, / — /);
  assert.doesNotMatch(page, /Ã|â€|Â/);
});

test("top and bottom set navigation use the canonical bare set href", () => {
  assert.match(source, /const setHref = buildCardParentSetHref\(detail\.set\)/);
  assert.match(source, /← Back to \{detail\.set\.name\}/);
  assert.doesNotMatch(source, /Back to \{detail\.set\.name\} Cards/);
  assert.doesNotMatch(source, /detail\.set\.targetId/);
  assert.match(source, /Explore more cards from \{detail\.set\.name\}/);
  assert.doesNotMatch(detailModel, /\?tab=cards/);
});

test("hero centers identity above bottom-aligned artwork without a details panel", () => {
  assert.match(source, /md:grid-rows-\[auto_minmax\(0,1fr\)\]/);
  assert.match(source, /data-card-identity className="text-center"/);
  assert.match(source, /Market Price As Of \{dateLabel\(detail\.market\.marketDate\)\}/);
  assert.match(source, /card-detail-artwork/);
  assert.match(source, /md:items-end/);
  assert.match(source, /max-w-\[430px\]/);
  assert.match(source, /data-card-market-panel className="h-full"/);
  assert.doesNotMatch(source, /lg:-ml-6/);
  assert.doesNotMatch(source, /data-card-details-panel|Card Details/);
  assert.match(source, /data-card-market-panel/);
  assert.doesNotMatch(source, /max-h-\[46vh\]/);
  const heroEnd = source.indexOf("</section>", source.indexOf("data-card-detail-hero"));
  const identityStart = source.indexOf("data-card-identity");
  const variantCall = source.indexOf("<VariantSelector", identityStart);
  const intelligenceCall = source.indexOf("<ChaseEfficiencySection", variantCall);
  assert.ok(identityStart < heroEnd && heroEnd < variantCall && variantCall < intelligenceCall);
});

test("market-only variants are selectable while pull modeling remains explicit", () => {
  assert.doesNotMatch(source, /disabled=\{!variant\.modeled/);
  assert.match(source, /pullStatusLabel\(variant\.pullModelStatus\)/);
});

test("Premium pull intelligence and standalone Plus products branch independently", () => {
  assert.match(source, /data-pull-profile/);
  assert.match(source, /data-pull-analytics-status/);
  assert.match(source, /pullStatusExplanation\(detail\.chase\?\.reason\)/);
  assert.match(source, /<ProductEconomics[\s\S]*?chase=\{chase\}[\s\S]*?pullAnalyticsAvailable=\{pullAnalyticsAvailable\}/);
  assert.match(source, /<OpeningProductsSection detail=\{detail\}/);
  assert.doesNotMatch(source, /Card Intelligence|CardIntelligence/);
  assert.doesNotMatch(source, /if \(!chase\.available\)[\s\S]*?return/);
  for (const status of [
    "legacy_run_variant_detail_unavailable",
    "not_pullable_by_current_model",
    "pull_model_configuration_missing",
    "insufficient_observed_pulls",
  ]) assert.ok(source.includes(status), `missing ${status}`);
});
