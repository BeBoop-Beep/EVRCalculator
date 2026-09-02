import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const page = read("../../../app/sealed-products/[productId]/page.js");
const client = read("./SealedProductDetailClient.jsx");
const market = read("./SealedProductMarketPanel.jsx");
const rip = read("./ProductRipSection.jsx");
const comparisons = read("./ProductComparisonSection.jsx");
const sharedScoreSurface = read("../../explore/RipScoreSurface.jsx");
const setRip = read("../../explore/RipDecisionPage.jsx");
const cardDetail = read("../card-detail/PokemonCardDetailClient.jsx");
const chaseArticle = read(
  "../../../app/Articles/how-chase-efficiency-works/page.js",
);

test("route stays thin, real, canonical, and has availability-aware SEO", () => {
  assert.match(page, /getSealedProductDetailServer/);
  assert.match(page, /SealedProductDetailClient/);
  assert.doesNotMatch(page, /marketDataLoader|MarketModule/);
  assert.match(page, /RIP & Market Analysis \| inDex/);
  assert.match(page, /detail\.rip\.available/);
  assert.match(page, /buildSealedProductHref/);
});

test("hero mirrors current Card Detail atmosphere, navigation, and image states", () => {
  assert.match(client, /PageArtworkAtmosphere/);
  assert.match(client, /data-product-set-ambient-artwork/);
  assert.match(client, /max-w-\[1600px\]/);
  assert.match(client, /max-w-\[1400px\]/);
  assert.match(client, /buildProductParentSetHref/);
  assert.match(client, /← Back to/);
  assert.match(client, /data-product-image/);
  assert.match(client, /data-product-image-placeholder/);
  assert.match(client, /Product image unavailable/);
  assert.match(client, /detail\.product\.name/);
});

test("sealed market is public, has all approved windows, and no card mode toggle", () => {
  assert.ok(
    client.indexOf("SealedProductMarketPanel") <
      client.indexOf("detail.rip.available ?"),
  );
  for (const token of ["1D", "7D", "30D", "3M", "6M", "1Y", "lifetime"])
    assert.match(read("./productDetailModel.mjs"), new RegExp(`"${token}"`));
  assert.doesNotMatch(market, /Raw|Graded|Asset mode/);
  assert.match(market, /Price history is not available for this product yet/);
  assert.match(market, /sealed market price/);
});

test("Product RIP uses Plus entitlement and only leader-normalized ranking fields", () => {
  assert.match(client, /hasIndexPlusAccess\(user\?\.index_plan\)/);
  assert.match(client, /entitled \? <><ProductRipSection/);
  assert.match(rip, /rip\.overallRipLeaderScore/);
  assert.match(rip, /rip\.financialRipLeaderScore/);
  assert.match(rip, /rip\.publicTier/);
  assert.match(rip, /rip\.familyRank/);
  assert.match(rip, /rip\.familySize/);
  assert.match(rip, /formatPublicRipScore/);
  assert.doesNotMatch(rip, /of 138|Overall Rank|overallRipAbsoluteScore/);
  assert.match(rip, /data-product-rip-score/);
  assert.match(rip, /Overall RIP = 90% Financial RIP \+ 10% Collector Appeal/);
  assert.match(rip, /publicLeaderScoreTier\(rip\.financialRipLeaderScore\)/);
  assert.match(rip, /const collectorTier = rip\.collectorAppealTier/);
  assert.doesNotMatch(
    rip,
    /publicLeaderScoreTier\(rip\.collectorAppealScore\)/,
  );
  assert.equal((rip.match(/Format Rank/g) || []).length, 1);
  assert.match(rip, /RipScoreSurface/);
  assert.match(setRip, /RipScoreSurface/);
  assert.match(sharedScoreSurface, /getRipTierPresentation/);
  assert.match(sharedScoreSurface, /data-score-surface/);
});

test("Opening Outcome Profile keeps value milestones primary and only two supporting measurements", () => {
  const keys = [
    ...rip.matchAll(
      /\[\s*"(?:Chance to Recover Cost|Entertainment Cost)",\s*"([^"]+)"/g,
    ),
  ].map((match) => match[1]);
  assert.deepEqual(keys, ["chanceToRecoverCost", "entertainmentCost"]);
  assert.match(rip, /gross modeled market value/);
  assert.match(
    rip,
    /fees,\s*shipping, liquidation friction, bid\/ask spread, and\s*grading/,
  );
  assert.match(rip, /data-opening-value-milestones/);
  assert.doesNotMatch(rip, /data-outcome-range-rail/);
  for (const key of ["p05", "typical", "ev", "price", "p95", "p99"])
    assert.match(rip, new RegExp(`"${key}"`));
  assert.match(rip, /aria-pressed=\{selected\}/);
  assert.match(rip, /onFocus=/);
  assert.match(rip, /onMouseEnter=/);
  assert.match(rip, /data-active-milestone/);
  for (const title of [
    "Low-End Opening",
    "Typical Opening",
    "Expected Value",
    "Current Product Price",
    "Realistic Upside",
    "Jackpot Upside",
  ])
    assert.match(rip, new RegExp(`"${title}"`));
  assert.match(rip, /data-supporting-outcome-metrics/);
  assert.doesNotMatch(rip, /data-primary-outcome-metrics/);
  assert.doesNotMatch(
    rip,
    /data-supporting-outcome=\{"(?:expectedValue|medianValue|p95Value|p99Value)"\}/,
  );
  assert.doesNotMatch(rip, /histogram|density|smoothed/i);
});

test("composition is summarized instead of dumping redundant raw fields", () => {
  assert.match(rip, /productCompositionSummary\(composition\)/);
  assert.match(rip, /data-product-composition/);
  assert.doesNotMatch(rip, />Random Packs</);
});

test("audited user-facing market surfaces use source-agnostic wording", () => {
  for (const source of [client, cardDetail, chaseArticle, market]) {
    assert.doesNotMatch(source, /TCG\s*player/i);
    assert.doesNotMatch(source, /Market source:/i);
  }
  assert.match(
    client,
    /Market prices are derived from tracked market observations/,
  );
  assert.match(
    cardDetail,
    /Market prices are derived from tracked market observations/,
  );
});

test("Basic entitlement keeps Product RIP and opening outcomes behind the lock", () => {
  assert.match(
    client,
    /detail\.rip\.available \? entitled \? <><ProductRipSection/,
  );
  assert.ok(
    client.indexOf("<ProductRipLock />") <
      client.indexOf(": <ProductRipSection detail={detail} />"),
  );
});

test("Set EV Realization is public like Set RIP's own headline, not locked behind Product RIP entitlement", () => {
  // Renders in the unconditional product-identity header, before the
  // entitled/locked/unavailable RIP branch - same access model as Set RIP's
  // ungated SimulationFullReport headline, never inside ProductRipLock or
  // the Plus-only ProductRipSection/ProductOpeningProfile.
  const headerIndex = client.indexOf("data-product-identity");
  const headlineIndex = client.indexOf("data-set-ev-realization-headline");
  const ripBranchIndex = client.indexOf("detail.rip.available ? entitled ?");
  assert.ok(headlineIndex > headerIndex);
  assert.ok(headlineIndex < ripBranchIndex);
  assert.match(client, /selectSetEvRealizationHeadline/);
  assert.doesNotMatch(rip, /selectSetEvRealizationHeadline|setEvRepresentativeness/);
  assert.match(client, /Set EV Realization/);
  // Never claims a per-opener guarantee or reads as product-specific.
  const headlineParagraph = client.slice(headlineIndex, client.indexOf("</p>", headlineIndex));
  assert.doesNotMatch(headlineParagraph, /guarantee/i);
  assert.doesNotMatch(headlineParagraph, /Product EV Realization/);
});

test("Set EV Realization reuses the Set RIP selector/formatters - no forked module, no new request", () => {
  const model = read("./productDetailModel.mjs");
  assert.match(model, /selectEvRepresentativenessPublicV1/);
  assert.doesNotMatch(model, /fetch\(|useEffect\(/);
  assert.doesNotMatch(client, /getSetEvRealization|\/ev-realization/);
});

test("comparisons and final CTA stay canonical without duplicate Set RIP metrics", () => {
  assert.match(comparisons, /comparisonRows\(detail, mode\)/);
  assert.match(comparisons, /buildSealedProductHref\(row\)/);
  assert.match(comparisons, /This Set/);
  assert.match(comparisons, /Same Format/);
  assert.match(client, /data-set-rip-cta/);
  assert.match(client, /href=\{setHref\}/);
  assert.doesNotMatch(
    client,
    /Set Overall RIP|Set Financial RIP|Set Collector Appeal/,
  );
});
