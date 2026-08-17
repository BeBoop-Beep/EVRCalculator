import test from "node:test";
import assert from "node:assert/strict";
import { normalisePayload } from "./explorePageServerCore.mjs";

const backendPayload = () => ({
  summary: { name: "Perfect Order" },
  ripDecision: {
    currentRunAvailable: true,
    sourceCalculationRunId: "run-1",
    sealedProducts: {
      products: [
        {
          productKey: "sleeved_pack",
          entertainmentCost: 4.1,
          entertainmentCostPerPackEquivalent: 4.1,
          entertainmentCostRatio: 1.0,
          recoveryModel: "modeled",
          available: true,
        },
      ],
    },
    topChase: { cardName: "Example", currentMarketPrice: 100 },
  },
});

test("normalisePayload forwards the backend ripDecision contract to the SSR payload", () => {
  const normalised = normalisePayload(backendPayload());
  assert.equal(typeof normalised.ripDecision, "object");
  assert.notEqual(normalised.ripDecision, null);
  assert.deepEqual(normalised.ripDecision, backendPayload().ripDecision);
});

test("entertainment cost fields survive normalisation unchanged", () => {
  const product = normalisePayload(backendPayload()).ripDecision.sealedProducts.products[0];
  assert.equal(product.entertainmentCost, 4.1);
  assert.equal(product.entertainmentCostPerPackEquivalent, 4.1);
  assert.equal(product.entertainmentCostRatio, 1.0);
  assert.equal(product.recoveryModel, "modeled");
  assert.equal(product.available, true);
});

test("a missing ripDecision stays null rather than becoming an empty object", () => {
  assert.equal(normalisePayload({ summary: {} }).ripDecision, null);
  assert.equal(normalisePayload({ ripDecision: "nope" }).ripDecision, null);
  assert.equal(normalisePayload({ ripDecision: [] }).ripDecision, null);
});

test("the SSR payload does not gain the dedicated full chaseEconomics dataset", () => {
  const withChase = backendPayload();
  withChase.chaseEconomics = { cards: new Array(25).fill({ cardName: "x" }) };
  const normalised = normalisePayload(withChase);
  assert.equal(normalised.chaseEconomics, undefined);
  assert.equal(normalised.ripDecision.chaseEconomics, undefined);
  assert.notEqual(normalised.ripDecision.topChase, undefined);
});
