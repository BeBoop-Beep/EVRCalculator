import test from "node:test";
import assert from "node:assert/strict";
import { SEALED_MARKET_WINDOWS, compactSealedProductLabel, deriveOneDayMovementFromHistory, getDisplayedTrendDirection, selectSealedProduct, selectSealedWindow } from "./sealedMarketTrendSelector.mjs";

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
