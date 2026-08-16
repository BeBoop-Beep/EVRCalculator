import assert from "node:assert/strict";
import test from "node:test";
import {
  buildBreakEvenAxis,
  defaultSelectedProductKey,
  selectLoosePackMarketPrice,
  selectRipDecisionContract,
} from "./ripDecisionContract.mjs";

/** A contract shaped exactly like `build_rip_decision_contract` publishes it. */
function currentRunContract(overrides = {}) {
  return {
    contractVersion: "rip-decision-v1",
    sourceCalculationRunId: "run-abc",
    currentRunAvailable: true,
    comparisonScope: "within_product_family_only",
    crossFormatComparable: false,
    sealedProducts: {
      runStatus: "current",
      sourceCalculationRunId: "run-abc",
      productCount: 2,
      products: [
        {
          productFamily: "sleeved_booster_pack",
          packCount: 1,
          marketPrice: 13.25,
          modelBreakEvenPrice: 9.35,
          modeledReturnPercent: 70.57,
          modelEdgePercent: -29.43,
          typicalOpening: 3.34,
          chanceToRecoverCost: 0.046,
        },
        {
          productFamily: "booster_box",
          packCount: 36,
          marketPrice: 189,
          modelBreakEvenPrice: 181,
          modeledReturnPercent: 95.77,
          modelEdgePercent: -4.23,
          typicalOpening: 150.2,
          chanceToRecoverCost: 0.31,
        },
      ],
    },
    topChase: {
      cardId: "card-1",
      cardVariantId: "variant-1",
      cardName: "Umbreon ex",
      rarity: "special illustration rare",
      imageSmallUrl: "https://img.example/small.png",
      currentMarketPrice: 412.5,
      modeledProbability: 0.0008,
      impliedOddsOneInN: 1250,
      packsFor50PercentChance: 866,
      packsFor90PercentChance: 2878,
      sourceCalculationRunId: "run-abc",
    },
    ...overrides,
  };
}

// --- A. selector / normalization -----------------------------------------

test("a current run publishes products and top chase from the real contract keys", () => {
  const decision = selectRipDecisionContract(currentRunContract());

  assert.equal(decision.contractPresent, true);
  assert.equal(decision.available, true);
  assert.equal(decision.sourceCalculationRunId, "run-abc");
  assert.equal(decision.productCount, 2);
  assert.equal(decision.products.length, 2);
  assert.equal(decision.topChase.name, "Umbreon ex");
  assert.equal(decision.topChase.currentMarketPrice, 412.5);
  assert.equal(decision.topChase.impliedOddsOneInN, 1250);
  assert.equal(decision.topChase.packsFor50PercentChance, 866);
  assert.equal(decision.topChase.packsFor90PercentChance, 2878);
});

test("a snapshot predating the contract is distinguishable from a run-less one", () => {
  const missing = selectRipDecisionContract(undefined);
  assert.equal(missing.contractPresent, false);
  assert.equal(missing.available, false);

  const noRun = selectRipDecisionContract({
    currentRunAvailable: false,
    sourceCalculationRunId: null,
    sealedProducts: { runStatus: "no_current_run", productCount: 0, products: [] },
    topChase: null,
  });
  assert.equal(noRun.contractPresent, true);
  assert.equal(noRun.available, false);
});

// --- F. unavailable state must not leak stale economics -------------------

test("no current run never surfaces product economics or a chase", () => {
  const decision = selectRipDecisionContract(
    currentRunContract({ currentRunAvailable: false })
  );

  assert.equal(decision.available, false);
  assert.deepEqual(decision.products, [], "stale product rows must not be published");
  assert.equal(decision.topChase, null, "stale chase must not be published");
});

test("absent numbers stay null and are never coerced to zero", () => {
  const decision = selectRipDecisionContract(
    currentRunContract({
      sealedProducts: {
        runStatus: "current",
        productCount: 1,
        products: [
          {
            productFamily: "booster_bundle",
            marketPrice: null,
            modelBreakEvenPrice: 42.5,
            modelEdgePercent: null,
            modeledReturnPercent: null,
          },
        ],
      },
    })
  );

  const [product] = decision.products;
  assert.equal(product.marketPrice, null);
  assert.equal(product.modelEdgePercent, null);
  assert.notEqual(product.modelEdgePercent, 0);
  assert.equal(product.modelBreakEvenPrice, 42.5);
});

test("a chase with no identity and no price is not rendered as a chase", () => {
  const decision = selectRipDecisionContract(
    currentRunContract({ topChase: { cardName: "", currentMarketPrice: null } })
  );
  assert.equal(decision.topChase, null);
});

// --- product ordering: contract order, never score order ------------------

test("product order is the contract's order, not an edge or score ranking", () => {
  const decision = selectRipDecisionContract(currentRunContract());
  assert.deepEqual(
    decision.products.map((product) => product.family),
    ["sleeved_booster_pack", "booster_box"],
    "the worse-edge pack must stay first because the contract supplied it first"
  );
  assert.deepEqual(decision.products.map((product) => product.order), [0, 1]);
});

test("the default selection is the first priced product, not the strongest edge", () => {
  const decision = selectRipDecisionContract(currentRunContract());
  assert.equal(defaultSelectedProductKey(decision.products), "sleeved_booster_pack");
});

test("cross-format comparability is republished as false", () => {
  const decision = selectRipDecisionContract(currentRunContract());
  assert.equal(decision.crossFormatComparable, false);
  assert.equal(decision.comparisonScope, "within_product_family_only");
});

// --- gross-spend precondition ---------------------------------------------

test("loose pack price is read only from a single-pack product", () => {
  const decision = selectRipDecisionContract(currentRunContract());
  assert.equal(selectLoosePackMarketPrice(decision.products), 13.25);

  const boxOnly = selectRipDecisionContract(
    currentRunContract({
      sealedProducts: {
        runStatus: "current",
        productCount: 1,
        products: [{ productFamily: "booster_box", packCount: 36, marketPrice: 189 }],
      },
    })
  );
  assert.equal(
    selectLoosePackMarketPrice(boxOnly.products),
    null,
    "without a modeled loose pack there is no price to express spend in"
  );
});

// --- B. break-even axis geometry ------------------------------------------

test("break-even axis places zero at centre and signs the two directions", () => {
  const axis = buildBreakEvenAxis([
    { modelEdgePercent: -30 },
    { modelEdgePercent: 6 },
  ]);

  assert.equal(axis.positionFor(0), 50, "zero sits exactly on break-even");
  assert.ok(axis.positionFor(-30) < 50, "negative edge renders below break-even");
  assert.ok(axis.positionFor(6) > 50, "positive edge renders above break-even");
});

test("the axis is symmetric so equal magnitudes are equally far from zero", () => {
  const axis = buildBreakEvenAxis([{ modelEdgePercent: -20 }, { modelEdgePercent: 4 }]);
  assert.equal(50 - axis.positionFor(-8), axis.positionFor(8) - 50);
});

test("an unavailable edge has no axis position and is not drawn at zero", () => {
  const axis = buildBreakEvenAxis([{ modelEdgePercent: -20 }]);
  assert.equal(axis.positionFor(null), null);
  assert.equal(axis.positionFor(undefined), null);
  assert.notEqual(axis.positionFor(null), 50);
});

test("an all-unavailable product list still yields a usable symmetric domain", () => {
  const axis = buildBreakEvenAxis([{ modelEdgePercent: null }]);
  assert.ok(axis.domain > 0);
  assert.equal(axis.positionFor(0), 50);
});
