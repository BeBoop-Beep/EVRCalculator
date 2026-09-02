import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { buildProductParentSetHref, comparisonRows, formatStrength, pluralFamilyLabel, productCompositionSummary, selectProductMarketWindow, selectSetEvRealizationHeadline } from "./productDetailModel.mjs";

const evRep = (runId, packCount = 420) => ({
  contractVersion: "ev_representativeness_public_v1",
  methodVersion: "ev_representativeness_v1",
  calculationRunId: runId,
  realizationHorizon: { targetEvRatio: 0.8, openerProbability: 0.8, packCount, status: "confirmed" },
});

test("set EV realization headline renders only from the product's own validated run", () => {
  const rip = { calculationRunId: "run-a", setEvRepresentativeness: evRep("run-a") };
  const headline = selectSetEvRealizationHeadline(rip);
  assert.equal(headline.packCount, 420);
  assert.equal(headline.targetEvRatio, 0.8);
  assert.equal(headline.openerProbability, 0.8);
});

test("set EV realization headline is omitted for a mismatched run, wrong contract, or missing data", () => {
  assert.equal(selectSetEvRealizationHeadline({ calculationRunId: "run-a", setEvRepresentativeness: evRep("run-b") }), null);
  assert.equal(selectSetEvRealizationHeadline({ calculationRunId: "run-a", setEvRepresentativeness: { ...evRep("run-a"), contractVersion: "future_v2" } }), null);
  assert.equal(selectSetEvRealizationHeadline({ calculationRunId: "run-a", setEvRepresentativeness: null }), null);
  assert.equal(selectSetEvRealizationHeadline({ calculationRunId: "run-a" }), null);
  assert.equal(selectSetEvRealizationHeadline(null), null);
});

test("set EV realization headline is the SAME selector Set RIP uses, not a forked implementation", () => {
  const model = fs.readFileSync(path.resolve("components/pokemon/sealed-product-detail/productDetailModel.mjs"), "utf8");
  assert.match(model, /import \{ selectEvRepresentativenessPublicV1 \} from "\.\.\/\.\.\/explore\/evRepresentativenessSelector\.mjs"/);
  assert.doesNotMatch(model, /HEADLINE_REALIZATION_TARGET|HEADLINE_CONFIDENCE|realization_ge_0\.80/);
});

test("product market windows consume backend movement authority", () => {
  const market = { history: [{ date: "2026-01-01", marketPrice: 10 }, { date: "2026-01-10", marketPrice: 12 }], movements: { "30D": { status: "available", amount: 2, percent: 20, actualStartDate: "2026-01-01", endDate: "2026-01-10", fullWindowCoverage: false } } };
  const selected = selectProductMarketWindow(market, "30D");
  assert.equal(selected.movement.deltaAmount, 2);
  assert.equal(selected.movement.deltaPercent, 20);
  assert.equal(selected.partial, true);
  assert.equal(selected.history.length, 2);
});

test("composition summaries stay concise for simple products and enrich guaranteed products", () => {
  assert.deepEqual(productCompositionSummary({ packCount: 11, randomPackCount: 11, guaranteedComponentCount: 0 }), { available: true, summary: "11 Packs", guaranteedValue: null });
  assert.deepEqual(productCompositionSummary({ packCount: 11, randomPackCount: 11, guaranteedComponentCount: 2, guaranteedComponentMarketValue: 18.5 }), { available: true, summary: "11 Packs + 2 Modeled Guaranteed Components", guaranteedValue: 18.5 });
  assert.deepEqual(productCompositionSummary({}), { available: false, summary: "", guaranteedValue: null });
});

test("comparison selection excludes current, duplicates, and cross-family rows", () => {
  const detail = { product: { id: "current", productFamily: "booster_box" }, comparisons: { sameSet: [{ sealedProductId: "current" }, { sealedProductId: "a" }], sameFamily: [{ sealedProductId: "current", productFamily: "booster_box" }, { sealedProductId: "a", productFamily: "booster_box" }, { sealedProductId: "a", productFamily: "booster_box" }, { sealedProductId: "wrong", productFamily: "elite_trainer_box" }] } };
  assert.deepEqual(comparisonRows(detail, "sameSet").map((row) => row.sealedProductId), ["a"]);
  assert.deepEqual(comparisonRows(detail, "sameFamily").map((row) => row.sealedProductId), ["a"]);
});

test("format language and canonical set route match Rankings and set routing", () => {
  assert.equal(formatStrength({ familyRank: 1, publicTier: "S" }), "Format leader");
  assert.equal(formatStrength({ familyRank: 3, publicTier: "A" }), "Strong in format");
  assert.equal(pluralFamilyLabel("Elite Trainer Box"), "Elite Trainer Boxes");
  assert.equal(buildProductParentSetHref({ slug: "scarlet-violet-151" }), "/TCGs/Pokemon/Sets/scarlet-violet-151");
});
