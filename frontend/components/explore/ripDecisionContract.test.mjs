import assert from "node:assert/strict";
import test from "node:test";
import {
  buildBreakEvenAxis,
  buildEdgeSentence,
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
          sealedProductId: "sku-sleeved-pack",
          productName: "Sleeved Booster Pack",
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
          sealedProductId: "sku-booster-box",
          productName: "Booster Box",
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

test("a current run that models no sealed products is its own state", () => {
  // Distinct from both "no contract" and "no current run": the run exists and
  // is current, it simply has no sealed product rows.
  const decision = selectRipDecisionContract(
    currentRunContract({
      sealedProducts: { runStatus: "current", productCount: 0, products: [] },
    })
  );

  assert.equal(decision.contractPresent, true);
  assert.equal(decision.available, true, "the run IS available; only the product list is empty");
  assert.deepEqual(decision.products, []);
  assert.equal(decision.productCount, 0);
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
  assert.equal(defaultSelectedProductKey(decision.products), "sku-sleeved-pack");
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

test("two priced loose-pack SKUs yield no price rather than an arbitrary one", () => {
  const twoPacks = selectRipDecisionContract(
    currentRunContract({
      sealedProducts: {
        runStatus: "current",
        productCount: 2,
        products: [
          {
            sealedProductId: "sku-pack-a",
            productName: "Sleeved Booster Pack",
            productFamily: "sleeved_booster_pack",
            packCount: 1,
            marketPrice: 13.25,
          },
          {
            sealedProductId: "sku-pack-b",
            productName: "Booster Pack (Blister)",
            productFamily: "sleeved_booster_pack",
            packCount: 1,
            marketPrice: 15.99,
          },
        ],
      },
    })
  );

  assert.equal(
    selectLoosePackMarketPrice(twoPacks.products),
    null,
    "no canonical loose-pack quote exists across SKUs, so none may be invented"
  );
  // Specifically not any of the undeclared policies.
  assert.notEqual(selectLoosePackMarketPrice(twoPacks.products), 13.25, "not the first or cheapest");
  assert.notEqual(selectLoosePackMarketPrice(twoPacks.products), 15.99, "not the highest");
});

test("an unpriced loose-pack SKU does not make a single priced one ambiguous", () => {
  const mixed = selectRipDecisionContract(
    currentRunContract({
      sealedProducts: {
        runStatus: "current",
        productCount: 2,
        products: [
          { sealedProductId: "sku-pack-a", productFamily: "sleeved_booster_pack", packCount: 1, marketPrice: 13.25 },
          { sealedProductId: "sku-pack-b", productFamily: "sleeved_booster_pack", packCount: 1, marketPrice: null },
        ],
      },
    })
  );
  assert.equal(selectLoosePackMarketPrice(mixed.products), 13.25, "only priced SKUs count");
});

// --- SKU identity: several products can share one family ------------------

/** Two real ETB SKUs of the SAME family, as the contract can publish them. */
function twoEliteTrainerBoxSkus() {
  return currentRunContract({
    sealedProducts: {
      runStatus: "current",
      productCount: 2,
      products: [
        {
          sealedProductId: "sku-etb-standard",
          productName: "Elite Trainer Box (Umbreon)",
          productFamily: "elite_trainer_box",
          packCount: 9,
          marketPrice: 59.99,
          modelBreakEvenPrice: 52.0,
          modelEdgePercent: -13.32,
          typicalOpening: 41.5,
          chanceToRecoverCost: 0.22,
        },
        {
          sealedProductId: "sku-etb-espeon",
          productName: "Elite Trainer Box (Espeon)",
          productFamily: "elite_trainer_box",
          packCount: 9,
          marketPrice: 74.5,
          modelBreakEvenPrice: 52.0,
          modelEdgePercent: -30.2,
          typicalOpening: 41.5,
          chanceToRecoverCost: 0.14,
        },
      ],
    },
  });
}

test("two SKUs of one family both survive and stay distinct", () => {
  const { products } = selectRipDecisionContract(twoEliteTrainerBoxSkus());

  assert.equal(products.length, 2, "neither SKU may be dropped");
  assert.deepEqual(
    products.map((product) => product.family),
    ["elite_trainer_box", "elite_trainer_box"],
    "they genuinely share a family"
  );
  assert.deepEqual(products.map((product) => product.key), ["sku-etb-standard", "sku-etb-espeon"]);
  assert.equal(new Set(products.map((product) => product.key)).size, 2, "keys must be unique");
  assert.deepEqual(
    products.map((product) => product.label),
    ["Elite Trainer Box (Umbreon)", "Elite Trainer Box (Espeon)"],
    "each SKU keeps its own name instead of collapsing to the family label"
  );
  assert.deepEqual(
    products.map((product) => product.sealedProductId),
    ["sku-etb-standard", "sku-etb-espeon"]
  );
});

test("the family is never used as the product key", () => {
  const { products } = selectRipDecisionContract(twoEliteTrainerBoxSkus());
  for (const product of products) {
    assert.notEqual(product.key, product.family, "keying on family collides same-family SKUs");
  }
});

test("selecting the second SKU resolves the second SKU's economics", () => {
  const { products } = selectRipDecisionContract(twoEliteTrainerBoxSkus());
  // The page resolves a selection exactly this way.
  const second = products.find((product) => product.key === "sku-etb-espeon");

  assert.equal(second.productName, "Elite Trainer Box (Espeon)");
  assert.equal(second.marketPrice, 74.5, "must not resolve the sibling SKU's price");
  assert.equal(second.modelEdgePercent, -30.2);
  assert.equal(second.chanceToRecoverCost, 0.14);
});

test("the default selection is still the first priced SKU, not a family", () => {
  const { products } = selectRipDecisionContract(twoEliteTrainerBoxSkus());
  assert.equal(defaultSelectedProductKey(products), "sku-etb-standard");
});

test("a product with no sealed product id still gets a unique fallback key", () => {
  const { products } = selectRipDecisionContract(
    currentRunContract({
      sealedProducts: {
        runStatus: "current",
        productCount: 2,
        products: [
          { productFamily: "booster_box", productName: null, marketPrice: 189 },
          { productFamily: "booster_box", productName: null, marketPrice: 205 },
        ],
      },
    })
  );
  assert.equal(products.length, 2);
  assert.equal(new Set(products.map((product) => product.key)).size, 2, "fallback keys stay unique");
});

// --- edge copy keeps the market-price denominator -------------------------

test("a positive edge says modeled value is above MARKET COST", () => {
  // edge = (110 / 100 - 1) * 100 = +10. The market price is 9.09% below
  // break-even, NOT 10%, so that phrasing must never appear.
  const sentence = buildEdgeSentence({
    marketPrice: 100,
    modelBreakEvenPrice: 110,
    modelEdgePercent: 10,
  });

  assert.equal(
    sentence,
    "At today's $100.00 price, modeled long-run opening value is 10% above market cost."
  );
  assert.ok(!sentence.includes("below modeled break-even"), "that re-bases the percentage");
  assert.ok(!sentence.includes("9.09"), "no second percentage metric is introduced");
});

test("a negative edge uses the same denominator and wording", () => {
  assert.equal(
    buildEdgeSentence({ marketPrice: 13.25, modelBreakEvenPrice: 9.35, modelEdgePercent: -29.4 }),
    "At today's $13.25 price, modeled long-run opening value is 29.4% below market cost."
  );
});

test("a zero edge sits exactly at break-even", () => {
  assert.equal(
    buildEdgeSentence({ marketPrice: 50, modelBreakEvenPrice: 50, modelEdgePercent: 0 }),
    "Today's $50.00 price sits exactly at modeled break-even."
  );
});

test("an unavailable edge or price yields no sentence rather than a guess", () => {
  assert.equal(buildEdgeSentence({ marketPrice: 100, modelEdgePercent: null }), null);
  assert.equal(buildEdgeSentence({ marketPrice: null, modelEdgePercent: 10 }), null);
  assert.equal(buildEdgeSentence(null), null);
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
