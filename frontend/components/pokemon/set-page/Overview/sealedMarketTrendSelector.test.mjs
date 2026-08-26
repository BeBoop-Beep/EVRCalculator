import test from "node:test";
import assert from "node:assert/strict";
import { SEALED_MARKET_WINDOWS, compactSealedProductLabel, deriveOneDayMovementFromHistory, getDisplayedTrendDirection, selectSealedProduct, selectSealedWindow, sortSealedProductsByCurrentPrice } from "./sealedMarketTrendSelector.mjs";

test("sealed market uses all canonical shared windows and keeps lifetime readable from legacy snapshots", () => {
  assert.deepEqual(SEALED_MARKET_WINDOWS.map(({ key }) => key), ["1D", "7D", "30D", "3M", "6M", "1Y", "lifetime"]);
  const legacy = {
    priceAsOf: "2026-02-01",
    movements: { LT: { status: "available", actualStartDate: "2025-01-01", amount: 12 } },
    history: [{ date: "2025-01-01" }, { date: "2026-02-01" }],
  };
  assert.equal(selectSealedWindow(legacy, "lifetime").movement.amount, 12);
  assert.equal(selectSealedWindow(legacy, "lifetime").history.length, 2);
});

test("variants stay separate and default selection is deterministic", () => {
  const products = [
    { sealedProductId: "a", productFamily: "elite_trainer_box", variantLabel: "Koraidon" },
    { sealedProductId: "b", productFamily: "pokemon_center_elite_trainer_box", variantLabel: "Koraidon" },
  ];
  assert.equal(selectSealedProduct({ products, defaultProductId: "b" }, null).sealedProductId, "b");
  assert.equal(compactSealedProductLabel(products[0]), "ETB — Koraidon");
  assert.equal(compactSealedProductLabel(products[1]), "PC ETB — Koraidon");
});

test("window filtering defaults cleanly to prepared 30D movement", () => {
  const product = {
    priceAsOf: "2026-02-01",
    movements: { "30D": { status: "available", requestedStartDate: "2026-01-02", actualStartDate: "2026-01-02", endDate: "2026-02-01", fullWindowCoverage: true } },
    history: [{ date: "2026-01-01", marketPrice: 1 }, { date: "2026-01-02", marketPrice: 2 }, { date: "2026-02-01", marketPrice: 3 }],
  };
  assert.deepEqual(selectSealedWindow(product, "30D").history.map((point) => point.date), ["2026-01-02", "2026-02-01"]);
});

test("valid v2 and legacy v1 one-day windows return only two distinct endpoints", () => {
  const history = [
    { date: "2026-07-31", marketPrice: 400 },
    { date: "2026-08-01", marketPrice: 430 },
    { date: "2026-08-01", marketPrice: 431.72 },
    { date: "2026-08-02", marketPrice: 422.60 },
  ];
  const prepared = {
    history,
    movements: {
      "1D": {
        status: "available",
        actualStartDate: "2026-08-01",
        requestedStartDate: "2026-08-01",
        endDate: "2026-08-02",
        amount: -9.12,
        percent: -2.11,
      },
    },
  };
  assert.deepEqual(selectSealedWindow(prepared, "1D").history.map((point) => point.date), ["2026-08-01", "2026-08-02"]);

  const legacy = selectSealedWindow({ history, movements: {} }, "1D");
  assert.equal(legacy.movement.comparisonStatus, "legacy_history_derived");
  assert.equal(legacy.movement.amount, -9.12);
  assert.equal(legacy.movement.percent, -2.11);
  assert.deepEqual(legacy.history.map((point) => point.date), ["2026-08-01", "2026-08-02"]);
  assert.equal(deriveOneDayMovementFromHistory(history).startPrice, 431.72);
});

test("missing non-lifetime metadata never falls through to full history", () => {
  const history = [
    { date: "2026-07-01", marketPrice: 100 },
    { date: "2026-08-01", marketPrice: 110 },
    { date: "2026-08-02", marketPrice: 111 },
  ];
  for (const key of ["7D", "30D"]) {
    const selected = selectSealedWindow({ history, movements: {} }, key);
    assert.equal(selected.effectiveWindowKey, "1D");
    assert.equal(selected.history.length, 2);
  }
  const malformed = selectSealedWindow({ history: [{ date: "2026-08-02" }], movements: {} }, "3M");
  assert.equal(malformed.movement.status, "unavailable");
  assert.deepEqual(malformed.history, []);
  const lifetime = selectSealedWindow({
    history,
    movements: {
      "1Y": { status: "available", fullWindowCoverage: true, actualStartDate: "2026-07-01", endDate: "2026-08-02" },
      lifetime: { status: "available", actualStartDate: "2026-07-01", endDate: "2026-08-02" },
    },
  }, "lifetime");
  assert.equal(lifetime.history.length, 3);
});

test("displayed movement determines positive, negative, and neutral chart direction", () => {
  assert.equal(getDisplayedTrendDirection({ percent: -2.11, amount: 99 }), "negative");
  assert.equal(getDisplayedTrendDirection({ percent: 0.7 }), "positive");
  assert.equal(getDisplayedTrendDirection({ percent: 0 }), "neutral");
  assert.equal(getDisplayedTrendDirection({ status: "unavailable" }), "neutral");
  assert.equal(getDisplayedTrendDirection({ amount: 4 }), "positive");
});

test("resolver cascades while keeping requested and effective windows separate", () => {
  const history = [
    { date: "2026-05-04", marketPrice: 100 },
    { date: "2026-07-03", marketPrice: 110 },
    { date: "2026-07-26", marketPrice: 115 },
    { date: "2026-08-01", marketPrice: 120 },
    { date: "2026-08-02", marketPrice: 118 },
  ];
  const available = (actualStartDate, fullWindowCoverage = true) => ({
    status: "available",
    actualStartDate,
    endDate: "2026-08-02",
    fullWindowCoverage,
  });
  const product = {
    priceAsOf: "2026-08-02",
    history,
    movements: {
      "1D": available("2026-08-01"),
      "7D": available("2026-07-26"),
      "30D": available("2026-07-03"),
      "3M": available("2026-05-04"),
      "6M": available("2026-05-04", false),
      "1Y": available("2026-05-04", false),
      lifetime: available("2026-05-04"),
    },
  };

  for (const key of ["1D", "7D", "30D", "3M"]) {
    assert.equal(selectSealedWindow(product, key).effectiveWindowKey, key);
  }
  for (const key of ["6M", "1Y", "lifetime"]) {
    const selected = selectSealedWindow(product, key);
    assert.equal(selected.requestedWindowKey, key);
    assert.equal(selected.effectiveWindowKey, "3M");
    assert.equal(selected.isFallback, true);
    assert.equal(selected.history[0].date, "2026-05-04");
  }
});

test("six-month and one-year coverage promote longer fallbacks and true lifetime", () => {
  const product = {
    priceAsOf: "2026-08-02",
    history: [{ date: "2025-08-02" }, { date: "2026-02-03" }, { date: "2026-08-02" }],
    movements: {
      "1D": { status: "available" },
      "6M": { status: "available", fullWindowCoverage: true, actualStartDate: "2026-02-03", endDate: "2026-08-02" },
      "1Y": { status: "available", fullWindowCoverage: false, actualStartDate: "2025-08-02", endDate: "2026-08-02" },
      lifetime: { status: "available", actualStartDate: "2025-08-02", endDate: "2026-08-02" },
    },
  };
  assert.equal(selectSealedWindow(product, "1Y").effectiveWindowKey, "6M");
  assert.equal(selectSealedWindow(product, "lifetime").effectiveWindowKey, "6M");
  product.movements["1Y"].fullWindowCoverage = true;
  assert.equal(selectSealedWindow(product, "lifetime").effectiveWindowKey, "lifetime");
});

// Sealed product ordering: most expensive first.
//
// The backend previously ordered products by product family, which put the
// Booster Box family ahead of a Pokémon Center ETB worth several times more,
// and defaultProductId simply took the head of that list. Ordering is now
// numeric on currentPrice, and the frontend re-sorts defensively so an older
// snapshot still showcases the right product without a rebuild.

const ascendedHeroes = () => ({
  defaultProductId: "bundle",
  products: [
    { sealedProductId: "bundle", productFamily: "booster_bundle", name: "Booster Bundle", currentPrice: 80.38 },
    { sealedProductId: "pc-etb", productFamily: "pokemon_center_elite_trainer_box", name: "Pokemon Center ETB", currentPrice: 422.6 },
    { sealedProductId: "pack", productFamily: "booster_pack", name: "Booster Pack", currentPrice: 6.75 },
    { sealedProductId: "etb", productFamily: "elite_trainer_box", name: "Elite Trainer Box", currentPrice: 169.41 },
  ],
});

test("products sort by numeric current price descending, not lexically", () => {
  const payload = ascendedHeroes();
  assert.deepEqual(
    sortSealedProductsByCurrentPrice(payload.products).map((item) => item.sealedProductId),
    ["pc-etb", "etb", "bundle", "pack"]
  );

  // The lexical failure mode this guards against: "422.60" < "80.38" as text.
  const ordered = sortSealedProductsByCurrentPrice(payload.products).map((item) => item.currentPrice);
  assert.deepEqual(ordered, [422.6, 169.41, 80.38, 6.75]);
  assert.ok(ordered[0] > ordered[1], "$422.60 must sort above $169.41");
});

test("products without a usable current price sort last", () => {
  const products = [
    { sealedProductId: "missing", productFamily: "booster_box", name: "Booster Box" },
    { sealedProductId: "priced", productFamily: "booster_pack", name: "Booster Pack", currentPrice: 6.75 },
    { sealedProductId: "null", productFamily: "booster_bundle", name: "Booster Bundle", currentPrice: null },
    { sealedProductId: "nan", productFamily: "sleeved_booster_pack", name: "Sleeved Pack", currentPrice: Number.NaN },
    { sealedProductId: "zero", productFamily: "elite_trainer_box", name: "Elite Trainer Box", currentPrice: 0 },
  ];
  const ordered = sortSealedProductsByCurrentPrice(products).map((item) => item.sealedProductId);
  assert.equal(ordered[0], "priced");
  assert.deepEqual(new Set(ordered.slice(1)), new Set(["missing", "null", "nan", "zero"]));
});

test("equal prices break ties deterministically on label, then name, then id", () => {
  const products = [
    { sealedProductId: "z", productFamily: "elite_trainer_box", variantLabel: "Koraidon", name: "ETB Koraidon", currentPrice: 50 },
    { sealedProductId: "a", productFamily: "elite_trainer_box", variantLabel: "Koraidon", name: "ETB Koraidon", currentPrice: 50 },
    { sealedProductId: "m", productFamily: "booster_bundle", name: "Booster Bundle", currentPrice: 50 },
  ];
  const ordered = sortSealedProductsByCurrentPrice(products).map((item) => item.sealedProductId);
  assert.deepEqual(ordered, ["m", "a", "z"]);
  // Stable across input order.
  assert.deepEqual(sortSealedProductsByCurrentPrice([...products].reverse()).map((item) => item.sealedProductId), ordered);
});

test("sorting never mutates the payload array it was given", () => {
  const payload = ascendedHeroes();
  const before = payload.products.map((item) => item.sealedProductId);
  const sorted = sortSealedProductsByCurrentPrice(payload.products);
  assert.deepEqual(payload.products.map((item) => item.sealedProductId), before);
  assert.notEqual(sorted, payload.products);
});

test("the highest-priced product is the initial selection and beats a stale cheaper default", () => {
  const payload = ascendedHeroes();
  // defaultProductId still points at the cheap Booster Bundle from the old
  // family-priority snapshot; price order must win.
  assert.equal(payload.defaultProductId, "bundle");
  assert.equal(selectSealedProduct(payload, null).sealedProductId, "pc-etb");
  assert.equal(selectSealedProduct(payload, undefined).sealedProductId, "pc-etb");
  assert.equal(selectSealedProduct(payload, "no-such-id").sealedProductId, "pc-etb");
});

test("an explicit user selection is always preserved", () => {
  const payload = ascendedHeroes();
  assert.equal(selectSealedProduct(payload, "pack").sealedProductId, "pack");
  assert.equal(selectSealedProduct(payload, "etb").sealedProductId, "etb");
  // Numeric ids still match their string form.
  assert.equal(selectSealedProduct({ products: [{ sealedProductId: 7, currentPrice: 1 }] }, "7").sealedProductId, 7);
});

test("the backend default is used only when no product carries a usable price", () => {
  const payload = {
    defaultProductId: "b",
    products: [
      { sealedProductId: "a", productFamily: "elite_trainer_box", name: "ETB" },
      { sealedProductId: "b", productFamily: "booster_box", name: "Booster Box", currentPrice: null },
    ],
  };
  assert.equal(selectSealedProduct(payload, null).sealedProductId, "b");
  // With no default either, the deterministic sorted head is the final
  // fallback ("Booster Box" precedes "ETB" on the label tie-breaker).
  const head = sortSealedProductsByCurrentPrice(payload.products)[0];
  assert.equal(selectSealedProduct({ products: payload.products }, null).sealedProductId, head.sealedProductId);
  assert.equal(head.sealedProductId, "b");
  assert.equal(selectSealedProduct({ products: [] }, null), null);
  assert.equal(selectSealedProduct(null, null), null);
});

test("standard and Pokemon Center ETBs stay separate products through sorting", () => {
  const payload = ascendedHeroes();
  const ordered = sortSealedProductsByCurrentPrice(payload.products);
  const etbs = ordered.filter((item) => item.productFamily.includes("elite_trainer_box"));
  assert.equal(etbs.length, 2);
  assert.deepEqual(etbs.map((item) => compactSealedProductLabel(item)), ["PC ETB", "ETB"]);
  assert.equal(ordered.length, payload.products.length, "no product is dropped or merged");
});

test("every canonical sealed family has a concise label", () => {
  // The canonical list is the backend classifier's OVERVIEW_FAMILIES. A family
  // missing from FAMILY_LABELS silently degrades to "Sealed Product" on the set
  // page and in the mobile Top Sealed list, which is how half_booster_box
  // (9 live products) shipped unlabeled.
  const CANONICAL_FAMILIES = [
    "booster_box",
    "half_booster_box",
    "enhanced_booster_box",
    "elite_trainer_box",
    "pokemon_center_elite_trainer_box",
    "booster_bundle",
    "loose_booster_pack",
    "sleeved_booster_pack",
  ];
  for (const productFamily of CANONICAL_FAMILIES) {
    assert.notEqual(
      compactSealedProductLabel({ productFamily }),
      "Sealed Product",
      `${productFamily} must have a concise label`
    );
  }
  // The generic fallback still applies to a family this build does not know.
  assert.equal(compactSealedProductLabel({ productFamily: "future_family" }), "Sealed Product");
});
