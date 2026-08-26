import test from "node:test";
import assert from "node:assert/strict";
import { applySetRipEntitlement } from "./setRipEntitlement.mjs";
import { readCanonicalBlock, resolveCanonicalRipV7 } from "../../components/explore/canonicalRipV7.mjs";

const payload = {
  productFamilyRankings: { families: { booster_box: { rank: 1 } } },
  rankings: [{ rarity_bucket: "sir", total_sampled_value: 999 }],
  targets: [{
    evRepresentativeness: { realizationHorizon: { packCount: 250 } },
    publicRipContractV10: { overallRip: { leaderNormalizedScore: 87, rank: 2, factors: { secret: 1 } }, financialRip: { leaderNormalizedScore: 91, dimensions: [1, 2] }, collectorAppeal: { relativeScore: 66, coverage: 0.8 }, audit: { weights: [1] } },
    ripDecision: {
      sealedProducts: { products: [{
        sealedProductId: "box-1", productName: "Booster Box", productFamily: "booster_box",
        packCount: 36, marketPrice: 119.99, overallRipScore: 96, financialRipScore: 91,
        typicalOpening: 55, chanceToRecoverCost: 0.12,
        entertainmentCost: { entertainmentCost: 65 },
      }] },
      topChase: { cardName: "Chase", impliedOddsOneInN: 480, packsFor50PercentChance: 333, packsFor90PercentChance: 1105 },
    },
  }],
};

test("Basic set payload keeps facts and strips Index Plus decision intelligence", () => {
  const result = applySetRipEntitlement(payload, { id: "basic", index_plan: null });
  const target = result.targets[0];
  const product = target.ripDecision.sealedProducts.products[0];
  assert.deepEqual(product, { sealedProductId: "box-1", productName: "Booster Box", productFamily: "booster_box", packCount: 36, marketPrice: 119.99 });
  assert.equal(result.productFamilyRankings, null);
  assert.deepEqual(result.rankings, []);
  assert.equal(target.evRepresentativeness, null);
  assert.deepEqual(target.publicRipContractV10.overallRip, { leaderNormalizedScore: 87, rank: 2 });
  assert.deepEqual(target.publicRipContractV10.financialRip, { leaderNormalizedScore: 91 });
  assert.deepEqual(target.publicRipContractV10.collectorAppeal, { relativeScore: 66 });
  assert.equal(target.publicRipContractV10.audit, undefined);
  assert.equal(target.ripDecision.topChase.impliedOddsOneInN, 480);
  assert.equal(target.ripDecision.topChase.packsFor50PercentChance, null);
  assert.equal(target.ripDecision.topChase.packsFor90PercentChance, null);
});

test("Index Plus receives the canonical premium publication unchanged", () => {
  assert.equal(applySetRipEntitlement(payload, { id: "plus", index_plan: "plus" }), payload);
  assert.equal(applySetRipEntitlement(payload, { id: "premium", index_plan: "premium" }), payload);
});

test("Basic redaction preserves authoritative V10/V4 set headline scores", () => {
  const source = { publicRipContractV10: {
    overallRip: { leaderNormalizedScore: 87.4, rank: 2, tier: "S", rankedSetCount: 20, components: { productRip: 100 } },
    financialRip: { leaderNormalizedScore: 92.1, rank: 1, tier: "S", rankedSetCount: 20, components: { winFrequency: 99 } },
    collectorAppeal: { relativeScore: 65.2, rank: 8, rankedSetCount: 20, components: { roster: 70 } },
  } };
  const redacted = applySetRipEntitlement(source, { index_plan: null });
  const canonical = resolveCanonicalRipV7(redacted);
  assert.equal(readCanonicalBlock(canonical.overall).publicScore, 87.4);
  assert.equal(readCanonicalBlock(canonical.financialRip).publicScore, 92.1);
  assert.equal(readCanonicalBlock(canonical.collectorAppeal).publicScore, 65.2);
  assert.equal(redacted.publicRipContractV10.overallRip.components, undefined);
});
