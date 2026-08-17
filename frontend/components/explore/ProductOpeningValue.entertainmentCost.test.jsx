// ENTERTAINMENT COST, tested by RENDERING the real product surface.
//
// The metric is display-only: every number below originates in the backend
// contract fixture and must reach the screen unchanged. These tests therefore
// assert the RENDERED strings, not the selector's return value, because the
// failure modes that matter are all presentational — a negative cost formatted
// as "$-4.25", an unavailable product printed as "$0.00", a per-pack figure
// quietly divided in the browser.

// Registered BEFORE the component import: it pulls in a CSS Module.
import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import React from "react";
import TestRenderer from "react-test-renderer";

import ProductOpeningValue from "./ProductOpeningValue.jsx";
import { selectRipDecisionContract } from "./ripDecisionContract.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const directory = path.dirname(new URL(import.meta.url).pathname.slice(1));

/** The backend block shape, verbatim from `entertainment_cost.py`. */
function entertainmentBlock(overrides = {}) {
  return {
    entertainmentCost: 75.0,
    entertainmentCostPerPackEquivalent: 2.08,
    entertainmentCostRatio: 0.4167,
    purchasePrice: 180.0,
    expectedValue: 105.0,
    packCount: 36,
    recoveryModel: "gross_market_value",
    accessoryValueIncluded: false,
    guaranteedComponentIncluded: false,
    available: true,
    reason: null,
    contractVersion: "entertainment-cost-v1",
    ...overrides,
  };
}

function product(overrides = {}) {
  return {
    sealedProductId: "box-1",
    productName: "Booster Box",
    productFamily: "booster_box",
    packCount: 36,
    marketPrice: 180.0,
    modelBreakEvenPrice: 168.0,
    modeledReturnPercent: 58.3,
    modelEdgePercent: -6.7,
    typicalOpening: 98.0,
    chanceToRecoverCost: 0.12,
    entertainmentCost: entertainmentBlock(),
    ...overrides,
  };
}

function decisionFor(products) {
  return selectRipDecisionContract({
    currentRunAvailable: true,
    comparisonScope: "within_product_family_only",
    crossFormatComparable: false,
    sealedProducts: { runStatus: "current", productCount: products.length, products },
  });
}

function render(products) {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(ProductOpeningValue, {
        decision: decisionFor(products),
        setName: "Test Set",
      }),
    );
  });
  return renderer;
}

/** Every text node in the tree, flattened. */
function textOf(renderer) {
  const chunks = [];
  const walk = (node) => {
    if (node === null || node === undefined || node === false) return;
    if (typeof node === "string" || typeof node === "number") {
      chunks.push(String(node));
      return;
    }
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    walk(node.children);
  };
  walk(renderer.toJSON());
  return chunks.join("");
}

/** All rendered props of nodes carrying `attribute`. */
function nodesWith(renderer, attribute) {
  const found = [];
  const walk = (node) => {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (node.props && attribute in node.props) found.push(node);
    (node.children || []).forEach(walk);
  };
  walk(renderer.toJSON());
  return found;
}

test("a supported product renders the published cost, per-pack figure and gross basis", () => {
  const renderer = render([product()]);
  const text = textOf(renderer);

  // The backend's numbers, not a re-derivation of 180 - 105 or 75 / 36.
  assert.ok(text.includes("$75.00"), "entertainment cost is shown");
  assert.ok(text.includes("$2.08"), "per-pack equivalent is shown");
  assert.ok(text.includes("$105.00"), "expected value is shown");
  assert.ok(text.includes("Entertainment Cost"), "the metric is labelled in plain language");
  assert.ok(text.includes("Entertainment Cost / Pack"));
  // The recovery model is stated, so the reader knows the calculation basis.
  assert.ok(
    text.includes("gross market value before selling fees"),
    "gross-market-value limitation is explicit",
  );
  assert.equal(nodesWith(renderer, "data-recovery-model").length, 1);
});

test("the per-pack figure appears in EVERY product row, so formats compare", () => {
  const renderer = render([
    product(),
    product({
      sealedProductId: "etb-1",
      productName: "Elite Trainer Box",
      productFamily: "elite_trainer_box",
      packCount: 9,
      marketPrice: 65.0,
      entertainmentCost: entertainmentBlock({
        entertainmentCost: 34.0,
        entertainmentCostPerPackEquivalent: 3.78,
        purchasePrice: 65.0,
        expectedValue: 31.0,
        packCount: 9,
      }),
    }),
  ]);

  const cells = nodesWith(renderer, "data-entertainment-cost-per-pack");
  assert.equal(cells.length, 2, "one per-pack cell per product row");
  const text = textOf(renderer);
  // The cheaper product overall is the more expensive entertainment per pack —
  // the whole reason the normalized figure is exposed at row level.
  assert.ok(text.includes("$2.08"));
  assert.ok(text.includes("$3.78"));
});

test("an unavailable product shows the not-modeled state and never $0.00", () => {
  const renderer = render([
    product({
      entertainmentCost: {
        entertainmentCost: null,
        entertainmentCostPerPackEquivalent: null,
        entertainmentCostRatio: null,
        purchasePrice: 180.0,
        expectedValue: null,
        packCount: 36,
        recoveryModel: "gross_market_value",
        accessoryValueIncluded: false,
        guaranteedComponentIncluded: false,
        available: false,
        reason: "simulation_result_unavailable",
        contractVersion: "entertainment-cost-v1",
      },
    }),
  ]);
  const text = textOf(renderer);

  assert.ok(text.includes("Not modeled yet"), "the site's unavailable language is used");
  assert.ok(!text.includes("$0.00"), "a missing value is never rendered as zero");
  // The internal reason is diagnostics, not user-facing copy.
  assert.ok(!text.includes("simulation_result_unavailable"));
  assert.equal(
    nodesWith(renderer, "data-entertainment-cost-per-pack")[0].props[
      "data-entertainment-cost-per-pack"
    ],
    "unavailable",
  );
});

test("a negative entertainment cost survives formatting and is not relabelled", () => {
  const renderer = render([
    product({
      entertainmentCost: entertainmentBlock({
        entertainmentCost: -4.25,
        entertainmentCostPerPackEquivalent: -0.12,
        entertainmentCostRatio: -0.0236,
        purchasePrice: 180.0,
        expectedValue: 184.25,
      }),
    }),
  ]);
  const text = textOf(renderer);

  assert.ok(text.includes("-$4.25"), "the minus sign leads the currency symbol");
  assert.ok(text.includes("-$0.12"));
  assert.ok(!text.includes("$-4.25"), "the sign is never buried inside the symbol");
  assert.ok(!text.includes("$0.00"), "a negative is never clamped to zero");
  assert.ok(!/profit/i.test(text), "a negative cost is never described as profit");
});

test("a product with no entertainment block at all still renders safely", () => {
  const renderer = render([product({ entertainmentCost: undefined })]);
  const text = textOf(renderer);

  assert.ok(text.includes("Booster Box"), "the product itself still renders");
  assert.ok(text.includes("Not modeled yet"));
  assert.ok(!text.includes("$0.00"));
  // With no published recovery model there is no basis to describe, so the
  // footnote must not claim one.
  assert.equal(nodesWith(renderer, "data-recovery-model").length, 0);
});

test("missing per-pack metadata degrades to the total alone", () => {
  // A published total with no pack count: the total is still valid, only the
  // normalization is missing, and the backend says so by nulling one field.
  const renderer = render([
    product({
      entertainmentCost: entertainmentBlock({
        entertainmentCostPerPackEquivalent: null,
        packCount: null,
      }),
    }),
  ]);
  const text = textOf(renderer);

  assert.ok(text.includes("$75.00"), "the total survives a missing pack count");
  assert.ok(text.includes("Not modeled yet"), "only the per-pack figure is unavailable");
});

test("copy never describes the metric as a loss or a guaranteed outcome", () => {
  // Comments legitimately NAME the forbidden phrasings in order to forbid
  // them, so only the code — where user-facing copy lives — is scanned.
  const source = fs
    .readFileSync(path.resolve(directory, "ProductOpeningValue.jsx"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
  for (const forbidden of [
    "guaranteed loss",
    "money lost",
    "you lose",
    "realized loss",
    "net liquidation",
  ]) {
    assert.ok(
      !source.toLowerCase().includes(forbidden),
      `copy must not say "${forbidden}" — the recovery model is gross market value`,
    );
  }
  assert.ok(source.includes("modeled expectation rather than a guaranteed outcome"));
});

test("ENTERTAINMENT COST IS BACKEND-OWNED: the frontend never recomputes it", () => {
  // The formulas are trivial, which is exactly why a frontend copy is dangerous:
  // it would look right while silently disagreeing with the canonical module
  // (Stage 2 expected value already contains its guaranteed promo, and the
  // per-pack divisor is the MODELED pack count).
  for (const file of ["ProductOpeningValue.jsx", "ripDecisionContract.mjs"]) {
    const source = fs.readFileSync(path.resolve(directory, file), "utf8");
    const code = source
      // Comments legitimately NAME the forbidden formulas in order to forbid them.
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    assert.ok(
      !/purchasePrice\s*-\s*expectedValue/.test(code),
      `${file} must not derive entertainment cost`,
    );
    assert.ok(
      !/marketPrice\s*-\s*.*expectedValue/.test(code),
      `${file} must not derive entertainment cost from the product price`,
    );
    assert.ok(
      !/entertainmentCost\s*\/\s*pack/i.test(code),
      `${file} must not derive the per-pack equivalent`,
    );
  }
});
